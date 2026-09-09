"""One no-cost forward observation cycle: source -> features -> score -> ledger.

No wagers or external messages are sent. Aggregator prices remain observational.
A single durable text ledger snapshot can be versioned with git without billing.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import fcntl
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import numpy as np
from .covers import collect
from .features import build_live_snapshot
from .model import ResidualLogistic
from .monitor import Monitor, parse_time


def open_ledger(day, state_root, ledger_root):
    Path(state_root).mkdir(parents=True, exist_ok=True)
    db=Path(state_root)/f'{day}.sqlite3'
    archive=Path(ledger_root)/f'{day}.sql'
    if not db.exists() and archive.exists():
        # A failed restore must not leave a partial DB that looks initialized.
        descriptor, name = tempfile.mkstemp(prefix=f'{day}-restore-', suffix='.sqlite3', dir=state_root)
        os.close(descriptor)
        temporary = Path(name)
        try:
            connection=sqlite3.connect(temporary)
            try:
                connection.executescript(archive.read_text())
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'models', 'quotes', 'predictions', 'decisions', 'settlements'} <= tables:
                    raise ValueError('Incomplete ledger archive schema')
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Ledger archive failed integrity check')
            finally: connection.close()
            try: os.link(temporary, db)
            except FileExistsError: pass
        finally: temporary.unlink(missing_ok=True)
    return Monitor(db)


def open_forward_ledger(state_root, ledger_root):
    """The same model registry and event history survive every calendar day."""
    return open_ledger('forward', state_root, ledger_root)


def export_ledger(monitor, destination):
    # Database rows remain append-only. The exported complete snapshot is versioned.
    destination=Path(destination)
    temporary=destination.with_suffix('.tmp')
    temporary.write_text('\n'.join(monitor.db.iterdump())+'\n')
    temporary.replace(destination)


def score_quotes(monitor, quotes, snapshots, artifact, artifact_sha, now=None):
    model=ResidualLogistic.from_dict(artifact['model'])
    mapping={row['event_id']:row for row in snapshots}
    if len(mapping)!=len(snapshots): raise ValueError('Duplicate feature event IDs')
    results=[]
    for quote in quotes:
        instant=now or datetime.now(timezone.utc)
        quote_id=monitor.ingest_quote(quote, now=instant)['quote_id']
        row=mapping.get(quote['event_id'])
        if row is None or not row.get('input_data_complete',False):
            results.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['missing_or_incomplete_features']})
            continue
        if (row.get('home_team_id') != quote.get('home_team_id') or
            row.get('away_team_id') != quote.get('away_team_id') or
            parse_time(row['start_time']) != parse_time(quote['starts_at'])):
            results.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['feature_quote_identity_or_schedule_mismatch']})
            continue
        cutoff=parse_time(row['feature_cutoff_at'])
        observed=parse_time(quote['observed_at'])
        if cutoff>observed or not 0<=(instant-cutoff).total_seconds()<=36*3600:
            results.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['feature_time_invalid']})
            continue
        if row['model_feature_version'] != 'mlb_lagged_workload_v1':
            raise ValueError('Unexpected feature version; freeze and validate a new model')
        x=np.array([[row[col] for col in artifact['feature_columns']]],dtype=float)
        dh,da=quote['decimal_home'],quote['decimal_away']
        market=(1/dh)/(1/dh+1/da)
        prediction={'event_id':quote['event_id'],'model_id':artifact['model_id'],
                    'artifact_sha256':artifact_sha,'probability_home':float(model.predict_proba(x,[market])[0]),
                    'generated_at':instant.isoformat(),'feature_cutoff_at':cutoff.isoformat(),
                    'market_quote_id':quote_id,'feature_snapshot_sha256':hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest(),
                    'cohort_id':'aggregator-observation-v1'}
        results.append(monitor.predict(prediction,now=instant))
    return results


def settle_from_schedule(monitor,schedule,seen_at,source_uri):
    pending={r[0] for r in monitor.db.execute('SELECT DISTINCT event_id FROM quotes WHERE event_id NOT IN (SELECT event_id FROM settlements)')}
    count=0
    for day in schedule.get('dates',[]):
        for game in day.get('games',[]):
            event=f'mlb:{game["gamePk"]}'
            if event not in pending or game.get('status',{}).get('detailedState') != 'Final':
                continue
            if any(game.get(key) for key in ('rescheduleDate', 'resumeDate', 'resumedFrom')): continue
            innings = game.get('linescore', {}).get('currentInning')
            if (game.get('gameType') != 'R' or game.get('scheduledInnings') != 9 or game.get('doubleHeader') != 'N'
                    or type(innings) is not int or innings < 9): continue
            h=game['teams']['home'].get('score'); a=game['teams']['away'].get('score')
            if not all(type(score) is int and score >= 0 for score in (h, a)) or h==a: continue
            quote = json.loads(monitor._latest_quote(event)['payload'])
            if any(quote.get(f'{side}_team_id') != game['teams'][side]['team']['id'] for side in ('home', 'away')):
                continue
            monitor.settle({'event_id':event,'status':'final','home_won':h>a,
                            'settled_at':seen_at,'source':{'uri':game.get('_source_uri',source_uri),
                            'provider':'MLB official final schedule','verified':True,
                            'verification_method':'Official MLB final score; hypothetical full-game settlement, not sportsbook grade'}},
                           now=parse_time(seen_at))
            pending.remove(event); count+=1
    return count


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def _outstanding(monitor):
    return {row[0] for row in monitor.db.execute(
        "SELECT DISTINCT event_id FROM quotes WHERE event_id LIKE 'mlb:%' AND event_id NOT IN (SELECT event_id FROM settlements)")}


def _run(state_root, ledger_root, model_path, report_root, now):
    state=Path(state_root); state.mkdir(parents=True,exist_ok=True)
    ledger=Path(ledger_root); ledger.mkdir(parents=True,exist_ok=True)
    instant = now or datetime.now(timezone.utc)
    today=instant.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    monitor=open_forward_ledger(state,ledger)
    artifact={}; snapshots=[]; decisions=[]; status={}; observation_error=None
    legacy_days = {path.stem for path in ledger.glob('????-??-??.sql')}
    legacy_days.update(path.stem for path in state.glob('????-??-??.sqlite3'))
    legacy_archives = [ledger/f'{day}.sql' for day in sorted(legacy_days)]
    legacy_events=set(); outstanding=set(); legacy_errors={}; report_days={}
    before_count=monitor.db.execute('SELECT count(*) FROM predictions').fetchone()[0]
    try:
        # Original daily ledgers remain separate evidence. Do not silently merge
        # conflicting registrations or count an old event again in the new one.
        for archive in legacy_archives:
            try:
                m=open_ledger(archive.stem,state,ledger)
                try:
                    legacy_events.update(row[0] for row in m.db.execute('SELECT DISTINCT event_id FROM quotes'))
                    outstanding.update(_outstanding(m))
                finally: m.close()
            except Exception as exc: legacy_errors[archive.stem]=type(exc).__name__
        phase='legacy_ledger_check'
        try:
            if legacy_errors: raise ValueError('Legacy ledger unavailable')
            phase='model'
            raw=Path(model_path).read_bytes(); artifact=json.loads(raw); sha=hashlib.sha256(raw).hexdigest()
            phase='features'
            feature_file=ledger/f'{today}-features.json'
            if not feature_file.exists():
                snapshots=build_live_snapshot(state/'mlb',today)
                _write_json(feature_file,snapshots)
            else: snapshots=json.loads(feature_file.read_text())
            # Quote receipt must follow completion of feature acquisition.
            phase='quotes'
            status=collect(state)
            quotes=json.loads((state/'quotes.json').read_text())
            phase='predictions'
            monitor.register_model({'model_id':artifact['model_id'],'research_status':'unproven',
                                    'artifact_sha256':sha,'market_conditioned':True,'artifact':artifact}, now=now)
            for quote in quotes:
                if quote['event_id'] in legacy_events:
                    decisions.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['event_in_legacy_ledger']})
                else:
                    decisions.extend(score_quotes(monitor,[quote],snapshots,artifact,sha,now=now))
        except Exception as exc:
            observation_error={'phase':phase,'error_type':type(exc).__name__}
            status={'observed_at':instant.isoformat(),'status':'blocked','reason':'observation_cycle_failed'}
        finally:
            export_ledger(monitor,ledger/'forward.sql')
        # Outcome acquisition is independent of feature, model and quote failure.
        outstanding.update(_outstanding(monitor))
        settlement_error=None; schedule={'dates':[]}; settled=0
        uri='https://statsapi.mlb.com/api/v1/schedule'
        invalid_pending = sorted(event for event in outstanding if not event.split(':',1)[1].isdigit())
        try:
            ids=sorted({event.split(':',1)[1] for event in outstanding}-
                       {event.split(':',1)[1] for event in invalid_pending},key=int)
            for start in range(0,len(ids),100):
                uri='https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=linescore&gamePks='+','.join(ids[start:start+100])
                with urlopen(uri,timeout=30) as response: batch=json.loads(response.read())
                for day_record in batch.get('dates',[]):
                    for game in day_record.get('games',[]): game['_source_uri']=uri
                    schedule['dates'].append(day_record)
        except Exception as exc: settlement_error=type(exc).__name__
        seen=now or datetime.now(timezone.utc)
        try: settled+=settle_from_schedule(monitor,schedule,seen.isoformat(),uri)
        except Exception as exc: settlement_error=type(exc).__name__
        finally: export_ledger(monitor,ledger/'forward.sql')
        for archive in legacy_archives:
            if archive.stem in legacy_errors: continue
            m=open_ledger(archive.stem,state,ledger)
            try:
                settled+=settle_from_schedule(m,schedule,seen.isoformat(),uri)
                report_days[archive.stem]=m.report(now=seen)
            except Exception as exc: legacy_errors[archive.stem]=type(exc).__name__
            finally:
                export_ledger(m,archive)
                m.close()
        cumulative=monitor.report(now=seen)
        recorded=monitor.db.execute('SELECT count(*) FROM predictions').fetchone()[0]-before_count
    finally: monitor.close()
    public_status={k:v for k,v in status.items() if k not in {'raw_snapshot','schedule_snapshot'}}
    public_status.update({'model_id':artifact.get('model_id'),'model_training_through':artifact.get('training_through'),
        'feature_snapshots':len(snapshots),'decision_counts':dict(Counter(d['kind'] for d in decisions)),
        'prediction_rows_recorded':recorded,'observation_error':observation_error,
        'settlements_added':settled,'settlement_error':settlement_error,
        'legacy_ledger_errors':legacy_errors,'invalid_pending_event_ids':invalid_pending,
        'ledger_archive':'forward.sql',
        'monitor_mode':'aggregator paper observations; model unproven',
        'betting_alerts_enabled':False,'notifications_sent':0})
    _write_json(Path(report_root)/'live-status.json',public_status)
    _write_json(Path(report_root)/'forward-report.json',{
        'assessment':'No proven edge. Prospective aggregator observations are not execution-verified evidence.',
        'scope':'One cumulative ledger; original daily ledgers are separate legacy evidence, never pooled.',
        'cumulative':cumulative,'legacy_days':report_days})
    _write_json(Path(report_root)/'latest-decisions.json',decisions)
    return public_status


def run(state_root='state',ledger_root='forward-data',model_path='reports/physical_model.json',report_root='reports',now=None):
    """One writer owns both local state and its shared durable export."""
    Path(state_root).mkdir(parents=True,exist_ok=True)
    Path(ledger_root).mkdir(parents=True,exist_ok=True)
    # The existing *.sqlite* ignore rule excludes the shared coordination file.
    with (Path(state_root)/'forward.lock').open('a') as state_lock, \
            (Path(ledger_root)/'.forward.sqlite3.lock').open('a') as export_lock:
        fcntl.flock(state_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(export_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run(state_root,ledger_root,model_path,report_root,now)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',default='state'); parser.add_argument('--ledger',default='forward-data')
    parser.add_argument('--model',default='reports/physical_model.json')
    args=parser.parse_args()
    try:
        result=run(args.state,args.ledger,args.model)
    except Exception as exc:
        # Publish a current failure state rather than leave an old successful status.
        result={'observed_at':datetime.now(timezone.utc).isoformat(),
                'status':'blocked','reason':'forward_cycle_failed','error_type':type(exc).__name__,
                'betting_alerts_enabled':False,'research_status':'unproven','notifications_sent':0}
        Path('reports').mkdir(exist_ok=True)
        Path('reports/live-status.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
