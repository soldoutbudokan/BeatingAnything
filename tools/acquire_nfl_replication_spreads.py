#!/usr/bin/env python3
"""Acquire only published, pinned historical board files; never call an odds API."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nfl-receptions-replication'
REPO = 'bsr-0/nfl-player-projections'
COMMIT = 'ca05a001e92386484abcb02880e5ae3ecc9800f2'
PATHS = ROOT / 'reports/nfl-receptions-replication-board-selection-2026-09-13.json'
MANIFEST = RAW / 'board-manifest.json'


def acquire(item):
    url = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{item['path']}"
    path = RAW / 'boards' / (item['fixture_date'] + '.json')
    sidecar = path.with_suffix('.acquisition.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        started = datetime.now(timezone.utc).isoformat()
        with urlopen(url, timeout=45) as response:
            data = response.read()
        ended = datetime.now(timezone.utc).isoformat()
        blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if blob != item['sha'] or len(data) != item['size']:
            raise ValueError('Published board differs from pin: ' + item['path'])
        path.write_bytes(data)
        sidecar.write_text(json.dumps({'request_started_utc': started, 'response_complete_utc': ended}, indent=2))
    data = path.read_bytes()
    assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == item['sha']
    obj = json.loads(data)
    assert isinstance(obj.get('data'), list), item['path']
    return {**item, 'source_url': url, 'local_path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(data).hexdigest(), 'source_snapshot_utc': obj['timestamp'],
            'events_in_board': len(obj['data']), **json.loads(sidecar.read_text())}


if __name__ == '__main__':
    selection = json.loads(PATHS.read_text())
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(acquire, selection['files']))
    result = {'source_repository': REPO, 'source_commit': COMMIT,
              'selection_sha256': hashlib.sha256(PATHS.read_bytes()).hexdigest(), 'files': rows}
    MANIFEST.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'boards': len(rows), 'bytes': sum(x['size'] for x in rows),
                      'manifest_sha256': hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}))
