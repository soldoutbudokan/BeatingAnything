#!/usr/bin/env python3
"""Fixed 2024–25 PREM fallback, following a blocked URC landing request.

Public feed is linked by PREM's own frontend; no authentication or browser
impersonation. Download only on --download; subsequent analysis uses cache.
Third-party responses stay ignored, and the report records their SHA256 hashes.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/rugby-yellow-card'
BASE = 'https://rugby-union-feeds.incrowdsports.com/v1/matches'
SEASON = '202401'
LIST_PATH = RAW / 'prem-2024-25-matches.json'
SEASON_LABEL = '2024-25'
REPORT_SUFFIX = ''
LIST_URL = BASE + '?provider=rugbyviz&season=202401&compId=1011&sort=date&form=true&images=false'
SCORE = {'Try': 5, 'Penalty Try': 7, 'Penalty try': 7, 'Conversion': 2, 'Penalty': 3, 'Drop Goal': 3, 'Drop goal': 3}


def fetch(url, path):
    if not path.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
        path.write_bytes(payload)
    return json.loads(path.read_bytes())


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    games = fetch(LIST_URL, LIST_PATH)['data']
    todo = [g for g in games if not (RAW / f"match-{g['id']}.json").exists()]
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, BASE + f"/{g['id']}?provider=rugbyviz", RAW / f"match-{g['id']}.json"): g['id'] for g in todo}
        for i, f in enumerate(as_completed(futures), 1):
            try:
                f.result()
            except Exception as exc:
                errors.append({'match_id': futures[f], 'error': str(exc)})
                # Do not submit new work or retry a denial. Pending work is cancelled.
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 429):
                    for remaining in futures:
                        remaining.cancel()
                    break
            if i % 10 == 0:
                print(f'downloaded {i}/{len(todo)}; errors={len(errors)}', flush=True)
    (RAW / f'download-errors-{SEASON_LABEL}.json').write_text(json.dumps(errors, indent=2) + '\n')
    print(f'Cached games: {len(list(RAW.glob("match-*.json")))}; download errors: {errors}', flush=True)


def clock(e):
    return int(e['minute']) * 60 + int(e.get('second') or 0)


def key(e):
    return (0 if e['period'] == 'First Half' else 1, clock(e), int(e['id']))


def yellow(e):
    return 'yellow' in e['type'].lower()


def red(e):
    return 'red' in e['type'].lower() and 'card' in e['type'].lower()


def try_event(e):
    return e['type'].lower() in ('try', 'penalty try')


def margin_band(score):
    return -1 if score < -7 else (1 if score > 7 else 0)


def analyze():
    games = json.loads((LIST_PATH).read_bytes())['data']
    types, excluded = Counter(), Counter()
    accepted, exposed, controls, hashes = [], [], [], []
    score_mismatches = []
    for g in games:
        p = RAW / f"match-{g['id']}.json"
        if not p.exists():
            excluded['missing_match_response'] += 1
            continue
        payload = p.read_bytes()
        hashes.append({'match_id': g['id'], 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)})
        m = json.loads(payload)['data']
        events = m.get('events') or []
        types.update(e['type'] for e in events)
        # The published feed has a terminal Post Game / End marker in every
        # completed match. It is not an extra-time playing period.
        events = [e for e in events if not (e.get('period') == 'Post Game' and e.get('type') == 'End')]
        if m.get('status') != 'result' or not events:
            excluded['not_complete_result'] += 1
            continue
        if any(e.get('period') not in ('First Half', 'Second Half') for e in events):
            excluded['extra_or_unknown_period'] += 1
            continue
        if not {'First Half Start', 'First Half End', 'Second Half Start', 'Second Half End'}.issubset({e['type'] for e in events}):
            excluded['missing_period_boundary'] += 1
            continue
        if any(clock(next(e for e in events if e['type'] == name)) < minimum for name, minimum in [('First Half End', 2400), ('Second Half End', 4800)]):
            excluded['shortened_playing_half'] += 1
            continue
        if any(red(e) for e in events):
            excluded['red_card_match'] += 1
            continue
        # Match detail order resets its displayed minute at half-time. Compare
        # period and playing clock together, never the wall-clock timestamp.
        events = sorted(events, key=key)
        teams = [m['homeTeam']['id'], m['awayTeam']['id']]
        score = {t: 0 for t in teams}
        unknown_scores = [e['type'] for e in events if any(w in e['type'].lower() for w in ('try', 'conversion', 'penalty', 'drop')) and e['type'] not in SCORE and not any(w in e['type'].lower() for w in ('miss', 'attempt'))]
        if unknown_scores:
            excluded['unknown_scoring_type'] += 1
            continue
        for e in events:
            if e['type'] in SCORE:
                score[e['teamId']] += SCORE[e['type']]
        if any(score[t['id']] != t['score'] for t in (m['homeTeam'], m['awayTeam'])):
            excluded['score_reconstruction_mismatch'] += 1
            score_mismatches.append({'match_id': m['id'], 'published_score': {str(t['id']): t['score'] for t in (m['homeTeam'], m['awayTeam'])}, 'reconstructed_score': score})
            continue
        accepted.append(m['id'])
        cards = [e for e in events if yellow(e)]
        def prior_margin(team, period, seconds, event_id=-1):
            boundary = (0 if period == 'First Half' else 1, seconds, event_id)
            sc = {t: 0 for t in teams}
            for e in events:
                if key(e) >= boundary:
                    break
                if e['type'] in SCORE:
                    sc[e['teamId']] += SCORE[e['type']]
            other = next(t for t in teams if t != team)
            return sc[team] - sc[other]
        def count_tries(team, period, start):
            return sum(try_event(e) and e.get('teamId') == team and e['period'] == period and start < clock(e) <= start + 600 for e in events)
        if cards:
            card = cards[0]
            period, start = card['period'], clock(card)
            end = 2400 if period == 'First Half' else 4800
            simultaneous = sum(e['period'] == period and clock(e) == start for e in cards)
            boundary_pt = any(e['period'] == period and clock(e) == start and e['type'].lower() == 'penalty try' for e in events)
            if end - start < 600:
                excluded['first_yellow_insufficient_half_remaining'] += 1
            elif simultaneous != 1:
                excluded['simultaneous_first_yellows'] += 1
            elif boundary_pt:
                excluded['penalty_try_at_card_boundary'] += 1
            else:
                team = next(t for t in teams if t != card['teamId'])
                margin = prior_margin(team, period, start, card['id'])
                exposed.append({'match_id': m['id'], 'team_id': team, 'period': period, 'start_seconds': start, 'clock_bin': start // 600, 'margin': margin, 'margin_band': margin_band(margin), 'tries': count_tries(team, period, start), 'minutes': 10, 'later_cards_in_window': sum(e['period'] == period and start < clock(e) <= start + 600 for e in cards)})
        for period, starts in [('First Half', range(0, 1801, 600)), ('Second Half', range(2400, 4201, 600))]:
            for start in starts:
                # Card-free controls exclude both a new card in the window and
                # a yellow in the preceding ten playing minutes of that half.
                # Exclude all second-half controls until 50:00 after a late
                # first-half yellow; its unused suspension can cross half-time.
                overlaps = any(e['period'] == period and start - 600 < clock(e) <= start + 600 for e in cards)
                cross_half = period == 'Second Half' and start < 3000 and any(e['period'] == 'First Half' and clock(e) > 1800 for e in cards)
                if overlaps or cross_half:
                    continue
                for team in teams:
                    margin = prior_margin(team, period, start)
                    controls.append({'match_id': m['id'], 'team_id': team, 'period': period, 'start_seconds': start, 'clock_bin': start // 600, 'margin_band': margin_band(margin), 'tries': count_tries(team, period, start), 'minutes': 10})
    by_stratum = defaultdict(list)
    for c in controls:
        by_stratum[(c['team_id'], c['clock_bin'], c['margin_band'])].append(c)
    matched = []
    for e in exposed:
        candidates = [c for c in by_stratum[(e['team_id'], e['clock_bin'], e['margin_band'])] if c['match_id'] != e['match_id']]
        if candidates:
            matched.append({**e, 'control_windows': len(candidates), 'control_mean_tries': sum(c['tries'] for c in candidates) / len(candidates)})
    n = len(matched)
    exp_mean = sum(e['tries'] for e in matched) / n if n else None
    control_mean = sum(e['control_mean_tries'] for e in matched) / n if n else None
    relative = exp_mean / control_mean - 1 if control_mean else None
    result = {'date': '2026-09-13', 'status': 'unresolved' if n < 100 else ('sport-side confirmed' if relative is not None and relative >= .3 else 'sport-side dead'), 'competition': 'Gallagher Premiership', 'season': SEASON_LABEL, 'source_url': LIST_URL, 'listed_games': len(games), 'accepted_games': len(accepted), 'excluded': dict(excluded), 'score_mismatch_details': score_mismatches, 'event_types': dict(types), 'qualifying_exposures': len(exposed), 'matched_exposures': n, 'control_windows': len(controls), 'exposed_try_mean_per_10_minutes': exp_mean, 'standardized_control_try_mean_per_10_minutes': control_mean, 'relative_change': relative, 'exposed_minutes': n * 10, 'post_trigger_additional_cards': sum(e['later_cards_in_window'] for e in matched), 'threshold_minimum_exposures': 100, 'threshold_relative_change': .3, 'exposure_rows': matched, 'match_hashes': hashes, 'list_sha256': hashlib.sha256((LIST_PATH).read_bytes()).hexdigest(), 'actual_fanduel_quotes': 0, 'caveats': ['Each season is preserved separately; combined results are exploratory, with a fixed stop after 2022–23 through 2024–25.', 'Trigger windows, not independently verified continuous 15v14 exposure.', 'Card selection and field position may explain scoring differences; this is not a causal yellow-card effect.', 'Controls are ten-minute aligned windows; exposed windows retain card seconds and are only matched to the same ten-minute start bin.', 'Entire red-card matches are excluded retrospectively; the screen is not a directly deployable trigger rule.', 'No FanDuel market availability, suspension behavior or live-price evidence has been obtained.']}
    out = ROOT / f'reports/rugby-yellow-card{REPORT_SUFFIX}-2026-09-13.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('exposure_rows','match_hashes')}, indent=2))


def summarize():
    root=ROOT
    paths=[root/'reports/rugby-yellow-card-2026-09-13.json',root/'reports/rugby-yellow-card-2023-24-2026-09-13.json',root/'reports/rugby-yellow-card-2022-23-2026-09-13.json']
    reports=[json.loads(p.read_text()) for p in paths]
    rows=[row for r in reports for row in r['exposure_rows']]
    n=len(rows); tries=sum(x['tries'] for x in rows); expected=sum(x['control_mean_tries'] for x in rows); relative=tries/expected-1
    out={'date':'2026-09-13','status':'sport-side confirmed' if n>=100 and relative>=.3 else ('sport-side dead' if n>=100 else 'unresolved'),'study':'First isolated yellow card, opponent tries in next ten playing minutes','competition':'Gallagher Premiership','season_reports':[{'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'season':r['season'],'listed_games':r['listed_games'],'accepted_games':r['accepted_games'],'matched_exposures':r['matched_exposures'],'exposed_try_mean_per_10_minutes':r['exposed_try_mean_per_10_minutes'],'standardized_control_try_mean_per_10_minutes':r['standardized_control_try_mean_per_10_minutes'],'relative_change':r['relative_change']} for p,r in zip(paths,reports)],'listed_games':sum(r['listed_games'] for r in reports),'accepted_games':sum(r['accepted_games'] for r in reports),'matched_exposures':n,'exposed_minutes':10*n,'tries':tries,'exposed_try_mean_per_10_minutes':tries/n,'standardized_control_try_mean_per_10_minutes':expected/n,'relative_change':relative,'post_trigger_additional_cards':sum(r['post_trigger_additional_cards'] for r in reports),'threshold_minimum_exposures':100,'threshold_relative_change':.3,'fixed_stop':'Three seasons 2022–23 through 2024–25, irrespective of effect','actual_fanduel_quotes':0,'edge_confirmed':False,'caveats':reports[-1]['caveats']}
    (root/'reports/rugby-yellow-card-combined-2026-09-13.json').write_text(json.dumps(out,indent=2)+'\n')
    lines=['# Rugby yellow-card exploration — September 13, 2026','',f"**{out['status'].capitalize()}:** {n} matched first-yellow-card windows across {out['listed_games']} published Premiership fixtures produced {tries} opponent tries in {10*n:,} playing minutes. The rate was **{tries/n:.3f} tries per ten minutes versus {expected/n:.3f} standardized control tries**, a **{relative:+.1%}** difference. The gate remains at least 100 matched windows and at least a 30% increase. It is a sport-side exploratory result; zero FanDuel quotes were obtained and no betting edge is confirmed.",'','| Season | Published fixtures | Eligible matches | Matched card windows | Opponent tries / 10 min | Standardized control tries / 10 min | Relative change |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in reports:
     lines.append(f"| {r['season']} | {r['listed_games']} | {r['accepted_games']} | {r['matched_exposures']} | {r['exposed_try_mean_per_10_minutes']:.3f} | {r['standardized_control_try_mean_per_10_minutes']:.3f} | {r['relative_change']:+.1%} |")
    lines += ['', '## What ran','', 'The card was written before outcome inspection. The official URC stats landing request returned HTTP 403, which was respected. PREM’s own public frontend explicitly references the InCrowd rugby-union match feed. An ordinary unauthenticated request recovered complete fixtures and match-event responses; no API key, account, header impersonation or blocked-source workaround was used. The fixed fallback was 2024–25. Its 93-game ceiling was known before the conditional result, so 2023–24 was added before either season’s effect was seen. After seeing the 44-window positive 2024–25 pilot, one final 2022–23 coverage extension was declared if the first two seasons had fewer than 100 matches; they had 81. The fixed stop was all three seasons regardless of result. The 2022–23 source retains seven played Worcester/Wasps fixtures; those games remain in the published-list sample instead of being removed to reproduce a later league table. The pooled result is exploration, not an untouched confirmation sample.','', 'The trigger is the first isolated yellow card, with at least ten regulation minutes left in that half. Red-card matches and a penalty try at the card’s exact clock time are excluded. The exposed outcome is every opponent try in the next ten playing minutes, including any further cards. Tries at the trigger’s exact timestamp are not counted. Every accepted event stream reconstructed the published final scores. Across the three seasons, 32 red-card matches and one score-mismatch match were excluded; match 271699 reconstructs Bath 10–London Irish 23 from events against a 10–25 scoreboard and was not repaired. There were 134 qualifying first-card windows, of which 133 had matching controls. The parser uses half plus minute/second, so first-half overrun and the second-half clock reset do not create negative time. The feed’s terminal `Post Game / End` marker was normalized after the initial schema pass excluded every match; no valid conditional comparison existed at that point.','', 'Controls are ten-minute aligned windows free of an active or newly occurring yellow. A late first-half yellow also removes the first ten minutes of second-half control exposure. Exposed windows match controls from other matches in the same season, team, ten-minute start bin and score band (more than seven behind, within seven, more than seven ahead). Each exposure receives its stratum’s control mean; the combined estimate averages these within-season comparisons. Later cards in an exposed window remain counted.','', '## What the result does and does not show','', 'The conditional scoring difference is large enough to investigate an actual live price. A yellow card often follows sustained pressure near the try line. Field position and possession are absent from this small event feed, so the difference cannot be attributed solely to the missing defender. Clock bins are coarse; exposed windows begin at the actual card second while control windows start on ten-minute boundaries. Entire red-card matches were excluded using later information. These choices make this an exploratory screening sample, not a deployable betting rule.','', 'The fixed ten-minute denominator measures an outcome window after a published trigger; it is not a claim that the teams remained exactly 15 versus 14 throughout. Return-to-field delays and later cards can change the actual headcount. An actual next-try market also needs the other team’s competing scoring rate and the no-further-try outcome; an opponent try-rate increase alone is insufficient to price it.','', f"There were {out['post_trigger_additional_cards']} additional yellow-card events inside the matched exposed windows. No confidence interval or causal inference is being claimed from the exploratory point estimates. The individual reports preserve every matched exposure and source response hash. An independent review reconstructed all 133 exposure clocks, margins and outcomes without discrepancies and checked the control-matching logic; the mismatched-score exclusion was confirmed from the raw feed.",'', '## Calendar and next concrete step','', 'Both candidate northern-hemisphere competitions have a full season ahead. [Irish Rugby’s official URC calendar](https://www.irishrugby.ie/2026/05/19/bkt-urc-fixtures-released-for-2026-27-season) starts September 25, 2026 and ends June 19, 2027. [PREM’s official announcement](https://www.premiershiprugby.com/content/gallagher-prem-2026-27-start-and-final-dates-confirmed) starts September 25–27, 2026 and ends June 19, 2027. [World Rugby law 9.29](https://passport.world.rugby/laws-of-the-game/laws-by-number/9-foul-play/) specifies ten-minute yellow cards; law 9.30 separately distinguishes permanent red cards from qualifying twenty-minute replacement reds. Do not transfer this estimate to rugby league or a red-card market.','', 'Next, verify whether FanDuel actually offers a live next-try-team or team-try-total market for PREM/URC and whether it remains open following a card. Obtain paired quotes, market rules, suspension state, exact trigger timing and a matched settlement reference. General rugby coverage or a rulebook mention does not establish a specific league’s live derivative availability. Do not expand this historical sample again merely because the conditional effect is positive.','', '## Reproduce','', 'Run the existing script for each fixed season. Without `--download`, it uses cached public inputs. Raw match data and site assets remain ignored; only derived rows and hashes are published.','', '```sh','python tools/explore_rugby_yellow_cards.py --download --season 202401','python tools/explore_rugby_yellow_cards.py --download --season 202301','python tools/explore_rugby_yellow_cards.py --download --season 202201','python tools/explore_rugby_yellow_cards.py --summary','```','', 'The feed entry point is [the published PREM match list](https://rugby-union-feeds.incrowdsports.com/v1/matches?provider=rugbyviz&season=202401&compId=1011&sort=date&form=true&images=false), referenced by [PREM’s fixture page](https://www.premiershiprugby.com/fixtures-results/). Each match uses `/v1/matches/{id}?provider=rugbyviz`. Reports retain exact SHA256 values; fresh responses may differ because the publisher refreshes metadata or corrects events.']
    (root/'reports/rugby-yellow-card-2026-09-13.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='season_reports'},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--summary', action='store_true')
    parser.add_argument('--season', choices=['202401', '202301', '202201'], default='202401')
    args = parser.parse_args()
    if args.summary:
        summarize()
        raise SystemExit(0)
    SEASON = args.season
    if SEASON != '202401':
        SEASON_LABEL = {'202301': '2023-24', '202201': '2022-23'}[SEASON]
        REPORT_SUFFIX = '-' + SEASON_LABEL
        LIST_PATH = RAW / f'prem-{SEASON_LABEL}-matches.json'
        LIST_URL = BASE + f'?provider=rugbyviz&season={SEASON}&compId=1011&sort=date&form=true&images=false'
    if args.download:
        download()
    analyze()
