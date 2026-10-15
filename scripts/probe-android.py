"""One Android-device action followed by a timestamped screenshot for manual calibration.

This is a development probe, not an unattended collector. Coordinates must come
from the most recently inspected screenshot of this device.
"""
import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--package', default='com.netease.yysbwp')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--tap', type=int, nargs=2)
    actions.add_argument('--swipe', type=int, nargs=5, metavar=('X1','Y1','X2','Y2','MS'))
    parser.add_argument('--output', type=Path, default=Path('data/live-probe'))
    args = parser.parse_args()
    command = [args.adb, '-s', args.serial]
    activity = subprocess.run(command + ['shell', 'dumpsys', 'activity', 'activities'],
                              capture_output=True, check=True, timeout=15).stdout.decode('utf-8', errors='replace')
    resumed = [line for line in activity.splitlines() if 'ResumedActivity' in line]
    if not any(args.package + '/' in line for line in resumed):
        raise RuntimeError('Expected game is not the resumed Android application; no input sent.')
    if args.tap:
        subprocess.run(command + ['shell', 'input', 'tap', *map(str, args.tap)], check=True, timeout=10)
        time.sleep(0.8)
    if args.swipe:
        subprocess.run(command + ['shell', 'input', 'swipe', *map(str, args.swipe)], check=True, timeout=10)
        time.sleep(0.8)
    started = datetime.now(timezone.utc)
    raw = subprocess.run(command + ['exec-out', 'screencap', '-p'],
                         capture_output=True, check=True, timeout=15).stdout
    completed = datetime.now(timezone.utc)
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Device did not return a PNG screenshot')
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / ('state-' + started.strftime('%Y%m%dT%H%M%S%fZ') + '.png')
    path.write_bytes(raw)
    path.with_suffix('.json').write_text(json.dumps({
        'capture_started_at': started.isoformat(), 'capture_completed_at': completed.isoformat(),
        'serial': args.serial, 'package': args.package, 'tap': args.tap, 'swipe': args.swipe,
        'purpose': 'manual_calibration', 'uploadable': False,
    }, indent=2), encoding='utf-8')
    print(path.resolve())


if __name__ == '__main__':
    main()
