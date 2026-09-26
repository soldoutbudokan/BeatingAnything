#!/usr/bin/env python3
"""One declared DNS-recovery pass; preserve original failed receipts and outputs."""
import hashlib
import json
from pathlib import Path
import sys

import inventory_nba_injury_price_clocks as inventory

ROOT = Path(__file__).resolve().parents[1]
ADDENDUM = ROOT / 'docs/nba-injury-clock-transport-recovery-2026-09-26.md'
BASE_REPORT = ROOT / 'reports/nba-injury-price-clocks-2026-09-26.json'
DIAGNOSTIC = ROOT / 'data/raw/nba-injury-price-clocks-2026-09-26/root-dns-diagnostic.json'
OUTPUT = ROOT / 'reports/nba-injury-price-clocks-recovery-2026-09-26.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not OUTPUT.exists(), 'Preserve the one recovery attempt'
    assert ADDENDUM.exists()
    original = json.loads(BASE_REPORT.read_text())
    assert sha(Path(inventory.__file__)) == original['tool']['sha256']
    assert original['distinct_attempted_urls'] == 3
    assert all(len(e['attempts']) == 1 and e['stop_reason'] == 'transport_failure_stop'
               and e['attempts'][0]['receipt']['curl_exit_code'] == 6 for e in original['events'])
    assert json.loads(DIAGNOSTIC.read_text())['resolved'] is True
    inventory.RAW = ROOT / 'data/raw/nba-injury-price-clocks-recovery-2026-09-26'
    inventory.REPORT = OUTPUT
    sys.argv = [sys.argv[0], '--fetch']
    inventory.main()
    result = json.loads(OUTPUT.read_text())
    urls = {a['url'] for e in original['events'] + result['events'] for a in e['attempts']}
    assert len(urls) <= 27
    assert original['network_requests_this_run'] + result['network_requests_this_run'] <= 30
    result['transport_recovery'] = {
        'addendum': {'path': str(ADDENDUM.relative_to(ROOT)), 'sha256': sha(ADDENDUM)},
        'wrapper': {'path': str(Path(__file__).relative_to(ROOT)), 'sha256': sha(Path(__file__))},
        'original_attempt': {'path': str(BASE_REPORT.relative_to(ROOT)), 'sha256': sha(BASE_REPORT)},
        'dns_diagnostic': {'path': str(DIAGNOSTIC.relative_to(ROOT)), 'sha256': sha(DIAGNOSTIC)},
        'distinct_urls_both_passes': len(urls),
        'request_attempts_both_passes': original['network_requests_this_run'] + result['network_requests_this_run'],
        'statistical_specification_changed': False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n')
    OUTPUT.with_suffix('.md').write_text(inventory.markdown(result) +
        '\nThis is the separately declared transport recovery after three DNS failures. '
        'The [original attempt](nba-injury-price-clocks-2026-09-26.md) is preserved.\n')


if __name__ == '__main__':
    main()
