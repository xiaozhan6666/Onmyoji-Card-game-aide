"""Prepare or send a completed local live capture through the Java API."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen
from bwp_collector.live_upload import prepare,send,BASE_URL,write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--send',action='store_true',help='Upload to the project local Java service')
    parser.add_argument('--resend',action='store_true',help='Verify idempotency by resending acknowledged observations')
    args=parser.parse_args()
    outbox=prepare(args.report)
    if not args.send:
        print(outbox);return
    report=json.loads(args.report.read_text(encoding='utf-8'))
    with urlopen(BASE_URL+'/api/shikigami',timeout=10) as response:
        catalog=json.load(response)
    if not any(str(r['id'])==report['shikigami_id'] and r['name']==report['shikigami_name'] for r in catalog):
        raise ValueError('Local catalog does not match captured shikigami')
    root=Path(__file__).resolve().parents[1]
    settings=json.loads((root/'data/backend-local/connection.json').read_text(encoding='utf-8-sig'))
    results=send(outbox,settings['collector_token'],resend=args.resend)
    acknowledged=sum(r['status'] in {'saved','duplicate'} for r in results)
    summary={'acknowledged':acknowledged,'requested':report['requested_rows'],'results':results,
             'complete':acknowledged==report['requested_rows']}
    write_json(outbox/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    if not summary['complete']: raise SystemExit(1)


if __name__=='__main__': main()
