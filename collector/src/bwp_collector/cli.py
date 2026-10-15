import argparse
import json
import sys
from pathlib import Path

from .contracts import BATCH_SCHEMA, CONFIG_SCHEMA, SAMPLE_SCHEMA, validate
from .imaging import grid, read_image, write_image
from .ocr import PaddleEngine, ReplayEngine
from .pipeline import evaluate, load_yaml, prepare, recognize, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="百闻牌离线截图识别（阶段 1、2）")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="显示尺寸并生成坐标网格图")
    inspect.add_argument("image", type=Path)
    inspect.add_argument("--output", type=Path, required=True)
    prep = commands.add_parser("prepare", help="保存原图、标注和稳定 UUIDv7")
    prep.add_argument("sample", type=Path)
    prep.add_argument("--output", type=Path, required=True)
    ocr = commands.add_parser("recognize", help="裁剪并离线识别，保存每次运行的诊断信息")
    ocr.add_argument("session", type=Path)
    ocr.add_argument("--config", type=Path, default=Path("config/ocr.yaml"))
    ocr.add_argument("--engine", choices=["paddle", "replay"], default="paddle")
    ocr.add_argument("--replay", type=Path)
    ev = commands.add_parser("evaluate", help="对照人工标注统计字段及整行准确率")
    ev.add_argument("report", type=Path)
    ev.add_argument("--labels", type=Path, required=True)
    ev.add_argument("--output", type=Path, required=True)
    schemas = commands.add_parser("schemas", help="导出 JSON Schema 给后续 Java 工程使用")
    schemas.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            if args.output.exists() or args.output.resolve() == args.image.resolve():
                raise ValueError("网格图输出位置已存在，请选择新文件，避免覆盖原图")
            image = read_image(args.image)
            write_image(args.output, grid(image))
            print(json.dumps({"width": image.shape[1], "height": image.shape[0], "grid": str(args.output)}))
        elif args.command == "prepare":
            session = prepare(args.sample, args.output)
            print(f"已保存 {len(session['rows'])} 行观察：{args.output / 'session.json'}")
        elif args.command == "recognize":
            config = load_yaml(args.config)
            validate(config, CONFIG_SCHEMA)
            if args.engine == "replay" and args.replay is None:
                raise ValueError("replay 模式必须指定 --replay 文件")
            engine = PaddleEngine(config) if args.engine == "paddle" else ReplayEngine(args.replay)
            run, report = recognize(args.session, config, engine)
            print(json.dumps({"report": str(run / "report.json"), "ready": report["ready_count"],
                              "pending": report["pending_count"]}, ensure_ascii=False))
        elif args.command == "evaluate":
            if args.output.exists():
                raise ValueError("评估输出文件已存在，请使用新路径")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            result = evaluate(report, load_yaml(args.labels))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, result)
            print(json.dumps(result, ensure_ascii=False))
        elif args.command == "schemas":
            args.output.mkdir(parents=True, exist_ok=True)
            for name, schema in [("sample", SAMPLE_SCHEMA), ("batch", BATCH_SCHEMA), ("ocr-config", CONFIG_SCHEMA)]:
                write_json(args.output / (name + ".schema.json"), schema)
            print(f"已导出协议：{args.output}")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
