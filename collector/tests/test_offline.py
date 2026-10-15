import copy
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest
import yaml

from bwp_collector.contracts import BATCH_SCHEMA, validate
from bwp_collector.imaging import crop, read_image, write_image
from bwp_collector.ocr import normalize_result
from bwp_collector.pipeline import evaluate, prepare, recognize
from bwp_collector.validation import LONG_MAX, parse_field, utc_millis


@pytest.mark.parametrize("text,want", [("1,840", "1840"), ("３２００", "3200"), ("0", "0"), ("0009", "9")])
def test_numeric_normalization(text, want):
    assert parse_field("bailian_points", text) == want


@pytest.mark.parametrize("text", ["1,84", "18O0", "1.8万", "-6", "1 840", "", str(LONG_MAX + 1)])
def test_ambiguous_number_never_guessed(text):
    with pytest.raises(ValueError):
        parse_field("bailian_points", text)


def test_identity_and_grade():
    assert parse_field("player_id", "000123") == "000123"
    assert parse_field("grade", "大名士") == 10
    with pytest.raises(ValueError):
        parse_field("grade", "未知")
    with pytest.raises(ValueError):
        parse_field("player_id", " 123")


def test_time_requires_timezone_and_truncates_milliseconds():
    assert utc_millis("2026-10-13T20:00:00.123999+08:00") == "2026-10-13T12:00:00.123Z"
    with pytest.raises(ValueError):
        utc_millis("2026-10-13T20:00:00")


def test_crop_rejects_wrong_resolution_and_handles_chinese_path(tmp_path):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    path = tmp_path / "中文截图.png"
    write_image(path, image)
    assert read_image(path).shape == image.shape
    with pytest.raises(ValueError):
        crop(image, [0, 0, 201, 100])


class FakePaddle:
    # Test double for export validation, not evidence of OCR model accuracy.
    name = "paddle"

    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def recognize(self, image, key):
        field = key.split(".")[1]
        text = {"player_id": "000123", "grade": "五段", "bailian_points": "1,840", "cumulative_wins": "100"}[field]
        return self.overrides.get(key, [{"text": text, "confidence": .99, "box": [0, 0, 50, 20]}])


@pytest.fixture
def fixture(tmp_path):
    write_image(tmp_path / "board.png", np.full((100, 400, 3), 255, dtype=np.uint8))
    sample = {"schema_version": "1.0", "sample_kind": "real", "context_confirmed": True,
              "scope_key": "test-scope", "season_key": "test-season", "shikigami_id": "1",
              "images": [{"key": "board", "path": "board.png", "size": [400, 100],
                          "captured_at": "2026-10-13T20:00:00+08:00"}],
              "rows": [{"key": "row-001", "identity_confirmed": True,
                        "fields": {f: {"image": "board", "box": [i*100, 0, i*100+100, 100]}
                                   for i, f in enumerate(("player_id", "grade", "bailian_points", "cumulative_wins"))},
                        "expected": {"player_id": "000123", "grade": 5, "bailian_points": "1840", "cumulative_wins": "100"}}]}
    config = {"schema_version": "1.0", "calibrated": True, "min_confidence": .95,
              "max_profile_delay_seconds": 30, "preprocess": "color", "scale": 1,
              "detection_model": "test", "recognition_model": "test"}
    return tmp_path, sample, config


def save_prepare(tmp_path, sample):
    path = tmp_path / "sample.yaml"
    path.write_text(yaml.safe_dump(sample), encoding="utf-8")
    root = tmp_path / "observation"
    prepare(path, root)
    return root


def test_rerun_preserves_capture_id_and_payload(fixture):
    tmp, sample, config = fixture
    root = save_prepare(tmp, sample)
    first, report = recognize(root, config, FakePaddle())
    second, again = recognize(root, config, FakePaddle())
    assert first != second
    assert report["rows"][0]["capture_id"] == again["rows"][0]["capture_id"]
    assert UUID(report["rows"][0]["capture_id"]).version == 7
    assert report["ready_count"] == 1
    payload = json.loads((first / "upload_candidate.json").read_text())
    validate(payload, BATCH_SCHEMA)
    assert payload["records"][0]["player_id"] == "000123"
    with pytest.raises(ValueError, match="观察目录已存在"):
        prepare(tmp / "sample.yaml", root)


@pytest.mark.parametrize("case", ["synthetic", "uncalibrated", "identity", "context", "missing", "low", "multiple", "season", "overflow", "replay"])
def test_uncertainty_never_exports(fixture, case):
    tmp, sample, config = fixture
    overrides = {}
    engine = FakePaddle(overrides)
    if case == "synthetic": sample["sample_kind"] = "synthetic"
    if case == "uncalibrated": config["calibrated"] = False
    if case == "identity": sample["rows"][0]["identity_confirmed"] = False
    if case == "context": sample["context_confirmed"] = False
    if case == "missing": del sample["rows"][0]["fields"]["player_id"]
    if case == "season": sample["season_key"] = None
    if case == "replay": engine.name = "replay"
    if case in ("low", "multiple", "overflow"):
        token = {"text": str(LONG_MAX + 1) if case == "overflow" else "1840", "confidence": .4 if case == "low" else .99, "box": [0, 0, 40, 20]}
        engine.overrides["row-001.bailian_points"] = [token] * (2 if case == "multiple" else 1)
    root = save_prepare(tmp, sample)
    run, report = recognize(root, config, engine)
    assert report["ready_count"] == 0
    assert report["pending_count"] == 1
    assert not (run / "upload_candidate.json").exists()


def test_stale_profile_and_different_score_screenshots(fixture):
    tmp, sample, config = fixture
    sample["images"].append({**sample["images"][0], "key": "profile", "captured_at": "2026-10-13T20:01:00+08:00"})
    sample["rows"][0]["fields"]["grade"]["image"] = "profile"
    sample["rows"][0]["fields"]["cumulative_wins"]["image"] = "profile"
    root = save_prepare(tmp, sample)
    _, report = recognize(root, config, FakePaddle())
    assert "grade:stale_profile" in report["rows"][0]["issues"]
    assert "points_wins_not_same_screenshot" in report["rows"][0]["issues"]


def test_duplicate_players_block_both_rows(fixture):
    tmp, sample, config = fixture
    second = copy.deepcopy(sample["rows"][0])
    second["key"] = "row-002"
    sample["rows"].append(second)
    root = save_prepare(tmp, sample)
    _, report = recognize(root, config, FakePaddle())
    assert report["pending_count"] == 2
    assert all("duplicate_player_in_page" in row["issues"] for row in report["rows"])


def test_tampered_original_rejected(fixture):
    tmp, sample, config = fixture
    root = save_prepare(tmp, sample)
    (root / "originals" / "board.image").write_bytes(b"changed")
    with pytest.raises(ValueError, match="原图校验失败"):
        recognize(root, config, FakePaddle())


def test_missing_prediction_counts_as_error(fixture):
    _, sample, _ = fixture
    result = evaluate({"engine": "replay", "rows": []}, sample)
    assert result["fields"]["player_id"]["total"] == 1
    assert result["fields"]["player_id"]["accuracy"] == 0
    assert result["full_rows"]["accuracy"] == 0


def test_paddle_result_adapter():
    result = {"res": {"rec_texts": ["1840"], "rec_scores": [.99], "rec_boxes": [[1, 2, 3, 4]]}}
    assert normalize_result(result)[0]["text"] == "1840"
    result["res"]["rec_scores"] = [float("nan")]
    with pytest.raises(ValueError):
        normalize_result(result)
