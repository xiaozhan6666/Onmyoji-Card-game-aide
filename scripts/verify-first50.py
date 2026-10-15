"""Read-only verification of the completed supervised S56 first-50 batch."""
import hashlib
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from bwp_collector.live_profile import profile_values
from bwp_collector.live_upload import checked_file, validate_response

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'data/live-capture/first50-S56-20261013'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=BATCH)
    parser.add_argument('--rows', type=int, choices=(5,10), help='Uniform row target for a new batch; omit for the historical mixed first batch')
    args = parser.parse_args()
    batch = args.batch.resolve()
    if not batch.is_relative_to(ROOT / 'data/live-capture'):
        raise ValueError('Batch path outside capture directory')
    if batch != BATCH.resolve() and args.rows is None:
        raise ValueError('New batches require an explicit --rows target')
    state = read(batch / 'progress.json')
    config = read(ROOT / 'config/capture-first50.json')
    assert state['status'] == 'complete' and state['completed'] == 50
    assert [i['name'] for i in state['items']] == config['names']
    total = 0
    captures = set()
    per_shikigami = {}
    for index, item in enumerate(state['items']):
        assert item['status'] == 'uploaded'
        report_path = batch / item['report']
        run = report_path.parent
        report = read(report_path)
        count = args.rows if args.rows is not None else (10 if index < 2 else 5)
        assert report['complete'] and report['requested_rows'] == count
        assert report['shikigami_name'] == item['name']
        assert report['shikigami_id'] == item['shikigami_id']
        assert [r['rank'] for r in report['rows']] == list(range(1, count + 1))
        summary = read(run / 'outbox/summary.json')
        assert summary['complete'] and summary['acknowledged'] == count
        players = set()
        for row in report['rows']:
            record = row['record']
            assert record['capture_id'] not in captures
            assert record['player_id'] not in players
            captures.add(record['capture_id']); players.add(record['player_id'])
            assert len(row['profile_readings']) == 2
            for reading in row['profile_readings']:
                assert profile_values(reading['id'], reading['grade']) == {
                    'player_id': record['player_id'], 'grade': record['grade']}
            for evidence in [row['board'], row['returned'], *[r['image'] for r in row['profile_readings']]]:
                checked_file(run, evidence)
            plan_path = run / 'outbox' / f"{row['rank']:03d}.json"
            plan = read(plan_path)
            receipt = read(plan_path.with_suffix('.receipt.json'))
            assert receipt['plan_sha256'] == hashlib.sha256(plan_path.read_bytes()).hexdigest()
            assert plan['manifest']['records'][0]['capture_id'] == record['capture_id']
            assert validate_response(receipt['response'], record['capture_id'])['status'] in {'saved', 'duplicate'}
        per_shikigami[item['shikigami_id']] = count
        total += count
    with urlopen('http://127.0.0.1:18080/api/rankings', timeout=20) as response:
        rankings = json.load(response)
    by_id = {r['id']: r for r in rankings}
    for identity, count in per_shikigami.items():
        assert int(by_id[identity]['observation_count']) >= count
        assert int(by_id[identity]['observed_players']) >= count
    result = {
        'verified': True, 'completed_shikigami': 50, 'batch_observations': total,
        'evidence_images_verified': total * 4, 'catalog_size': len(rankings),
        'observed_shikigami': sum(int(r['observation_count']) > 0 for r in rankings),
        'site_observations': sum(int(r['observation_count']) for r in rankings),
        'site_sample_games': sum(int(r['sample_games']) for r in rankings),
        'non_null_win_rates': sum(r['win_rate'] is not None for r in rankings),
        'batch_updated_at': state['updated_at'],
    }
    (batch / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
