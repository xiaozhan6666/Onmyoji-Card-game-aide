"""Import manually identified, full-color game portraits without recoloring them.

Sources and pixel bounds are reviewed in config/portraits.json. A color check is
only a rejection heuristic, not character identification or proof of authenticity.
All entries must pass before any existing web asset is overwritten.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def checked_box(value, size):
    if not isinstance(value, list) or len(value) != 4 or not all(type(n) is int for n in value):
        raise ValueError('裁剪坐标必须是四个整数')
    left, top, right, bottom = value
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError('裁剪坐标超出图片边界')
    return tuple(value)


def prepare(entries):
    prepared = {}
    for item in entries:
        identifier = item['id']
        if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isdecimal() or identifier in prepared:
            raise ValueError('式神 ID 必须是唯一的数字字符串')
        source = (ROOT / item['source']).resolve()
        if not source.is_relative_to(ROOT / 'data'):
            raise ValueError('头像来源必须位于项目 data 目录')
        with Image.open(source) as original:
            portrait = original.convert('RGBA').crop(checked_box(item['box'], original.size))
        # Inspect the character interior, not the colorful frame surrounding it.
        sample = portrait.crop(checked_box(item['color_sample'], portrait.size))
        pixels = np.asarray(sample, dtype=np.int16)
        visible = pixels[:, :, 3] >= 240
        if not np.any(visible):
            raise ValueError(f"{item['name']}：色彩检查区域没有足够不透明的像素")
        color_fraction = float(np.mean(np.ptp(pixels[:, :, :3][visible], axis=1) > 20))
        if color_fraction < 0.08:
            raise ValueError(f"{item['name']}：疑似灰度或低色彩素材（{color_fraction:.1%}），保留现有头像，请人工检查来源")
        output = io.BytesIO()
        portrait.save(output, format='PNG')
        prepared[identifier] = (output.getvalue(), item['name'], color_fraction)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只检查，不更新素材')
    args = parser.parse_args()
    entries = json.loads((ROOT / 'config/portraits.json').read_text(encoding='utf-8'))['portraits']
    try:
        prepared = prepare(entries)
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error)) from error
    assets = {}
    for identifier, (raw, name, fraction) in prepared.items():
        digest = hashlib.sha256(raw).hexdigest()[:12]
        assets[identifier] = f'/portraits/{identifier}.png?v={digest}'
        if not args.check:
            destination = ROOT / 'frontend/public/portraits' / f'{identifier}.png'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        print(f'{identifier} {name}: color={fraction:.1%}, sha256={digest}')
    if not args.check:
        (ROOT / 'frontend/src/portrait-assets.json').write_text(
            json.dumps(assets, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
