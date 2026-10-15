import hashlib
import json
from copy import deepcopy
import pytest
from uuid6 import uuid7
from bwp_collector.live_upload import prepare,send,write_json,checked_file,validate_response
from bwp_collector.live_profile import rank_rows,require_overlap


def rank(n,y,confidence=.99):
    return {'text':str(n),'confidence':confidence,'box':[10,(y-245)*2-35,80,(y-245)*2+35]}


def test_rank_positions_are_read_after_scroll_and_fragments_excluded():
    assert rank_rows([rank(7,210),rank(8,327),rank(9,454),rank(10,581),rank(11,708)])=={
        8:327,9:454,10:581,11:708}
    require_overlap({5:270,6:397,7:524,8:651,9:778},{8:327,9:454,10:581,11:708},10)


@pytest.mark.parametrize('tokens',[[rank(5,270),rank(7,397),rank(8,524)],
    [rank(5,270),rank(5,397),rank(6,524)], [rank(5,270),rank(6,350),rank(7,524)],
    [rank(5,270),rank(6,397,.8),rank(7,524)], [rank('O',270),rank(6,397),rank(7,524)]])
def test_uncertain_rank_or_missing_row_rejected(tokens):
    with pytest.raises(ValueError): rank_rows(tokens)


def test_scroll_must_advance_without_skipping_target():
    for current,target in [({8:300,9:427,10:554},6),({5:300,6:427},6),({10:300,11:427},10)]:
        with pytest.raises(ValueError): require_overlap({4:300,5:427,6:554},current,target)


@pytest.fixture
def report(tmp_path):
    raw=b'\x89PNG\r\n\x1a\nlocal-test-evidence'
    (tmp_path/'board.png').write_bytes(raw)
    evidence={'path':'board.png','sha256':hashlib.sha256(raw).hexdigest(),
        'captured_at':'2026-10-13T06:30:00.000Z','completed_at':'2026-10-13T06:30:02.000Z'}
    readings=[{'id':[{'text':'ID:00123','confidence':.99}],
        'grade':[{'text':'大名士22席','confidence':.99}],'image':dict(evidence)} for _ in range(2)]
    capture=str(uuid7())
    record={'capture_id':capture,'shikigami_id':'3','season_key':'S56','player_id':'00123','grade':10,
        'bailian_points':'3000','cumulative_wins':'100','captured_at':evidence['captured_at']}
    data={'capture_version':'mumu-top10-v1','complete':True,'scope_key':'local-development',
        'season_key':'S56','shikigami_id':'3','requested_rows':1,'rows':[{
        'rank':1,'capture_id':capture,'status':'candidate_for_review','record':record,
        'board':dict(evidence),'returned':dict(evidence),'profile_readings':readings,'return_difference':0}]}
    path=tmp_path/'report.json';write_json(path,data)
    return path,data


def reply(capture,status='saved',id='1'):
    return {'schema_version':'1.0','results':[{'capture_id':capture,'record_index':0,'status':status,'id':id}]}


def test_prepare_preserves_capture_and_rejects_incomplete(report):
    path,data=report
    outbox=prepare(path);original=(outbox/'001.json').read_bytes()
    assert prepare(path)==outbox and (outbox/'001.json').read_bytes()==original
    data['complete']=False;write_json(path,data)
    with pytest.raises(ValueError): prepare(path)


@pytest.mark.parametrize('change',['hash','identity','time','duplicate','context'])
def test_bad_evidence_never_prepares(report,change):
    path,data=report;row=data['rows'][0]
    if change=='hash': row['board']['sha256']='0'*64
    if change=='identity': row['profile_readings'][1]['id'][0]['text']='ID:00999'
    if change=='time': row['profile_readings'][1]['image']['completed_at']='2026-10-13T06:31:00.000Z'
    if change=='duplicate':
        other=deepcopy(row);other['rank']=2;data['rows'].append(other);data['requested_rows']=2
    if change=='context': row['record']['season_key']='S57'
    write_json(path,data)
    with pytest.raises(ValueError): prepare(path)
    assert not (path.parent/'outbox').exists()


def test_timeout_retry_retains_identity_and_receipt_skips_acknowledged(report):
    path,data=report;outbox=prepare(path);seen=[]
    def timeout(manifest,files,token):
        seen.append(manifest);raise TimeoutError('response lost')
    with pytest.raises(TimeoutError): send(outbox,'test-token',transport=timeout)
    assert not (outbox/'001.receipt.json').exists()
    def success(manifest,files,token):
        seen.append(manifest);return reply(manifest['records'][0]['capture_id'],'duplicate')
    assert send(outbox,'test-token',transport=success)[0]['status']=='duplicate'
    assert seen[0]==seen[1]
    assert send(outbox,'test-token',transport=timeout)[0]['status']=='duplicate'
    assert len(seen)==2


def test_http_200_with_conflict_is_not_acknowledged(report):
    path,_=report;outbox=prepare(path)
    def conflict(manifest,files,token): return reply(manifest['records'][0]['capture_id'],'conflict')
    assert send(outbox,'test-token',transport=conflict)[0]['status']=='conflict'
    called=[]
    def saved(manifest,files,token):
        called.append(True);return reply(manifest['records'][0]['capture_id'])
    assert send(outbox,'test-token',transport=saved)[0]['status']=='saved'
    assert called


def test_response_must_match_capture_and_have_saved_id():
    capture=str(uuid7())
    for response in [reply(str(uuid7())),reply(capture,id=None),reply(capture,'unknown'),{'schema_version':'1.0','results':[]}]:
        with pytest.raises(ValueError): validate_response(response,capture)


def test_paths_and_changed_files_are_rejected(report):
    path,data=report;outside=path.parent.parent/'outside-test.png';outside.write_bytes(b'x')
    with pytest.raises(ValueError): checked_file(path.parent,{'path':'../outside-test.png','sha256':hashlib.sha256(b'x').hexdigest()})
    outbox=prepare(path);(path.parent/'board.png').write_bytes(b'changed')
    with pytest.raises(ValueError): send(outbox,'test-token',transport=lambda *args: pytest.fail('must not send'))
