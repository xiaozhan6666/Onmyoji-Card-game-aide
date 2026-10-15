from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path):
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"不能读取图片：{path}")
    return image


def write_image(path: Path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG 编码失败")
    path.write_bytes(encoded.tobytes())


def crop(image, box):
    if not isinstance(box, list) or len(box) != 4 or any(type(x) is not int for x in box):
        raise ValueError("裁剪框必须是四个整数 [left, top, right, bottom]")
    left, top, right, bottom = box
    height, width = image.shape[:2]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError(f"裁剪框超出图片范围：{box} / {width}x{height}")
    return image[top:bottom, left:right].copy()


def preprocess(image, mode: str, scale: int):
    image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if mode == "color":
        return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if mode == "threshold":
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def grid(image, step=100):
    out = image.copy()
    height, width = out.shape[:2]
    for x in range(0, width, step):
        cv2.line(out, (x, 0), (x, height - 1), (100, 100, 255), 1)
        cv2.putText(out, str(x), (x + 2, 18), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
    for y in range(0, height, step):
        cv2.line(out, (0, y), (width - 1, y), (100, 100, 255), 1)
        cv2.putText(out, str(y), (2, y + 15), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
    return out
