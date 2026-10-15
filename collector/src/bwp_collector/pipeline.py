import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml
from uuid6 import uuid7

from .contracts import BATCH_SCHEMA, CONFIG_SCHEMA, SAMPLE_SCHEMA, validate
from .imaging import crop, preprocess, read_image, write_image
from .validation import FIELDS, decimal_string, identifier, instant, parse_field, utc_millis


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_versions():
    versions = {}
    for name in ("bwp-collector", "paddleocr", "paddlepaddle", "paddlex", "opencv-contrib-python"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def prepare(sample_path: Path, output: Path):
    sample = load_yaml(sample_path)
    validate(sample, SAMPLE_SCHEMA)
    if output.exists():
        raise ValueError("观察目录已存在，请直接 recognize 重跑，避免重新生成 capture_id")
    loaded = {}
    for source in sample["images"]:
        key = source["key"]
        if key in loaded:
            raise ValueError("图片 key 重复")
        path = (sample_path.parent / source["path"]).resolve()
        image = read_image(path)
        if list(image.shape[1::-1]) != source["size"]:
            raise ValueError(f"图片 {key} 分辨率与标注不符，必须重新校准裁剪框")
        loaded[key] = (path, image)
        source["captured_at"] = utc_millis(source["captured_at"])
    seen = set()
    for row in sample["rows"]:
        if row["key"] in seen:
            raise ValueError("行 key 重复")
        seen.add(row["key"])
        for field in row["fields"].values():
            if field["image"] not in loaded:
                raise ValueError("裁剪区域引用了不存在的图片")
            crop(loaded[field["image"]][1], field["box"])
    output.mkdir(parents=True)
    (output / "originals").mkdir()
    sources = []
    for source in sample["images"]:
        source = dict(source)
        path, _ = loaded[source["key"]]
        data = path.read_bytes()
        # Preserve original bytes; extension is not used to determine the decoder.
        target = output / "originals" / (source["key"] + ".image")
        target.write_bytes(data)
        source["path"] = target.relative_to(output).as_posix()
        source["sha256"] = hashlib.sha256(data).hexdigest()
        sources.append(source)
    for row in sample["rows"]:
        row["capture_id"] = str(uuid7())
    session = {**sample, "images": sources}
    write_json(output / "session.json", session)
    return session


def source_images(session, root):
    images = {}
    for source in session["images"]:
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("原图路径不在观察目录中")
        if sha256(path) != source["sha256"]:
            raise ValueError("原图校验失败，文件已被修改")
        images[source["key"]] = read_image(path)
    return images


def context_issues(session, config, engine_name):
    issues = []
    if session["sample_kind"] != "real":
        issues.append("synthetic_sample")
    if engine_name != "paddle":
        issues.append("replay_not_real_ocr")
    if not session["context_confirmed"]:
        issues.append("context_unconfirmed")
    if not config["calibrated"]:
        issues.append("layout_uncalibrated")
    for key in ("scope_key", "season_key"):
        try:
            identifier(session[key], key)
        except ValueError:
            issues.append(key + "_invalid")
    try:
        decimal_string(session["shikigami_id"], "shikigami_id", 4294967295, 1)
    except ValueError:
        issues.append("shikigami_id_invalid")
    return issues


def recognize(root: Path, config: dict, engine):
    validate(config, CONFIG_SCHEMA)
    session = json.loads((root / "session.json").read_text(encoding="utf-8"))
    images = source_images(session, root)
    times = {s["key"]: s["captured_at"] for s in session["images"]}
    run_id = str(uuid7())
    run = root / "runs" / run_id
    run.mkdir(parents=True)
    (run / "crops").mkdir()
    common = context_issues(session, config, engine.name)
    results = []
    overlays = {key: value.copy() for key, value in images.items()}
    for row in session["rows"]:
        issues = list(common)
        values, evidence = {}, {}
        if not row["identity_confirmed"]:
            issues.append("identity_unconfirmed")
        for field in FIELDS:
            spec = row["fields"].get(field)
            if spec is None:
                issues.append(field + ":missing_region")
                continue
            name = row["key"] + "." + field
            raw = crop(images[spec["image"]], spec["box"])
            processed = preprocess(raw, config["preprocess"], config["scale"])
            write_image(run / "crops" / (name + ".raw.png"), raw)
            write_image(run / "crops" / (name + ".ocr.png"), processed)
            tokens = engine.recognize(processed, name)
            evidence[field] = {"source": spec, "tokens": tokens}
            # One tightly cropped field must yield exactly one token. Never join rows.
            if len(tokens) != 1:
                issues.append(field + ":ambiguous_or_empty")
                continue
            if tokens[0]["confidence"] < config["min_confidence"]:
                issues.append(field + ":low_confidence")
                continue
            try:
                values[field] = parse_field(field, tokens[0]["text"])
            except ValueError as exc:
                issues.append(field + ":" + str(exc))
            left, top, right, bottom = spec["box"]
            cv2.rectangle(overlays[spec["image"]], (left, top), (right, bottom), (0, 200, 0), 2)
            cv2.putText(overlays[spec["image"]], name, (left, max(top - 4, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 255), 1)
        fields = row["fields"]
        point_source = fields.get("bailian_points", {}).get("image")
        win_source = fields.get("cumulative_wins", {}).get("image")
        captured_at = times.get(point_source)
        if point_source != win_source:
            issues.append("points_wins_not_same_screenshot")
        if captured_at:
            for field in ("player_id", "grade"):
                if field in fields:
                    delay = abs((instant(times[fields[field]["image"]]) - instant(captured_at)).total_seconds())
                    if delay > config["max_profile_delay_seconds"]:
                        issues.append(field + ":stale_profile")
        results.append({"row_key": row["key"], "capture_id": row["capture_id"],
                        "status": "pending" if issues else "ready", "issues": issues,
                        "values": values, "captured_at": captured_at, "evidence": evidence,
                        "image_keys": sorted({s["image"] for s in fields.values()})})
    # Two rows claiming the same player are not silently merged or exported.
    players = {}
    for row in results:
        player = row["values"].get("player_id")
        if player is not None:
            players.setdefault(player, []).append(row)
    for rows in players.values():
        if len(rows) > 1:
            for row in rows:
                row["status"] = "pending"
                row["issues"].append("duplicate_player_in_page")
    records = []
    for row in results:
        if row["status"] == "ready":
            records.append({"capture_id": row["capture_id"], "shikigami_id": session["shikigami_id"],
                            "season_key": session["season_key"], **row["values"],
                            "captured_at": row["captured_at"], "image_keys": row["image_keys"]})
    report = {"schema_version": "1.0", "run_id": run_id, "engine": engine.name,
              "sample_kind": session["sample_kind"], "config": config,
              "runtime_versions": runtime_versions(),
              "images": [{"key": s["key"], "sha256": s["sha256"]} for s in session["images"]],
              "created_at": utc_millis(datetime.now(timezone.utc).isoformat()),
              "ready_count": len(records), "pending_count": len(results) - len(records), "rows": results}
    write_json(run / "report.json", report)
    if records:
        used = {key for row in records for key in row["image_keys"]}
        payload = {"schema_version": "1.0", "scope_key": session["scope_key"], "records": records,
                   "images": [{"key": s["key"], "sha256": s["sha256"]}
                              for s in session["images"] if s["key"] in used]}
        validate(payload, BATCH_SCHEMA)
        write_json(run / "upload_candidate.json", payload)
    for key, overlay in overlays.items():
        write_image(run / (key + ".regions.png"), overlay)
    return run, report


def evaluate(report: dict, sample: dict):
    validate(sample, SAMPLE_SCHEMA)
    actual = {r["row_key"]: r for r in report["rows"]}
    counts = {field: {"correct": 0, "total": 0} for field in FIELDS}
    mismatches, exact_rows, total_rows = [], 0, 0
    for row in sample["rows"]:
        expected = row.get("expected", {})
        values = actual.get(row["key"], {}).get("values", {})
        for field, value in expected.items():
            counts[field]["total"] += 1
            correct = values.get(field) == value
            counts[field]["correct"] += int(correct)
            if not correct:
                mismatches.append({"row_key": row["key"], "field": field,
                                   "expected": value, "actual": values.get(field)})
        if set(expected) == set(FIELDS):
            total_rows += 1
            exact_rows += int(all(values.get(k) == v for k, v in expected.items()))
    if not any(c["total"] for c in counts.values()):
        raise ValueError("没有人工标注 expected，不能计算准确率")
    for count in counts.values():
        count["accuracy"] = count["correct"] / count["total"] if count["total"] else None
    return {"sample_kind": sample["sample_kind"], "engine": report["engine"], "fields": counts,
            "full_rows": {"correct": exact_rows, "total": total_rows,
                          "accuracy": exact_rows / total_rows if total_rows else None},
            "mismatches": mismatches,
            "note": "单份标注样本的测量结果，不代表真实榜单总体准确率或阶段验收通过。"}
