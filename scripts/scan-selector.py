"""Bounded inventory screenshots of the observed Android shikigami selector."""
import argparse
import json
import subprocess
import time
from datetime import datetime,timezone
from pathlib import Path
import cv2
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('--adb',required=True)
parser.add_argument('--serial',required=True)
args=parser.parse_args()
command=[args.adb,'-s',args.serial]
run=Path('data/selector')/datetime.now(timezone.utc).strftime('scan-%Y%m%dT%H%M%SZ')
run.mkdir(parents=True)
previous=None
for index in range(16):
    activity=subprocess.run(command+['shell','dumpsys','activity','activities'],capture_output=True,check=True).stdout.decode('utf-8',errors='replace')
    if not any('com.netease.yysbwp/' in s for s in activity.splitlines() if 'ResumedActivity' in s):
        raise RuntimeError('Game not foreground')
    raw=subprocess.run(command+['exec-out','screencap','-p'],capture_output=True,check=True).stdout
    picture=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
    if picture is None or picture.shape[:2]!=(1080,1920): raise ValueError('Wrong size')
    (run/f'{index:02d}.png').write_bytes(raw)
    if previous is not None:
        difference=float(np.mean(np.abs(picture[265:885,195:1740].astype(float)-previous[265:885,195:1740].astype(float))))
        if difference<1:
            (run/'scan.json').write_text(json.dumps({'bottom_detected':True,'last_index':index,'swipe':[1800,820,1800,420,800]}),encoding='utf-8')
            print(run,flush=True);break
    previous=picture
    subprocess.run(command+['shell','input','swipe','1800','820','1800','420','800'],check=True)
    time.sleep(.8)
else:
    (run/'scan.json').write_text(json.dumps({'bottom_detected':False,'last_index':15}),encoding='utf-8')
    print(run,flush=True)
