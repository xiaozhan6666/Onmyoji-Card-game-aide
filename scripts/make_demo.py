"""Generate labelled synthetic fixtures. These are never real game observations."""

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont


def make_demo(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        raise ValueError("示例生成需要微软雅黑字体；可改为本机支持中文的字体路径")
    font = ImageFont.truetype(str(font_path), 28)
    image = Image.new("RGB", (1000, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 10), "SYNTHETIC TEST / 非游戏截图", font=font, fill="black")
    sample = {"schema_version": "1.0", "sample_kind": "synthetic", "context_confirmed": True,
              "scope_key": "demo-only", "season_key": "demo-season", "shikigami_id": "1",
              "images": [{"key": "board", "path": "board.png", "size": [1000, 260],
                          "captured_at": "2026-10-13T20:00:00.123456+08:00"}], "rows": []}
    replay = {}
    for number, values in enumerate([("000123", "五段", "1,840", "100"),
                                     ("000456", "大名士", "3,200", "250")], start=1):
        row = {"key": f"row-{number:03d}", "identity_confirmed": True, "fields": {},
               "expected": {"player_id": values[0], "grade": 5 if number == 1 else 10,
                            "bailian_points": values[2].replace(",", ""), "cumulative_wins": values[3]}}
        for index, (field, text) in enumerate(zip(row["expected"], values)):
            x, y = 20 + index * 240, 80 + (number - 1) * 80
            draw.text((x + 8, y + 5), text, font=font, fill="black")
            row["fields"][field] = {"image": "board", "box": [x, y, x + 220, y + 60]}
            replay[row["key"] + "." + field] = {"rec_texts": [text], "rec_scores": [.99],
                                                  "rec_boxes": [[0, 0, 200, 50]]}
        sample["rows"].append(row)
    image.save(output / "board.png")
    (output / "sample.yaml").write_text(yaml.safe_dump(sample, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (output / "replay.json").write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/demo-input"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("输出目录已存在，请使用新路径")
    make_demo(args.output)
