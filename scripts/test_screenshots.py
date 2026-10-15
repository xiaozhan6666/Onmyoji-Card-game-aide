"""Evaluate manually labelled game screenshots; never create upload observations."""

import json
import os
import time
from datetime import datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / ".cache" / "paddlex")
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[key] = "2"
    from paddleocr import PaddleOCR
    from bwp_collector.imaging import crop, preprocess, read_image, write_image
    from bwp_collector.ocr import normalize_result
    from bwp_collector.validation import parse_field
    import cv2

    base = root / "data" / "screenshots-test"
    labels = json.loads((base / "labels.json").read_text(encoding="utf-8"))
    run = base / datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run.mkdir()
    started = time.perf_counter()
    models = root / ".cache" / "paddlex" / "official_models"
    engine = PaddleOCR(
        device="cpu", cpu_threads=2,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        text_detection_model_dir=str(models / "PP-OCRv5_mobile_det"),
        text_recognition_model_dir=str(models / "PP-OCRv5_mobile_rec"),
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, text_rec_score_thresh=0.0,
    )
    load_seconds = time.perf_counter() - started
    results = []
    for filename, truth in labels.items():
        image = read_image(root / "data" / "screenshots" / filename)
        height, width = image.shape[:2]
        if (width, height) not in ((1920, 864), (1280, 576)):
            raise ValueError("该测试布局仅适用于已核对的两种尺寸")
        factor = width / 1920
        out = run / Path(filename).stem
        out.mkdir()
        overlay = image.copy()
        rows = []
        image_started = time.perf_counter()
        # Pixel positions calibrated from these four images, not universal layouts.
        for row_index, expected_pair in enumerate(truth["rows"] + [truth["self"]]):
            center_y = [227, 330, 431, 533, 635, 705][row_index]
            row = {"kind": "ranking" if row_index < 5 else "self", "rank": row_index + 1 if row_index < 5 else None,
                   "fields": {}}
            for field, left, right, expected in zip(
                    ("bailian_points", "cumulative_wins"), (1080, 1415), (1175, 1510), expected_pair):
                box = [round(v * factor) for v in (left, center_y - 25, right, center_y + 25)]
                raw = crop(image, box)
                processed = preprocess(raw, "color", 2)
                key = f"row-{row_index + 1}.{field}"
                write_image(out / (key + ".raw.png"), raw)
                write_image(out / (key + ".ocr.png"), processed)
                tokens = normalize_result(list(engine.predict(processed))[0])
                value, reason = None, None
                if len(tokens) != 1:
                    reason = "ambiguous_or_empty"
                elif tokens[0]["confidence"] < .95:
                    reason = "low_confidence"
                else:
                    try:
                        value = parse_field(field, tokens[0]["text"])
                    except ValueError as exc:
                        reason = str(exc)
                row["fields"][field] = {"box": box, "tokens": tokens, "expected": expected,
                                        "parsed": value, "correct": value == expected, "reason": reason}
                left_px, top, right_px, bottom = box
                color = (0, 200, 0) if value == expected else (0, 0, 255)
                cv2.rectangle(overlay, (left_px, top), (right_px, bottom), color, 2)
                cv2.putText(overlay, str(row_index + 1) if row_index < 5 else "SELF", (left_px, top - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
            rows.append(row)
        # Supplementary title probe, not scored without a human-confirmed label.
        box = [round(v * factor) for v in (272, 484, 395, 522)]
        title = preprocess(crop(image, box), "color", 3)
        write_image(out / "shikigami-title.png", title)
        title_tokens = normalize_result(list(engine.predict(title))[0])
        write_image(out / "regions.png", overlay)
        result = {"filename": filename, "size": [width, height], "rows": rows,
                  "title_ocr_unscored": title_tokens, "seconds": round(time.perf_counter() - image_started, 3)}
        results.append(result)
        print(json.dumps({"filename": filename, "correct": sum(f["correct"] for r in rows for f in r["fields"].values()),
                          "fields": 12, "title": title_tokens, "seconds": result["seconds"]}, ensure_ascii=False), flush=True)
    summary = {}
    for kind in ("ranking", "self"):
        rows = [row for image in results for row in image["rows"] if row["kind"] == kind]
        fields = [field for row in rows for field in row["fields"].values()]
        summary[kind] = {"correct_fields": sum(f["correct"] for f in fields), "total_fields": len(fields),
                         "correct_rows": sum(all(f["correct"] for f in r["fields"].values()) for r in rows), "total_rows": len(rows)}
    report = {"input_type": "real screenshots; one page has two resolution variants", "cpu_threads": 2,
              "confidence_threshold": .95, "load_seconds_excluding_imports": round(load_seconds, 3),
              "summary": summary, "images": results,
              "limitations": ["ROI calibrated on these same images; this is not an independent validation set",
                              "No player ID, grade or verified capture timestamp; no upload payload created",
                              "Bottom self row excluded from leaderboard row metrics"]}
    (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "report": str(run / "report.json")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
