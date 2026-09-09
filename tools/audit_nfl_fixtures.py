"""Metadata-only feasibility. Never reads result, score or model-summary fields."""
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'data/raw/nfl-fixture-feasibility'
OUTPUT.mkdir(parents=True, exist_ok=True)
RAW = OUTPUT/'fixture-source-uninspected-results.csv'
DB = ROOT/'data/raw/nfl-source-audit/nfl_odds.duckdb'
SOURCE = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
EASTERN = ZoneInfo('America/New_York')
NAMES = dict(zip(
    ['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears',
     'Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers',
     'Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Las Vegas Raiders',
     'Los Angeles Chargers','Los Angeles Rams','Miami Dolphins','Minnesota Vikings','New England Patriots',
     'New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers',
     'San Francisco 49ers','Seattle Seahawks','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders'],
    ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LA',
     'MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS']))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def stamp(value):
    return value.astimezone(timezone.utc).isoformat()


def dump(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n')


fields = ('game_id','season','game_type','week','gameday','gametime','home_team','away_team','old_game_id','gsis','nfl_detail_id')
# Drop every nonmetadata column before inspecting any rows.
with RAW.open() as handle:
    metadata = [{key: row.get(key) for key in fields} for row in csv.DictReader(handle)]
metadata = [row for row in metadata if row['season']=='2025' and row['game_type'] in {'REG','WC','DIV','CON','SB'}]
dump(OUTPUT/'fixture-metadata.json', metadata)
# Keep original bytes unchanged for hash verification; do not display or use other fields.
fixtures = {}
fixture_errors = []
by_teams = defaultdict(list)
for row in metadata:
    try:
        naive = datetime.fromisoformat(row['gameday']+'T'+row['gametime'])
        kickoff = naive.replace(tzinfo=EASTERN).astimezone(timezone.utc)
        if row['game_id'] in fixtures:
            raise ValueError('duplicate_fixture_id')
        fixtures[row['game_id']] = {**row, 'kickoff':kickoff}
        by_teams[row['home_team'],row['away_team']].append(row['game_id'])
    except (ValueError, TypeError) as exc:
        fixture_errors.append({'game_id':row['game_id'],'reason':str(exc)})

connection = duckdb.connect()
connection.execute("ATTACH '"+str(DB).replace("'", "''")+"' AS nfl_odds (READ_ONLY)")
# raw_odds contains quoted outcome names/prices, not realized game outcomes.
# Never query fct_game_summary/fct_season_summary or any score/result columns.
columns = ('captured_at','event_id','commence_time','home_team','away_team','bookmaker_last_update','outcome_name','outcome_price','outcome_point')
raw_rows = connection.execute('SELECT '+','.join(columns)+" FROM nfl_odds.main.raw_odds WHERE sport_key='americanfootball_nfl' AND bookmaker_key='fanduel' AND market_key='h2h'").fetchall()
reference_rows = connection.execute('SELECT '+','.join(columns)+" FROM nfl_odds.main.raw_odds WHERE sport_key='americanfootball_nfl' AND bookmaker_key='pinnacle' AND market_key='h2h'").fetchall()
connection.close()
groups = defaultdict(list)
reference_groups = defaultdict(list)
rejections = []
row_errors = Counter()
for values in raw_rows:
    row = dict(zip(columns,values))
    if any(row[key] is None for key in ('captured_at','event_id','commence_time','home_team','away_team')):
        row_errors['missing_identity_or_timestamp'] += 1
        rejections.append({'kind':'row','event_id':row['event_id'],'reason':'missing_identity_or_timestamp'})
        continue
    # The extracter's dates are explicitly UTC; DuckDB TIMESTAMP erased tzinfo.
    capture = row['captured_at'].replace(tzinfo=timezone.utc)
    source_start = row['commence_time'].replace(tzinfo=timezone.utc)
    key = row['event_id'],capture,source_start,row['home_team'],row['away_team']
    groups[key].append(row)

for values in reference_rows:
    row = dict(zip(columns, values))
    if any(row[key] is None for key in ('captured_at','event_id','commence_time','home_team','away_team')):
        rejections.append({'kind':'reference_row','event_id':row['event_id'],'reason':'missing_identity_or_timestamp'})
        continue
    key = (row['event_id'], row['captured_at'].replace(tzinfo=timezone.utc),
           row['commence_time'].replace(tzinfo=timezone.utc), row['home_team'], row['away_team'])
    reference_groups[key].append(row)

candidate_mappings = {}
source_event_fixtures = defaultdict(set)
source_event_teams = defaultdict(set)
for key in set(groups) | set(reference_groups):
    event,capture,source_start,home,away = key
    source_event_teams[event].add((home, away))
    if home not in NAMES or away not in NAMES or home==away:
        candidate_mappings[key] = []
        continue
    matched = [game for game in by_teams[NAMES[home],NAMES[away]]
               if abs((fixtures[game]['kickoff']-source_start).total_seconds()) <= 900]
    candidate_mappings[key] = matched
    if len(matched)==1:
        source_event_fixtures[event].add(matched[0])

boundaries = {game:row['kickoff'] for game,row in fixtures.items()}
for key,matched in candidate_mappings.items():
    # Once identity is uniquely bound, even an out-of-tolerance source revision
    # may tighten the cutoff. It cannot make its own rejected snapshot eligible.
    if len(source_event_fixtures[key[0]])==1 and len(source_event_teams[key[0]])==1:
        game=next(iter(source_event_fixtures[key[0]]))
        boundaries[game] = min(boundaries[game],key[2])

pair_audit = Counter()
reference_audit = Counter()
mapped_events = set()
valid = defaultdict(list)
valid_reference = defaultdict(list)
all_game_reasons = defaultdict(Counter)
source_starts = defaultdict(set)
for bookmaker, book_groups in (('fanduel', groups), ('pinnacle', reference_groups)):
 for key, values in sorted(book_groups.items()):
    event,capture,source_start,home,away = key
    matched = candidate_mappings[key]
    reasons=[]
    game = matched[0] if len(matched)==1 else None
    if not matched: reasons.append('no_unique_fixture_within_15_minutes')
    elif len(matched)>1: reasons.append('ambiguous_independent_fixture')
    elif len(source_event_fixtures[event])!=1: reasons.append('source_event_maps_to_multiple_fixtures')
    if len(source_event_teams[event])!=1: reasons.append('source_event_has_conflicting_team_identity')
    if not reasons:
        if bookmaker == 'fanduel':
            mapped_events.add(event)
            source_starts[game].add(source_start)
    sides=defaultdict(set)
    updates=set()
    for row in values:
        if row['outcome_name'] not in {home,away}:
            reasons.append('unknown_h2h_side')
        price=row['outcome_price']
        if not isinstance(price,(int,float)) or not math.isfinite(price) or abs(price)<100:
            reasons.append('invalid_american_price')
        else:
            decimal=1+price/100 if price>0 else 1+100/abs(price)
            sides[row['outcome_name']].add(decimal)
        if row['outcome_point'] is not None:
            reasons.append('h2h_has_point_line')
        if row['bookmaker_last_update'] is None:
            reasons.append('missing_book_update')
        else: updates.add(row['bookmaker_last_update'].replace(tzinfo=timezone.utc))
    if set(sides)!={home,away} or any(len(prices)!=1 for prices in sides.values()):
        reasons.append('incomplete_or_conflicting_pair')
    if len(updates)!=1:
        reasons.append('inconsistent_or_missing_book_update')
    else:
        age=(capture-next(iter(updates))).total_seconds()
        if not 0<=age<=90: reasons.append('book_update_age_outside_0_to_90_seconds')
    if set(sides)=={home,away} and all(len(prices)==1 for prices in sides.values()):
        vig=sum(1/next(iter(prices)) for prices in sides.values())-1
        if not -1e-12<=vig<=.08+1e-12: reasons.append('paired_overround_outside_0_to_8_percent')
    if game and capture>=boundaries[game]: reasons.append('not_before_earliest_scheduled_start')
    reasons=sorted(set(reasons))
    if reasons:
        (pair_audit if bookmaker == 'fanduel' else reference_audit).update(reasons)
        if game and bookmaker == 'fanduel':all_game_reasons[game].update(reasons)
        rejections.append({'kind':'snapshot','bookmaker':bookmaker,'event_id':event,'game_id':game,
                           'captured_at':stamp(capture),'source_start':stamp(source_start),'reasons':reasons})
        continue
    (valid if bookmaker == 'fanduel' else valid_reference)[game].append(
        {'event_id':event,'captured_at':capture,'source_start':source_start, 'key':key,
         'book_update_age_seconds':age,'lead_seconds':(boundaries[game]-capture).total_seconds()})

entry_window_audit = Counter()
for game, observations in valid.items():
    for row in observations:
        reason = ('before_24h_entry_window' if row['lead_seconds']>86400 else
                  'inside_final_1h' if row['lead_seconds']<3600 else 'entry_window_eligible_pair')
        entry_window_audit[reason] += 1
        if reason != 'entry_window_eligible_pair':
            rejections.append({'kind':'entry_window_only','bookmaker':'fanduel','game_id':game,
                               'event_id':row['event_id'],'captured_at':stamp(row['captured_at']),
                               'reason':reason})


def quote_projection(rows):
    """Only raw quote metadata/prices. No fixture result columns were selected."""
    return [{key: stamp(value.replace(tzinfo=timezone.utc)) if isinstance(value,datetime) else value
             for key,value in row.items()} for row in rows]

entries=[]
candidate_quotes=[]
excluded=[]
for game,fixture in sorted(fixtures.items()):
    candidates=[row for row in valid[game] if 3600<=row['lead_seconds']<=86400]
    if not candidates:
        reasons=['no_pair_in_fixed_24h_to_1h_entry_window']
        if not valid[game]:reasons.append('no_valid_fresh_prestart_pair')
        excluded.append({'game_id':game,'reasons':reasons,'snapshot_rejection_counts':dict(all_game_reasons[game])})
        continue
    first_time=min(row['captured_at'] for row in candidates)
    first=[row for row in candidates if row['captured_at']==first_time]
    # Multiple source event IDs are never manually collapsed to increase coverage.
    if len({row['event_id'] for row in first})!=1 or len({row['source_start'] for row in first})!=1:
        excluded.append({'game_id':game,'reasons':['ambiguous_first_eligible_snapshot']})
        continue
    chosen=first[0]
    last=max(valid[game],key=lambda row:row['captured_at'])
    reference_last=max(valid_reference[game],key=lambda row:row['captured_at'],default=None)
    entries.append({'game_id':game,'event_id':chosen['event_id'],'game_type':fixture['game_type'],
                    'week':int(fixture['week']),
                    'entry_at':stamp(chosen['captured_at']),'boundary':stamp(boundaries[game]),
                    'entry_lead_seconds':chosen['lead_seconds'],
                    'last_prestart_lead_seconds':(fixture['kickoff']-last['captured_at']).total_seconds(),
                    'last_prestart_lead_to_earliest_boundary_seconds':last['lead_seconds'],
                    'pinnacle_last_prestart_lead_seconds':(fixture['kickoff']-reference_last['captured_at']).total_seconds() if reference_last else None})
    reference_at_entry = [row for row in valid_reference[game] if row['key']==chosen['key']]
    candidate_quotes.append({**entries[-1], 'fixture':{key:value for key,value in fixture.items() if key!='kickoff'},
         'independent_scheduled_start':stamp(fixture['kickoff']),
         'fanduel_entry_rows':quote_projection(groups[chosen['key']]),
         'pinnacle_same_event_capture_rows':quote_projection([row for key, rows in reference_groups.items()
             if key[:2]==chosen['key'][:2] for row in rows]),
         'pinnacle_at_entry_meets_same_pair_freshness_vig_gates':bool(reference_at_entry),
         'fanduel_last_prestart_rows':quote_projection(groups[last['key']]),
         'pinnacle_last_prestart_rows':quote_projection(reference_groups[reference_last['key']]) if reference_last else []})

detail_path=OUTPUT/'snapshot-rejections.jsonl'
detail_path.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in rejections))
dump(OUTPUT/'entry-metadata.json',entries)
dump(OUTPUT/'candidate-quote-projection.json',candidate_quotes)
lead=[row['last_prestart_lead_seconds'] for row in entries]
coverage={str(seconds):sum(value<=seconds for value in lead) for seconds in (60,90,300,900,1800,3600,10800)}
reference_lead=[row['pinnacle_last_prestart_lead_seconds'] for row in entries if row['pinnacle_last_prestart_lead_seconds'] is not None]
reference_coverage={str(seconds):sum(value<=seconds for value in reference_lead) for seconds in (60,90,300,900,1800,3600,10800)}
week_counts=[]
for week in sorted({row['week'] for row in metadata},key=int):
    selected=[row for row in entries if row['week']==int(week)]
    week_counts.append({'week':int(week),'fixtures':sum(row['week']==week for row in metadata),
        'entries':len(selected),'game_types':sorted({row['game_type'] for row in selected}),
        'fanduel_last_lead_le_30m':sum(row['last_prestart_lead_seconds']<=1800 for row in selected),
        'pinnacle_last_lead_le_30m':sum(row['pinnacle_last_prestart_lead_seconds'] is not None and row['pinnacle_last_prestart_lead_seconds']<=1800 for row in selected),
        'pinnacle_last_lead_missing':sum(row['pinnacle_last_prestart_lead_seconds'] is None for row in selected)})
report={'scope':'Metadata-only feasibility, not a registered experiment; no game-result labels, models, EV, returns or CLV computed',
 'generated_at':datetime.now(timezone.utc).isoformat(),'season':2025,
 'runtime':{'python':sys.version.split()[0],'duckdb':duckdb.__version__},
 'sources':{'fixture_url':SOURCE,'fixture_raw_sha256':sha(RAW),'fixture_metadata_sha256':sha(OUTPUT/'fixture-metadata.json'),
            'odds_database_path':str(DB),'odds_database_sha256':sha(DB),'audit_script_sha256':sha(__file__),
            'snapshot_rejections_path':str(detail_path),'snapshot_rejections_sha256':sha(detail_path),
            'entry_metadata_path':str(OUTPUT/'entry-metadata.json'),'entry_metadata_sha256':sha(OUTPUT/'entry-metadata.json'),
            'candidate_quote_projection_path':str(OUTPUT/'candidate-quote-projection.json'),
            'candidate_quote_projection_sha256':sha(OUTPUT/'candidate-quote-projection.json')},
 'fixture_source_class':'Public nflverse fixture dataset maintained by Lee Sharpe; independent of the odds archive, not an NFL execution feed',
 'rules':{'fixture_match':'Exact explicit team map, unique ordered home/away fixture within15minutes; ambiguous IDs excluded',
          'boundary':'Earliest independent kickoff or any observed source scheduled start for uniquely bound stable team/event identity; later revisions cannot extend cutoff, even an out-of-tolerance revision can tighten it',
          'entry_window_seconds':[3600,86400],'book_update_age_seconds':[0,90],'paired_overround':[0,.08],
          'quote_pair':'Exact event/capture/source-start/home/away/FanDuel/h2h; two distinct sides, one common book update, no conflict',
          'last_prestart':'Last pair meeting same freshness/pair/overround gates strictly before earliest boundary, among accepted-entry fixtures; lead measured to independent fixture kickoff, so an early obsolete source schedule cannot manufacture a close'},
 'counts':{'fixtures':len(fixtures),'fixtures_by_type':dict(Counter(row['game_type'] for row in fixtures.values())),
           'raw_fanduel_h2h_rows':len(raw_rows),'raw_event_ids':len({row[1] for row in raw_rows}),
           'snapshot_groups':len(groups),'uniquely_mapped_source_events':len(mapped_events),'valid_fresh_prestart_pairs':sum(map(len,valid.values())),
           'accepted_entry_events':len(entries),'accepted_entries_by_type':dict(Counter(row['game_type'] for row in entries)),
           'excluded_entry_events':len(excluded),'fixtures_with_multiple_source_starts':sum(len(values)>1 for values in source_starts.values()),
           'fixtures_with_source_boundary_earlier_than_independent':sum(boundaries[game]<fixture['kickoff'] for game,fixture in fixtures.items())},
 'pair_rejection_counts':dict(pair_audit),'reference_pair_rejection_counts':dict(reference_audit),
 'entry_window_pair_counts':dict(entry_window_audit),
 'invalid_row_counts':dict(row_errors),'fixture_errors':fixture_errors,
 'excluded_entry_events':excluded,'last_prestart_lead_coverage_seconds':coverage,
 'pinnacle_last_prestart_lead_coverage_seconds':reference_coverage,
 'pinnacle_last_prestart_missing':len(entries)-len(reference_lead),
 'pinnacle_at_entry_same_gates':sum(row['pinnacle_at_entry_meets_same_pair_freshness_vig_gates'] for row in candidate_quotes),
 'coverage_by_nfl_week':week_counts,
 'last_prestart_lead_seconds':{'minimum':min(lead) if lead else None,'median':statistics.median(lead) if lead else None,'maximum':max(lead) if lead else None},
 'team_identity_map':NAMES,'limitations':['Historical fixture revisions and kickoff publication vintage are unverified.',
 'Bookmaker last_update is publisher metadata, not proof of executable local FanDuel availability.',
 'No missing-close filtering, strategy selection, probability forecasts, sport labels, game returns or significance analysis performed.']}
dump(ROOT/'reports/nfl-fixture-feasibility.json',report)
print(json.dumps({key:report[key] for key in ('counts','pair_rejection_counts','last_prestart_lead_coverage_seconds','last_prestart_lead_seconds')},indent=2))
