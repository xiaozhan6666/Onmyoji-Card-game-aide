"""PaddleOCR 3.x adapter; replay exists only for deterministic parser tests."""

import json
import math
import os
from pathlib import Path


def normalize_result(result):
    data = result.json if hasattr(result, "json") else result
    if isinstance(data, str):
        data = json.loads(data)
    data = data.get("res", data)
    texts = data["rec_texts"]
    scores = data["rec_scores"]
    boxes = data["rec_boxes"]
    if not len(texts) == len(scores) == len(boxes):
        raise ValueError("OCR 返回的文字、置信度和位置数量不一致")
    tokens = []
    for text, score, box in zip(texts, scores, boxes):
        score = float(score)
        if not isinstance(text, str) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("OCR 返回了非法文字或置信度")
        tokens.append({"text": text, "confidence": score, "box": [int(v) for v in box]})
    return tokens


class PaddleEngine:
    name = "paddle"

    def __init__(self, config):
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(Path.cwd() / ".cache" / "paddlex"))
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ValueError('未安装 OCR 依赖，请执行 python -m pip install -e ".[ocr]"') from exc
        self.options = {
            "device": "cpu",
            "cpu_threads": 2,
            "text_detection_model_name": config["detection_model"],
            "text_recognition_model_name": config["recognition_model"],
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "text_rec_score_thresh": 0.0,
        }
        for key in ("text_detection_model_dir", "text_recognition_model_dir"):
            if config.get(key):
                self.options[key] = config[key]
        self.engine = PaddleOCR(**self.options)

    def recognize(self, image, key):
        pages = list(self.engine.predict(image))
        if len(pages) != 1:
            raise ValueError("单个裁剪区域必须返回一页 OCR 结果")
        return normalize_result(pages[0])


class ReplayEngine:
    name = "replay"

    def __init__(self, path: Path):
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def recognize(self, image, key):
        if key not in self.data:
            raise ValueError(f"回放缺少字段：{key}")
        return normalize_result(self.data[key])
