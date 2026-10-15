"""Supervised, bounded first-50 capture in the reviewed name-sorted selector.

Each completed character is uploaded immediately; resume reuses saved reports
and outbox receipts. Unknown UI or failed evidence stops without guessing.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['PADDLE_PDX_CACHE_HOME'] = str(ROOT / '.cache/paddlex')
for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
    os.environ[key] = '2'
sys.stdout.reconfigure(encoding='utf-8')


def registry(names):
    """Register exact reviewed names in the existing local-development database."""
    settings = json.loads((ROOT / 'data/backend-local/connection.json').read_text(encoding='utf-8-sig'))
    mysql = next((ROOT / '.cache/toolchains/mysql84').glob('*/bin/mysql.exe'))
    env = os.environ.copy(); env['MYSQL_PWD'] = settings['dev_password']
    command = [str(mysql), '--no-defaults', '--protocol=TCP', '-h127.0.0.1',
               f"-P{settings['port']}", '-ubwp_dev', '--default-character-set=utf8mb4', '-N', '-B', 'bwp_aide']
    def query(sql):
        response = subprocess.run(command, input=sql.encode('utf-8'), capture_output=True, env=env, timeout=20)
        if response.returncode: raise RuntimeError('Local catalog query failed; credentials suppressed')
        return response.stdout.decode('utf-8').strip()
    scope = query("SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA='bwp_aide' AND TABLE_NAME='shikigami';")
    if scope != 'bwp_scope:local-development': raise ValueError('Unexpected database scope')
    sql = ['START TRANSACTION;']
    for name in names:
        literal = "CONVERT(0x" + name.encode('utf-8').hex() + " USING utf8mb4)"
        sql.append(f'INSERT INTO shikigami(name) SELECT {literal} WHERE NOT EXISTS (SELECT 1 FROM shikigami WHERE BINARY name=BINARY {literal});')
    sql.append('COMMIT;')
    query('\n'.join(sql))
    with urlopen('http://127.0.0.1:18080/api/shikigami', timeout=10) as response: catalog = json.load(response)
    result = {}
    for name in names:
        matches = [str(item['id']) for item in catalog if item['name'] == name]
        if len(matches) != 1: raise ValueError('Missing or ambiguous catalog name: ' + name)
        result[name] = matches[0]
    return result, settings['collector_token']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--max-new', type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.max_new <= 50: raise ValueError('Bound must be 1..50')
    import cv2
    import numpy as np
    import msvcrt
    from bwp_collector.imaging import read_image, crop, preprocess
    from bwp_collector.ocr import PaddleEngine
    from bwp_collector.live_upload import prepare, send, write_json

    config = json.loads((ROOT / 'config/capture-first50.json').read_text(encoding='utf-8'))
    names = config['names']
    if len(names) != 50 or len(set(names)) != 50: raise ValueError('Expected fifty unique reviewed names')
    fingerprint = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    batch = args.batch.resolve()
    if not batch.is_relative_to(ROOT / 'data/live-capture'): raise ValueError('Batch path outside capture directory')
    batch.mkdir(parents=True, exist_ok=True)
    state_path = batch / 'progress.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'config_sha256': fingerprint, 'season': config['season'], 'status': 'prepared',
        'started_at': datetime.now(timezone.utc).isoformat(),
        'items': [{'index': i + 1, 'name': name, 'status': 'pending', 'attempts': []} for i, name in enumerate(names)]}
    if state['config_sha256'] != fingerprint:
        previous_config={**config,'rows_per_shikigami':10}
        previous_fingerprint=hashlib.sha256(json.dumps(previous_config,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if config['rows_per_shikigami']!=5 or state['config_sha256']!=previous_fingerprint:
            raise ValueError('Batch configuration changed; cannot resume')
        state.setdefault('scope_changes',[]).append({'at':datetime.now(timezone.utc).isoformat(),
            'from_rows':10,'to_rows':5,'reason':'User reduced future captures to top five; existing records retained'})
        state['config_sha256']=fingerprint
    state['rows_per_shikigami']=config['rows_per_shikigami']
    command = [args.adb, '-s', args.serial]
    selector_reference = [read_image(ROOT / p) for p in config['selector_references']]
    first_board = read_image(ROOT / config['first_board_reference'])
    def save():
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        state['completed'] = sum(i['status'] == 'uploaded' for i in state['items'])
        write_json(state_path, state)
    def foreground():
        output = subprocess.run(command + ['shell', 'dumpsys', 'activity', 'activities'], capture_output=True, check=True, timeout=10).stdout.decode('utf-8', errors='replace')
        if not any('com.netease.yysbwp/' in line for line in output.splitlines() if 'ResumedActivity' in line):
            raise RuntimeError('Game is not foreground')
    def screenshot(label):
        foreground()
        raw = subprocess.run(command + ['exec-out', 'screencap', '-p'], capture_output=True, check=True, timeout=10).stdout
        picture = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if picture is None or picture.shape[:2] != (1080, 1920): raise ValueError('Unexpected game resolution')
        path = batch / (datetime.now(timezone.utc).strftime('%H%M%S%f-') + label + '.png')
        path.write_bytes(raw)
        return picture, path
    def action(kind, *coordinates):
        foreground()
        subprocess.run(command + ['shell', 'input', kind, *map(str, coordinates)], check=True, timeout=10)
        time.sleep(.8)
    def difference(a, b, box):
        l,t,r,bottom = box
        return float(np.mean(np.abs(a[t:bottom,l:r].astype(float) - b[t:bottom,l:r].astype(float))))
    def is_selector(picture):
        return (difference(picture, selector_reference[0], [815,58,1105,115]) < 12
                and difference(picture, selector_reference[0], [1054,996,1178,1044]) < 12)
    def is_board(picture):
        return difference(picture, first_board, [1050,165,1670,222]) < 8
    def template(index):
        column = index % 10
        left = round(197 + column * 155.5)
        if index < 30:
            source = selector_reference[0]; top = 289 + (index // 10) * 201
        else:
            source = selector_reference[1]; top = 409 + ((index - 30) // 10) * 201
        return source[top + 6:top + 105, left + 6:left + 134]
    def locate(picture, index):
        needle = template(index)
        haystack = picture[180:880,195:1742]
        matches = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x,y) = cv2.minMaxLoc(matches)
        if score < .97: return None
        return (195+x+needle.shape[1]//2, 180+y+needle.shape[0]//2, float(score))
    def normalized(text): return ''.join(text.split()).replace('・','·').replace('•','·')
    def board_identity(picture,index):
        # Verify the actual artwork as well as the selector click. Use a central
        # patch, excluding the diamond frame and effects; allow only a narrow
        # scale range observed between selector portraits and leaderboard icons.
        needle=template(index)[24:79,36:91]
        area=picture[466:595,113:250]
        best=0.0
        for scale in np.arange(.7,1.21,.005):
            resized=cv2.resize(needle,None,fx=scale,fy=scale)
            _,score,_,_=cv2.minMaxLoc(cv2.matchTemplate(area,resized,cv2.TM_CCOEFF_NORMED))
            best=max(best,float(score))
        state['items'][index]['board_portrait_score']=best
        return best>=.96
    def title(picture):
        tokens = engine.recognize(preprocess(crop(picture,[90,596,278,656]),'color',2),'batch-title')
        if not tokens or any(t['confidence'] < .85 for t in tokens): return None
        tokens.sort(key=lambda t:(t['box'][1]//25,t['box'][0]))
        return normalized(''.join(t['text'] for t in tokens))
    def select(index,allow_reload=True):
        picture, path = screenshot('navigation')
        if not is_board(picture) and not is_selector(picture):
            # A failed row may leave its verified profile card open. Only close
            # an explicitly identified profile; never tap through unknown popups.
            from bwp_collector.live_profile import profile_anchor
            band=engine.recognize(preprocess(crop(picture,[1280,250,1444,950]),'color',2),'recovery-id')
            _, top=profile_anchor(band)
            buttons=engine.recognize(preprocess(crop(picture,[780,top+216,1395,top+300]),'color',2),'recovery-buttons')
            if '查看信息' not in {t['text'] for t in buttons if t['confidence']>=.95}:
                raise ValueError('Unknown popup; no recovery input sent')
            action('tap',460,198)
            picture,path=screenshot('profile-dismissed')
            if not is_board(picture): raise ValueError('Profile dismissal did not reveal board')
        if is_board(picture) and board_identity(picture,index):
            # Re-selecting the current character can leave the game's list empty.
            # Restore its existing board to rank one instead.
            for _ in range(4):
                if difference(picture,first_board,[368,245,474,815])<=8: return path
                action('swipe',1350,350,1350,780,800)
                picture,path=screenshot('board-return-top')
                if not is_board(picture) or not board_identity(picture,index):
                    raise ValueError('Board changed while returning to first rank')
            if allow_reload:
                # The game can clear a list when its current character is
                # selected again. One verified switch away/back reloads it.
                action('tap',180,450)
                select((index+1)%len(names),allow_reload=False)
                return select(index,allow_reload=False)
            raise ValueError('Current board did not return to rank one')
        if is_board(picture):
            action('tap', 180, 450)
            picture, path = screenshot('selector')
        if not is_selector(picture): raise ValueError('Unknown UI; expected name-sorted selector or uncovered board')
        for attempt in range(5):
            match = locate(picture, index)
            if match:
                x,y,score = match
                state['items'][index]['selection'] = {'screenshot':str(path.relative_to(batch)), 'template_match':score, 'tap':[x,y]}
                save(); action('tap',x,y)
                for _ in range(15):
                    picture, path = screenshot('selected-board')
                    if (is_board(picture)
                            and difference(picture,first_board,[368,245,474,815]) <= 8
                            and board_identity(picture,index)):
                        state['items'][index]['board_title_ocr']=title(picture)
                        save()
                        return path
                    time.sleep(.5)
                raise ValueError('Selected board title did not match reviewed name: ' + names[index])
            # This bounded run only uses the first five grid rows. Reset upward
            # before searching the second page, keeping every tap image-verified.
            if attempt < 2: action('swipe',1800,320,1800,850,800)
            else: action('swipe',1800,820,1800,420,800)
            picture, path = screenshot('selector-scroll')
            if not is_selector(picture): raise ValueError('Selector changed during scroll')
        raise ValueError('Reviewed portrait not found: ' + names[index])

    lock_path = ROOT / 'data/live-capture' / (hashlib.sha256(args.serial.encode()).hexdigest()[:16] + '.lock')
    with lock_path.open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1): lock.write(b'0'); lock.flush()
        lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        ids, token = registry(names)
        models = ROOT / '.cache/paddlex/official_models'
        engine = PaddleEngine({'detection_model':'PP-OCRv5_mobile_det','recognition_model':'PP-OCRv5_mobile_rec',
            'text_detection_model_dir':str(models/'PP-OCRv5_mobile_det'),'text_recognition_model_dir':str(models/'PP-OCRv5_mobile_rec')})
        spec = importlib.util.spec_from_file_location('live_page',ROOT / 'scripts/capture-live-page.py')
        live = importlib.util.module_from_spec(spec); spec.loader.exec_module(live)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        new = 0
        try:
            state['status'] = 'running'; state.pop('error',None); save()
            for index, item in enumerate(state['items']):
                if item['status'] == 'uploaded': continue
                if (batch/'stop.request').exists(): break
                if new >= args.max_new: break
                item['shikigami_id'] = ids[item['name']]
                report = batch / item['report'] if item.get('report') else None
                if not report or not report.exists() or not json.loads(report.read_text(encoding='utf-8')).get('complete'):
                    item['status'] = 'selecting'; save()
                    reference = select(index)
                    run = batch / f"{index+1:02d}-attempt-{len(item['attempts'])+1}"
                    item['attempts'].append(str(run.relative_to(batch)))
                    item['report'] = str((run/'report.json').relative_to(batch)); item['status'] = 'capturing'; save()
                    print(json.dumps({'event':'start','index':index+1,'name':item['name']},ensure_ascii=False),flush=True)
                    report = live.main(['--adb',args.adb,'--serial',args.serial,'--shikigami-name',item['name'],
                        '--shikigami-id',item['shikigami_id'],'--season',config['season'],'--rows',str(config['rows_per_shikigami']),
                        '--first-page-reference',str(ROOT/config['first_board_reference']),
                        '--selected-board-reference',str(reference),'--run-dir',str(run)],engine=engine,lock_held=True)
                item['status'] = 'uploading'; save()
                outbox = prepare(report)
                results = send(outbox,token)
                captured_rows=json.loads(report.read_text(encoding='utf-8'))['requested_rows']
                if len(results) != captured_rows or any(r['status'] not in {'saved','duplicate'} for r in results):
                    raise RuntimeError('Upload incomplete; resume original outbox')
                write_json(outbox/'summary.json',{'acknowledged':captured_rows,'requested':captured_rows,'results':results,'complete':True})
                item['status'] = 'uploaded'; item['captured_rows']=captured_rows
                item['uploaded_at'] = datetime.now(timezone.utc).isoformat(); new += 1; save()
                print(json.dumps({'event':'uploaded','index':index+1,'name':item['name'],'completed':state['completed'],'target':50},ensure_ascii=False),flush=True)
            state['status'] = 'complete' if state['completed'] == 50 else 'checkpoint'; save()
        except Exception as exc:
            state['status'] = 'needs_review'; state['error'] = str(exc); save()
            raise
        finally:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print(str(state_path),flush=True)


if __name__ == '__main__': main()
