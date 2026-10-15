"""Durable, per-observation multipart outbox for calibrated live captures.

No network is used during preparation. Receipts acknowledge individual records;
failed/ambiguous requests retain exactly the same capture ID and manifest.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib import request, error

from .contracts import BATCH_SCHEMA, validate
from .validation import decimal_string, identifier, instant

BASE_URL = 'http://127.0.0.1:18080'


def write_json(path, value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def checked_file(run, evidence):
    path=(run/evidence['path']).resolve()
    if not path.is_relative_to(run.resolve()) or not path.is_file():
        raise ValueError('Image is missing or outside the capture directory')
    raw=path.read_bytes()
    if len(raw)>8*1024*1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Evidence is not a supported PNG within 8 MiB')
    if hashlib.sha256(raw).hexdigest()!=evidence['sha256']:
        raise ValueError('Evidence hash mismatch')
    return path,raw


def prepare(report_path):
    report_path=Path(report_path).resolve(); run=report_path.parent
    report=json.loads(report_path.read_text(encoding='utf-8'))
    rows=report['rows']; count=report['requested_rows']
    if (report.get('capture_version')!='mumu-top10-v1' or report.get('complete') is not True
            or type(count) is not int or not 1<=count<=10
            or len(rows)!=count or [r['rank'] for r in rows]!=list(range(1,count+1))):
        raise ValueError('Only a complete calibrated capture can be prepared')
    if report['scope_key']!='local-development' or report['season_key']!='S56':
        raise ValueError('Unexpected capture scope or season')
    plans=[];players=set();captures=set()
    for row in rows:
        record=dict(row['record'])
        if row['status']!='candidate_for_review' or record['capture_id']!=row['capture_id']:
            raise ValueError('Row did not pass capture validation')
        if record['player_id'] in players or record['capture_id'] in captures:
            raise ValueError('Duplicate identity or capture in run')
        players.add(record['player_id']);captures.add(record['capture_id'])
        if (record['season_key']!=report['season_key'] or record['shikigami_id']!=report['shikigami_id']
                or record['captured_at']!=row['board']['captured_at']):
            raise ValueError('Observation context or timestamp changed')
        decimal_string(record['shikigami_id'],'shikigami_id',4294967295,1)
        identifier(record['player_id'],'player_id')
        for field in ('bailian_points','cumulative_wins'): decimal_string(record[field],field)
        readings=row['profile_readings']
        if len(readings)!=2 or row['return_difference']>5:
            raise ValueError('Missing independent profile confirmation or return validation')
        from .live_profile import profile_values
        expected={'player_id':record['player_id'],'grade':record['grade']}
        if any(profile_values(r['id'],r['grade'])!=expected for r in readings):
            raise ValueError('Profile evidence disagrees with observation')
        delay=(instant(readings[-1]['image']['completed_at'])-instant(record['captured_at'])).total_seconds()
        if not 0<=delay<=30: raise ValueError('Profile evidence is too old')
        evidence=[row['board'],*[r['image'] for r in readings],row['returned']]
        images=[];files={}
        for index,item in enumerate(evidence):
            path,_=checked_file(run,item)
            key=f'image_{index}'
            images.append({'key':key,'sha256':item['sha256']})
            files[key]=str(path.relative_to(run))
        record['image_keys']=list(files)
        manifest={'schema_version':'1.0','scope_key':report['scope_key'],'records':[record],'images':images}
        validate(manifest,BATCH_SCHEMA)
        plans.append({'rank':row['rank'],'manifest':manifest,'files':files})
    # Validate all rows and images before creating the outbox.
    outbox=run/'outbox';outbox.mkdir(exist_ok=True)
    for plan in plans:
        path=outbox/f"{plan['rank']:03d}.json"
        if path.exists():
            if json.loads(path.read_text(encoding='utf-8'))!=plan:
                raise ValueError('Existing outbox differs; do not replace its capture IDs')
        else: write_json(path,plan)
    return outbox


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(manifest,files,token):
    boundary='bwp-'+uuid.uuid4().hex
    parts=[]
    def add(name,content,content_type,filename=None):
        disposition=f'Content-Disposition: form-data; name="{name}"'
        if filename: disposition+=f'; filename="{filename}"'
        parts.append((f'--{boundary}\r\n{disposition}\r\nContent-Type: {content_type}\r\n\r\n').encode())
        parts.extend([content,b'\r\n'])
    add('manifest',json.dumps(manifest,ensure_ascii=False).encode('utf-8'),'application/json')
    for key,raw in files.items(): add(key,raw,'image/png',key+'.png')
    parts.append(f'--{boundary}--\r\n'.encode())
    body=b''.join(parts)
    if len(body)>40*1024*1024: raise ValueError('Batch exceeds request size limit')
    req=request.Request(BASE_URL+'/api/collector/batches',data=body,headers={
        'Authorization':'Bearer '+token,'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
    try:
        with request.build_opener(request.ProxyHandler({}),NoRedirect()).open(req,timeout=30) as response:
            return json.loads(response.read(256*1024))
    except error.HTTPError as exc:
        raise RuntimeError(f'Upload HTTP {exc.code}; original observation retained') from None
    except (error.URLError,TimeoutError) as exc:
        raise RuntimeError('Upload disconnected or timed out; retry the original outbox') from None


def validate_response(response,capture):
    if response.get('schema_version')!='1.0' or len(response.get('results',[]))!=1:
        raise ValueError('Ambiguous upload response')
    result=response['results'][0]
    if result.get('capture_id')!=capture or result.get('record_index')!=0:
        raise ValueError('Response refers to another observation')
    if result.get('status') not in {'saved','duplicate','invalid','conflict'}:
        raise ValueError('Unknown upload status')
    if result['status'] in {'saved','duplicate'}:
        decimal_string(result.get('id'),'stored_id',minimum=1)
    return result


def send(outbox,token,*,resend=False,transport=post):
    outbox=Path(outbox).resolve();run=outbox.parent
    outcomes=[]
    for path in sorted(outbox.glob('[0-9][0-9][0-9].json')):
        plan=json.loads(path.read_text(encoding='utf-8'));manifest=plan['manifest']
        validate(manifest,BATCH_SCHEMA)
        if manifest['scope_key']!='local-development' or len(manifest['records'])!=1:
            raise ValueError('Invalid local outbox')
        capture=manifest['records'][0]['capture_id']
        receipt_path=path.with_suffix('.receipt.json')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if receipt_path.exists() and not resend:
            receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt.get('plan_sha256')!=digest: raise ValueError('Outbox changed after acknowledgement')
            result=validate_response(receipt['response'],capture)
            if result['status'] in {'saved','duplicate'}:
                outcomes.append(result);continue
        files={}
        for item in manifest['images']:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',item['key']) or item['key']=='manifest':
                raise ValueError('Invalid multipart key')
            _,files[item['key']]=checked_file(run,{'path':plan['files'][item['key']],'sha256':item['sha256']})
        response=transport(manifest,files,token)
        result=validate_response(response,capture)
        write_json(receipt_path,{'plan_sha256':digest,'response':response})
        outcomes.append(result)
        if result['status'] not in {'saved','duplicate'}: break
    if not outcomes: raise ValueError('Outbox has no observations')
    return outcomes
