"""Bounded, supervised top-ten capture for the calibrated MuMu 1920x1080 layout.

Start on the selected shikigami's first leaderboard page. One OCR instance,
one device lock, fresh board per row. Evidence stays local; upload is separate.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from contextlib import nullcontext
from datetime import datetime,timezone
from pathlib import Path


def main(argv=None, *, engine=None, lock_held=False):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb',required=True)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--shikigami-name',required=True)
    parser.add_argument('--shikigami-id',required=True)
    parser.add_argument('--first-page-reference',type=Path,required=True)
    parser.add_argument('--rows',type=int,choices=range(1,11),default=10)
    parser.add_argument('--season',required=True,choices=['S56'])
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--selected-board-reference',type=Path,
                        help='Board reached from a pixel-verified selector portrait; used by the bounded batch runner')
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    os.environ['PADDLE_PDX_CACHE_HOME']=str(root/'.cache/paddlex')
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'): os.environ[key]='2'
    import cv2
    import numpy as np
    from uuid6 import uuid7
    from bwp_collector.imaging import read_image,crop,preprocess
    from bwp_collector.ocr import PaddleEngine
    from bwp_collector.live_profile import one_text,profile_values,profile_anchor,nickname_text,nickname_image_agrees,return_difference,rank_rows,require_overlap
    from bwp_collector.validation import parse_field,utc_millis
    import msvcrt
    lockdir=root/'data/live-capture';lockdir.mkdir(parents=True,exist_ok=True)
    lockname=hashlib.sha256(args.serial.encode()).hexdigest()[:16]+'.lock'
    with (nullcontext() if lock_held else (lockdir/lockname).open('a+b')) as device_lock:
        if not lock_held:
            device_lock.seek(0)
            if not device_lock.read(1): device_lock.write(b'0');device_lock.flush()
            device_lock.seek(0)
            msvcrt.locking(device_lock.fileno(),msvcrt.LK_NBLCK,1)
        # OS releases this lock on normal exit, exception or process termination.
        run=args.run_dir or lockdir/datetime.now(timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ')
        run=run.resolve()
        if not run.is_relative_to(lockdir.resolve()): raise ValueError('Run must stay inside data/live-capture')
        run.mkdir()
        command=[args.adb,'-s',args.serial]
        counter=0
        events=[]
        def check_game():
            data=subprocess.run(command+['shell','dumpsys','activity','activities'],capture_output=True,check=True,timeout=10).stdout.decode('utf-8',errors='replace')
            if not any('com.netease.yysbwp/' in line for line in data.splitlines() if 'ResumedActivity' in line):
                raise RuntimeError('Game is not foreground; stopped without sending input')
        def snapshot(label):
            nonlocal counter
            check_game();counter+=1;started=datetime.now(timezone.utc)
            raw=subprocess.run(command+['exec-out','screencap','-p'],capture_output=True,check=True,timeout=10).stdout
            completed=datetime.now(timezone.utc)
            image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
            if image is None or image.shape[:2]!=(1080,1920): raise RuntimeError('Unexpected screenshot resolution')
            path=run/f'{counter:03d}-{label}.png';path.write_bytes(raw)
            evidence={'path':str(path.relative_to(run)), 'captured_at':utc_millis(started.isoformat()),
                      'completed_at':utc_millis(completed.isoformat()),'sha256':hashlib.sha256(raw).hexdigest()}
            events.append({'capture':evidence})
            (run/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
            return image,evidence
        def tap(x,y):
            check_game()
            subprocess.run(command+['shell','input','tap',str(x),str(y)],check=True,timeout=10)
            events.append({'tap':[x,y], 'at':datetime.now(timezone.utc).isoformat()})
        def scroll():
            check_game()
            # Short, slow drag keeps an overlap; verify actual ranks afterwards.
            swipe=[1350,750,1350,480,650]
            subprocess.run(command+['shell','input','swipe',*map(str,swipe)],check=True,timeout=10)
            events.append({'swipe':swipe,'at':datetime.now(timezone.utc).isoformat()})
            time.sleep(.8)
        models=root/'.cache/paddlex/official_models'
        if engine is None:
            engine=PaddleEngine({'detection_model':'PP-OCRv5_mobile_det','recognition_model':'PP-OCRv5_mobile_rec',
                'text_detection_model_dir':str(models/'PP-OCRv5_mobile_det'),'text_recognition_model_dir':str(models/'PP-OCRv5_mobile_rec')})
        def tokens(image,box): return engine.recognize(preprocess(crop(image,box),'color',2),'live')
        reference=read_image(args.first_page_reference)
        if reference.shape[:2]!=(1080,1920): raise ValueError('Reference resolution mismatch')
        selected_reference=read_image(args.selected_board_reference) if args.selected_board_reference else None
        def normalized_title(text): return ''.join(text.split()).replace('・','·').replace('•','·')
        def assert_board(image):
            title_tokens=tokens(image,[90,596,278,656])
            events.append({'title_ocr':title_tokens})
            title=''.join(t['text'] for t in sorted(title_tokens,key=lambda t:(t['box'][1]//25,t['box'][0])))
            if selected_reference is None and (not title_tokens or any(t['confidence']<.95 for t in title_tokens)
                    or normalized_title(title)!=normalized_title(args.shikigami_name)):
                raise ValueError('Wrong or unreadable shikigami title')
            if selected_reference is not None:
                title_diff=np.mean(np.abs(image[604:644,100:265].astype(float)-selected_reference[604:644,100:265].astype(float)))
                if title_diff>5: raise ValueError('Selected shikigami label changed')
                portrait_diff=np.mean(np.abs(image[504:555,155:207].astype(float)-selected_reference[504:555,155:207].astype(float)))
                if portrait_diff>5: raise ValueError('Selected shikigami portrait changed')
            headings=tokens(image,[1050,165,1670,222])
            if {t['text'] for t in headings if t['confidence']>=.95}!={'式神百炼值','式神胜场'}:
                raise ValueError('Not the bailian leaderboard')
            # Header dims under a popup, including cards that move down the screen.
            header_diff=np.mean(np.abs(image[165:222,1050:1670].astype(float)-reference[165:222,1050:1670].astype(float)))
            if header_diff>8: raise ValueError('Unexpected popup or dimmed overlay')
            rank_diff=np.mean(np.abs(image[245:815,368:474].astype(float)-reference[245:815,368:474].astype(float)))
            if rank_diff<=8:
                return dict(enumerate([285,412,539,666,793],1))
            result=tokens(image,[368,245,474,817])
            events.append({'rank_ocr':result})
            return rank_rows(result)
        def numbers(image,y):
            values={}
            for field,l,r in [('bailian_points',1098,1240),('cumulative_wins',1510,1660)]:
                reading=tokens(image,[l,y-25,r,y+25])
                events.append({'number_ocr':reading,'field':field,'center_y':y,'crop':'row'})
                try:
                    values[field]=parse_field(field,one_text(reading))
                except ValueError:
                    # A lone zero may not be detected in a short crop. The
                    # full numeric column supplies context; select only a box
                    # centered on this verified rank, with the same .95 gate.
                    column=tokens(image,[l,247,r,817])
                    reading=[t for t in column if abs(247+(t['box'][1]+t['box'][3])/4-y)<=15]
                    events.append({'number_ocr':reading,'field':field,'center_y':y,'crop':'column'})
                    values[field]=parse_field(field,one_text(reading))
            return values
        # Nickname is only an extra before/after consistency check, never the player key.
        # Decorative fonts score lower; the four persisted fields still require >= .95.
        def row_name(image,y,with_tokens=False):
            result=tokens(image,[685,y-36,1045,y+12])
            if not result:
                # Names without a decorative title sit lower. Keep the same
                # origin for evidence boxes, extend down to include the glyphs.
                expanded=tokens(image,[685,y-36,1045,y+25])
                result=[t for t in expanded if t['box'][3]-t['box'][1]>=30
                        and (t['box'][1]+t['box'][3])/4<=52]
                events.append({'nickname_extended_crop':True,'center_y':y,'tokens':expanded})
            events.append({'nickname_ocr':result,'center_y':y})
            try:
                name=nickname_text(result)
            except ValueError:
                if not with_tokens: raise
                # Nickname is auxiliary, never a player key. Leave unreadable
                # text unset and require a strict before/after image match.
                name=None
            return (name,result) if with_tokens else name
        def read_profile(image):
            band=tokens(image,[1280,250,1444,950])
            id_tokens,top=profile_anchor(band)
            grade_tokens=tokens(image,[990,top+71,1295,top+123])
            original_grade=grade_tokens
            if len(grade_tokens)==1 and .85<=grade_tokens[0]['confidence']<.95:
                native=engine.recognize(crop(image,[990,top+71,1295,top+123]),'live-grade-native')
                # A single fixed-scale retry must agree on the entire text and
                # meet the original confidence threshold. Keep 2x box units.
                if (len(native)==1 and native[0]['confidence']>=.95
                        and ''.join(native[0]['text'].split())==''.join(grade_tokens[0]['text'].split())):
                    grade_tokens=[{**native[0],'box':[v*2 for v in native[0]['box']]}]
            buttons=tokens(image,[780,top+216,1395,top+300])
            reading={'id':id_tokens,'grade':grade_tokens,'anchor_top':top,'band':band}
            if grade_tokens is not original_grade:
                reading['grade_original_2x']=original_grade
                reading['grade_retry_scale']=1
            events.append({'profile_ocr':reading})
            if '查看信息' not in {t['text'] for t in buttons if t['confidence']>=.95}:
                raise ValueError('Profile not ready')
            return profile_values(id_tokens,grade_tokens),reading
        results=[];seen=set();started=time.perf_counter()
        report={'scope_key':'local-development','season_key':args.season,'shikigami_id':args.shikigami_id,
                'shikigami_name':args.shikigami_name,'trial':True,'requested_rows':args.rows,'rows':results,
                'cpu_threads':2,'uploaded':False,'capture_version':'mumu-top10-v1','complete':False}
        try:
            for index in range(1,args.rows+1):
                attempt={'rank':index,'capture_id':str(uuid7()),'status':'pending'};results.append(attempt)
                before,board=snapshot(f'row-{index}-board');positions=assert_board(before)
                if index==1 and positions.get(1)!=285:
                    raise ValueError('Start from the verified first page')
                if index not in positions:
                    if index-1 not in positions:
                        raise ValueError('Current page no longer overlaps the last captured rank')
                    previous=positions
                    scroll()
                    before,board=snapshot(f'row-{index}-scrolled');positions=assert_board(before)
                    require_overlap(previous,positions,index)
                    events.append({'page_transition':{'previous':previous,'current':positions}})
                    # Verify overlapping rows still contain the previously captured data.
                    for old in results[:-1]:
                        if old['rank'] in positions:
                            oy=positions[old['rank']]
                            if numbers(before,oy)!=old['values'] or row_name(before,oy)!=old['board_nickname']:
                                raise ValueError('Overlapping player row changed during scroll')
                y=positions[index]
                attempt.update({'row_y':y,'visible_ranks':positions})
                values=numbers(before,y);nickname,nickname_before=row_name(before,y,True)
                attempt.update({'board':board,'values':values,'board_nickname':nickname})
                tap(628,y)
                deadline=time.monotonic()+7
                while True:
                    time.sleep(.35);profile,evidence=snapshot(f'row-{index}-profile')
                    try:
                        identity,reading=read_profile(profile)
                        attempt.setdefault('profile_readings',[]).append({'image':evidence,**reading})
                        attempt.update({'profile':evidence,'ocr':reading,'identity':identity})
                        break
                    except ValueError as exc:
                        attempt.setdefault('retries',[]).append({'image':evidence,'reason':str(exc)})
                        if time.monotonic()>=deadline: raise RuntimeError('Profile timed out; leave evidence for review')
                # The two independently captured frames must agree before accepting identity.
                deadline=time.monotonic()+7
                while True:
                    time.sleep(.35);again,second=snapshot(f'row-{index}-profile-confirm')
                    try:
                        confirmed,reading=read_profile(again)
                    except ValueError as exc:
                        attempt.setdefault('retries',[]).append({'image':second,'reason':str(exc)})
                        if time.monotonic()>=deadline:
                            raise RuntimeError('Profile confirmation timed out; leave evidence for review')
                        continue
                    if confirmed!=identity:
                        raise RuntimeError('Profile identity changed while open')
                    attempt.setdefault('profile_readings',[]).append({'image':second,**reading})
                    break
                tap(460,198)
                deadline=time.monotonic()+7
                while True:
                    time.sleep(.35);after,returned=snapshot(f'row-{index}-returned')
                    try:
                        returned_positions=assert_board(after)
                        if set(returned_positions)!=set(positions) or any(abs(returned_positions[k]-v)>2 for k,v in positions.items()):
                            raise ValueError('Rank positions changed during profile access')
                        break
                    except ValueError:
                        if time.monotonic()>=deadline: raise RuntimeError('Failed to return to the same board')
                elapsed=(datetime.fromisoformat(second['completed_at'].replace('Z','+00:00'))-
                         datetime.fromisoformat(board['captured_at'].replace('Z','+00:00'))).total_seconds()
                difference=return_difference(before,after,y)
                attempt.update({'returned':returned,'profile_delay_seconds':elapsed,'return_difference':difference})
                returned_nickname,nickname_after=row_name(after,y,True)
                nickname_agrees=nickname is not None and returned_nickname==nickname
                if not nickname_agrees:
                    nickname_agrees=nickname_image_agrees(before,after,y,nickname_before,nickname_after,allow_unreadable=True)
                    attempt['nickname_visual_confirmation']={'before':nickname,'after':returned_nickname,'accepted':nickname_agrees}
                if elapsed>30 or numbers(after,y)!=values or not nickname_agrees or difference>5:
                    raise RuntimeError('Board row moved/changed or profile became too old; association rejected')
                if identity['player_id'] in seen: raise RuntimeError('Duplicate player across different target ranks')
                seen.add(identity['player_id']);attempt['status']='candidate_for_review'
                # Review candidates are deliberately distinct from the upload protocol.
                attempt['record']={'capture_id':attempt['capture_id'],'shikigami_id':args.shikigami_id,
                    'season_key':args.season,**identity,**values,'captured_at':board['captured_at']}
                print(json.dumps({'rank':index,'status':attempt['status'],'grade':identity['grade'],
                    'profile_delay_seconds':round(elapsed,3)},ensure_ascii=False),flush=True)
            report['complete']=True
        except Exception as exc:
            report['error']=str(exc)
            if results: results[-1]['reason']=str(exc)
            raise
        finally:
            report['elapsed_seconds']=round(time.perf_counter()-started,3)
            report['candidate_count']=sum(r['status']=='candidate_for_review' for r in results)
            (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            (run/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
            print(str(run/'report.json'),flush=True)
        return run/'report.json'


if __name__=='__main__': main()
