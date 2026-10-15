"""Measure this machine's OCR process; synthetic crops are not game benchmarks."""

import json
import argparse
import os
import threading
import time
from pathlib import Path

import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu-threads", type=int, choices=range(1, 33))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / ".cache" / "paddlex")
    if args.cpu_threads:
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            os.environ[key] = str(args.cpu_threads)
    process = psutil.Process()
    logical = psutil.cpu_count() or 1
    reports = []

    def measure(name, action):
        samples = []
        stop = threading.Event()
        process.cpu_percent()

        def sample():
            while not stop.wait(.1):
                samples.append((process.memory_info().rss, process.cpu_percent() / logical))

        start_mem = process.memory_info().rss
        before = process.cpu_times()
        started = time.perf_counter()
        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        try:
            result = action()
        finally:
            stop.set()
            thread.join()
        elapsed = time.perf_counter() - started
        after = process.cpu_times()
        end_mem = process.memory_info().rss
        cpu_seconds = after.user + after.system - before.user - before.system
        item = {
            "phase": name, "wall_seconds": round(elapsed, 3),
            "cpu_seconds": round(cpu_seconds, 3),
            "cpu_machine_average_percent": round(cpu_seconds / elapsed / logical * 100, 2),
            "cpu_machine_sample_peak_percent": round(max([s[1] for s in samples], default=0), 2),
            "rss_start_mib": round(start_mem / 2**20, 1),
            "rss_end_mib": round(end_mem / 2**20, 1),
            "rss_sample_peak_mib": round(max([start_mem, end_mem] + [s[0] for s in samples]) / 2**20, 1),
        }
        reports.append(item)
        print(json.dumps(item), flush=True)
        return result

    def load():
        from bwp_collector.ocr import PaddleEngine
        from bwp_collector.pipeline import load_yaml
        config = load_yaml(root / "config" / "ocr.yaml")
        # Require cached weights, avoiding downloads during the measured phase.
        for kind, model in (("detection", config["detection_model"]), ("recognition", config["recognition_model"])):
            directory = root / ".cache" / "paddlex" / "official_models" / model
            if not directory.is_dir():
                raise ValueError("请先下载模型，再运行资源测量")
            config[f"text_{kind}_model_dir"] = str(directory)
        if not args.cpu_threads:
            return PaddleEngine(config)
        from paddleocr import PaddleOCR
        from bwp_collector.ocr import normalize_result

        class LimitedEngine:
            def __init__(self):
                self.engine = PaddleOCR(
                    device="cpu", cpu_threads=args.cpu_threads,
                    text_detection_model_name=config["detection_model"],
                    text_recognition_model_name=config["recognition_model"],
                    text_detection_model_dir=config["text_detection_model_dir"],
                    text_recognition_model_dir=config["text_recognition_model_dir"],
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False, text_rec_score_thresh=0.0,
                )

            def recognize(self, image, key):
                return normalize_result(list(self.engine.predict(image))[0])

        return LimitedEngine()

    engine = measure("load_cached_models_and_imports", load)
    from bwp_collector.imaging import read_image
    crop_dirs = sorted((root / "data" / "demo-session" / "runs").glob("*/crops"))
    if not crop_dirs:
        raise ValueError("请先执行 README 中的离线演示")
    images = [read_image(p) for p in sorted(crop_dirs[-1].glob("*.ocr.png"))]
    if not images:
        raise ValueError("没有可测量的裁剪图片")

    def recognize(repeats):
        for _ in range(repeats):
            for image in images:
                engine.recognize(image, "benchmark")

    measure("first_pass_8_fields", lambda: recognize(1))
    measure("warm_24_fields", lambda: recognize(3))
    measure("idle_model_loaded", lambda: time.sleep(3))
    measure("idle_after_settling", lambda: time.sleep(3))
    result = {
        "pid": process.pid, "logical_cpus": logical,
        "cpu_threads_override": args.cpu_threads,
        "ram_gib": round(psutil.virtual_memory().total / 2**30, 2),
        "input": "synthetic demo field crops; not real game screenshots",
        "field_count_per_pass": len(images), "crop_shapes": [list(i.shape) for i in images],
        "cpu_metric": "process CPU seconds / wall seconds / logical CPUs; approximate Task Manager percentage",
        "memory_metric": "process working set (RSS), sampled every 100 ms; excludes game and emulator",
        "phases": reports,
    }
    suffix = f"-{args.cpu_threads}threads" if args.cpu_threads else ""
    output = root / "data" / ("ocr-resource-benchmark" + suffix + ".json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output), flush=True)


if __name__ == "__main__":
    main()
