#!/usr/bin/env python3
"""Bounded lagged-report census. No boxscores, player performance, or target labels."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re

import inventory_nba_injury_price_clocks as base

ROOT = base.ROOT
RAW = ROOT / 'data/raw/nba-announced-absence-2026-09-26'
PRICES = RAW / 'prices.json'
PRICE_SHA = 'f44b4d42fc168e434776a7fd89a2cc9bd09bd470adb13189de7b4270ac048372'
DECL = ROOT / 'docs/nba-announced-absence-declaration-2026-09-26.md'
REPORT = ROOT / 'reports/nba-announced-absence-source-inventory-2026-09-26.json'
DENIED_EVENT = 'df4b9f35b66ef20724b6b3e81081ddfd'
BOUNDARY = base.parse_iso('2026-01-01T00:00:00Z')


def candidates(entry):
    slot = (entry.astimezone(base.NY) - timedelta(minutes=60)).replace(second=0,microsecond=0)
    slot = slot.replace(minute=slot.minute//30*30)
    result = []
    for i in range(6):
        when = slot - timedelta(minutes=30*i)
        stem = when.strftime('Injury-Report_%Y-%m-%d_%I')
        names = [stem + when.strftime('_%M%p.pdf')]
        if when.minute == 30:
            names.append(stem + when.strftime('%p.pdf'))
        result.extend({'slot_et':when.isoformat(),'url':'https://ak-static.cms.nba.com/referee/injury/'+n} for n in names)
    assert len(result) == 9 and len({r['url'] for r in result}) == 9
    return result


class Sources:
    def __init__(self, permit_fetch):
        self.permit_fetch = permit_fetch
        self.receipts = {}
        self.new_requests = 0
        self.clocks = {}
        self.lines = {}
        # Recovery receipts supersede transport-only originals, never a retained denial.
        folders = ['nba-injury-price-clocks-2026-09-26','nba-injury-price-clocks-recovery-2026-09-26',
                   'nba-injury-new-source-check-2026-09-26','nba-announced-absence-2026-09-26']
        for folder in folders:
            for p in sorted((ROOT/'data/raw'/folder).rglob('*.receipt.json')):
                r = json.loads(p.read_text())
                if 'url' not in r or 'body_path' not in r:
                    continue
                old = self.receipts.get(r['url'])
                if old and old.get('http_status') in {401,403,429}:
                    continue
                self.receipts[r['url']] = r

    def get(self,url):
        if url in self.receipts:
            r = self.receipts[url]
            for k in ['body','headers']:
                assert base.sha(ROOT/r[k+'_path']) == r[k+'_sha256']
            return r,False
        if self.new_requests >= 1200:
            raise RuntimeError('global_request_ceiling')
        r,new = base.fetch(url,self.permit_fetch)
        self.new_requests += int(new)
        self.receipts[url] = r
        return r,new

    def clock(self,r,entry):
        key = r['body_sha256']
        # The full receipt also matters: a later Last-Modified cannot be discarded.
        key += r['headers_sha256']
        if key not in self.clocks:
            self.clocks[key] = base.clock_check(r,entry)
        c = deepcopy(self.clocks[key])
        if 'available_after_bound_utc' in c:
            c['seconds_before_entry'] = (entry-base.parse_iso(c['available_after_bound_utc'])).total_seconds()
            reasons = [s for s in c['rejection_reasons'] if s != 'source_clock_outside_60_minute_to_6_hour_window']
            if not 3600 <= c['seconds_before_entry'] <= 21600:
                reasons.append('source_clock_outside_60_minute_to_6_hour_window')
            c['rejection_reasons'] = reasons
            c['clock_qualified'] = not reasons
        return c

    def pdf_lines(self,r):
        key = r['body_sha256']
        if key not in self.lines:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(ROOT/r['body_path'])
            lines = []
            for i in range(len(doc)):
                page = doc[i]
                textpage = page.get_textpage()
                lines.extend((i+1,' '.join(s.split())) for s in textpage.get_text_range().splitlines())
                textpage.close()
                page.close()
            doc.close()
            self.lines[key] = lines
        return self.lines[key]


def extract(lines,sample,teams):
    target_day = base.parse_iso(sample['provider_start_utc']).astimezone(base.NY).strftime('%m/%d/%Y')
    target_matchup = teams[sample['away_team']]+'@'+teams[sample['home_team']]
    day = time = matchup = club = None
    states = {sample[k]:{'seen':False,'not_yet_submitted':False,'status_rows':[]} for k in ['away_team','home_team']}
    raw, times, ambiguities = [],set(),[]
    for page,line in lines:
        if not line or line.startswith('Injury Report:') or re.fullmatch(r'Page \d+ of \d+',line) or line.startswith('Game Date Game Time'):
            continue
        found_day = re.search(r'\b\d{2}/\d{2}/\d{4}\b',line)
        if found_day:
            day = found_day.group()
        found_time = base.TIME_RE.search(line)
        if found_time:
            time = found_time[1]+(' '+found_time[2] if found_time[2] else '')
        found_match = base.MATCH_RE.search(line)
        if found_match:
            matchup = found_match[1]+'@'+found_match[2]
            club = None
        names = [name for name in teams if base.norm(name) in base.norm(line)]
        if len(names) == 1:
            club = names[0]
        if matchup != target_matchup or day != target_day:
            continue
        raw.append({'page':page,'raw_line':line,'team_context':club})
        if time:
            times.add(time)
        if len(names) > 1:
            ambiguities.append('multiple_team_names_on_line')
        if club not in states:
            ambiguities.append('unknown_team_context')
            continue
        state = states[club]
        state['seen'] = True
        if 'NOTYETSUBMITTED' in re.sub('[^A-Z]','',line.upper()):
            state['not_yet_submitted'] = True
        statuses = list(base.STATUS_RE.finditer(line))
        if len(statuses) > 1:
            ambiguities.append('multiple_statuses_on_line')
        if len(statuses) == 1:
            status = statuses[0]
            prefix = re.sub(r'\b\d{2}/\d{2}/\d{4}\b','',line[:status.start()])
            prefix = base.MATCH_RE.sub('',base.TIME_RE.sub('',prefix))
            for name in names:
                prefix = re.sub(r'\s*'.join(map(re.escape,name.split())),'',prefix,flags=re.I)
            player = prefix.strip()
            if not player or ',' not in player:
                ambiguities.append('player_name_format_unresolved')
            state['status_rows'].append({'player_literal':player,'status':status[1],
                'reason_first_line':line[status.end():].strip(),'page':page})
    for club,state in states.items():
        names = {}
        dedup = []
        for row in state['status_rows']:
            key = base.norm(row['player_literal'])
            value = (row['status'],row['reason_first_line'])
            if key in names and names[key] != value:
                ambiguities.append('conflicting_duplicate_player')
            elif key not in names:
                names[key] = value
                dedup.append(row)
        state['status_rows'] = dedup
    both = all(s['seen'] and s['status_rows'] and not s['not_yet_submitted'] for s in states.values())
    starts = sorted({s for t in times for s in base.printed_start_candidates(target_day,t)})
    matched_starts = [s for s in starts if base.parse_iso(s) == base.parse_iso(sample['independent_start_utc'])]
    qualified = bool(raw) and both and len(matched_starts)==1 and not ambiguities
    out = [(club,r['player_literal']) for club,s in states.items() for r in s['status_rows'] if r['status']=='Out']
    return {'target_matchup':target_matchup,'target_game_date_et':target_day,'matching_fixture_raw_lines':raw,
        'teams':states,'printed_game_time_et_values':sorted(times),'printed_start_utc_candidates':starts,
        'independent_matched_start_candidates':matched_starts,'ambiguities':sorted(set(ambiguities)),
        'both_teams_submitted':both,'fixture_qualified':qualified,'explicit_out_count':len(out),
        'generous_exposure_ceiling_eligible':qualified and bool(out),
        'unlisted_players_treated_as_healthy':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true')
    args = parser.parse_args()
    assert not REPORT.exists(), 'Preserve completed inventory'
    assert base.sha(PRICES) == PRICE_SHA
    base.RAW = RAW
    sources = Sources(args.fetch)
    teams = base.load_teams()
    prices = json.loads(PRICES.read_text())['events']
    events,period_summary = [],{}
    for period,early in [('calibration',True),('evaluation',False)]:
        rows = [s for s in prices if (base.parse_iso(s['source_snapshot_utc']) < BOUNDARY)==early]
        for sample in rows:
            entry = base.parse_iso(sample['source_snapshot_utc'])
            event = {'period':period,'event_id':sample['event_id'],'espn_game_id':sample['espn_game_id'],
                'selected_price_metadata':sample,'attempts':[],'stop_reason':'bounded_slots_exhausted'}
            if sample['event_id'] == DENIED_EVENT:
                event['stop_reason'] = 'previously_denied_event_excluded'
            else:
                event['candidate_urls'] = candidates(entry)
                for candidate in event['candidate_urls']:
                    try:
                        receipt,new = sources.get(candidate['url'])
                    except RuntimeError as exc:
                        event['stop_reason'] = str(exc)
                        break
                    attempt = dict(candidate,receipt=receipt,reused_receipt=not new)
                    event['attempts'].append(attempt)
                    if receipt['curl_exit_code'] != 0:
                        event['stop_reason'] = 'transport_failure_stop'
                        break
                    status = receipt['http_status']
                    if status == 404:
                        continue
                    if status != 200:
                        event['stop_reason'] = 'access_denial_or_server_response_stop'
                        break
                    if not receipt['body_path'].endswith('.pdf'):
                        event['stop_reason'] = 'non_pdf_response_stop'
                        break
                    check = sources.clock(receipt,entry)
                    attempt['clock_check'] = check
                    if check['clock_qualified']:
                        event['stop_reason'] = 'first_clock_qualified_pdf'
                        event['qualified_receipt'] = receipt
                        event['qualified_clock'] = check
                        event['fixture_evidence'] = extract(sources.pdf_lines(receipt),sample,teams)
                        break
            events.append(event)
            # Partial ledger permits recovery/audit without rerunning any URL.
            base.write_json(RAW/'source-inventory.partial.json',{'events':events,'new_requests':sources.new_requests})
            print(json.dumps({'event_id':sample['event_id'],'period':period,'stop':event['stop_reason'],
                'source_qualified':event.get('fixture_evidence',{}).get('generous_exposure_ceiling_eligible',False),
                'new_requests':sources.new_requests}),flush=True)
        group = [e for e in events if e['period']==period]
        n = sum(e.get('fixture_evidence',{}).get('generous_exposure_ceiling_eligible',False) for e in group)
        period_summary[period] = {'price_events':len(group),'stop_counts':dict(Counter(e['stop_reason'] for e in group)),
            'clock_qualified_events':sum('qualified_clock' in e for e in group),
            'fixture_qualified_events':sum(e.get('fixture_evidence',{}).get('fixture_qualified',False) for e in group),
            'generous_any_out_game_ceiling':n,'source_gate_pass':n>=100}
        if n<100:
            break
    result = {'declaration':{'path':base.relative(DECL),'sha256':base.sha(DECL),'commit':'4acb250'},
        'tool':{'path':base.relative(Path(__file__)),'sha256':base.sha(__file__)},
        'shared_clock_fetch_helper':{'path':base.relative(Path(base.__file__)),'sha256':base.sha(base.__file__)},
        'price_inventory':{'path':base.relative(PRICES),'sha256':PRICE_SHA},
        'new_http_requests':sources.new_requests,'distinct_considered_urls':len({a['url'] for e in events for a in e['attempts']}),
        'period_summary':period_summary,'events':events,'player_performance_read':False,'forecasts_or_returns_computed':False,
        'scope':'Lagged official-source ceiling only. No star roles, membership, target participation or scoring joined.',
        'source_claim_limit':'Current retained PDFs and server timestamps are retrospective source assertions, not original receipts.'}
    base.write_json(REPORT,result)
    print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2),flush=True)


if __name__=='__main__':
    main()
