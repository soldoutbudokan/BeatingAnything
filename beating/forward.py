"""One no-cost forward observation cycle: source -> features -> score -> ledger.

No wagers or external messages are sent. Aggregator prices remain observational.
Daily text ledger snapshots can be versioned with git without artifact billing.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import numpy as np
from .covers import collect
from .features import build_live_snapshot
from .model import ResidualLogistic
from .monitor import Monitor, parse_time


def open_ledger(day, state_root, ledger_root):
    db=Path(state_root)/f'{day}.sqlite3'
    archive=Path(ledger_root)/f'{day}.sql'
    if not db.exists() and archive.exists():
        connection=sqlite3.connect(db)
        try: connection.executescript(archive.read_text())
        finally: connection.close()
    return Monitor(db)


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
        quote_id=monitor.ingest_quote(quote)['quote_id']
        row=mapping.get(quote['event_id'])
        if row is None or not row.get('input_data_complete',False):
            results.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['missing_or_incomplete_features']})
            continue
        if (row.get('home_team_id') != quote.get('home_team_id') or
            row.get('away_team_id') != quote.get('away_team_id') or
            parse_time(row['start_time']) != parse_time(quote['starts_at'])):
            results.append({'event_id':quote['event_id'],'kind':'BLOCKED','reasons':['feature_quote_identity_or_schedule_mismatch']})
            continue
        instant=now or datetime.now(timezone.utc)
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
            if event not in pending or game.get('status',{}).get('detailedState') not in {'Final','Completed Early'}:
                continue
            if game.get('rescheduleDate'): continue
            h=game['teams']['home'].get('score'); a=game['teams']['away'].get('score')
            if h is None or a is None or h==a: continue
            monitor.settle({'event_id':event,'status':'final','home_won':h>a,
                            'settled_at':seen_at,'source':{'uri':game.get('_source_uri',source_uri),
                            'provider':'MLB official final schedule','verified':True,
                            'verification_method':'Official MLB final score; hypothetical full-game settlement, not sportsbook grade'}})
            pending.remove(event); count+=1
    return count


def run(state_root='state',ledger_root='forward-data',model_path='reports/physical_model.json'):
    state=Path(state_root); state.mkdir(parents=True,exist_ok=True)
    ledger=Path(ledger_root); ledger.mkdir(parents=True,exist_ok=True)
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    raw=Path(model_path).read_bytes(); artifact=json.loads(raw); sha=hashlib.sha256(raw).hexdigest()
    feature_file=ledger/f'{today}-features.json'
    if not feature_file.exists():
        snapshots=build_live_snapshot(state/'mlb',today)
        feature_file.write_text(json.dumps(snapshots,indent=2)+'\n')
    else: snapshots=json.loads(feature_file.read_text())
    # Quote receipt must follow completion of feature acquisition.
    status=collect(state)
    quotes=json.loads((state/'quotes.json').read_text())
    monitor=open_ledger(today,state,ledger)
    try:
        monitor.register_model({'model_id':artifact['model_id'],'research_status':'unproven',
                                'artifact_sha256':sha,'market_conditioned':True,'artifact':artifact})
        decisions=score_quotes(monitor,quotes,snapshots,artifact,sha)
        export_ledger(monitor,ledger/f'{today}.sql')
    finally: monitor.close()
    # Grade observed events with official outcomes. Retries do not revise settled rows.
    outstanding=set()
    for archive in sorted(ledger.glob('????-??-??.sql')):
        m=open_ledger(archive.stem,state,ledger)
        try:
            outstanding.update(row[0].split(':',1)[1] for row in m.db.execute(
                "SELECT DISTINCT event_id FROM quotes WHERE event_id LIKE 'mlb:%' AND event_id NOT IN (SELECT event_id FROM settlements)"))
        finally: m.close()
    settlement_error=None; schedule={'dates':[]}; settled=0
    uri='https://statsapi.mlb.com/api/v1/schedule'
    try:
        ids=sorted(outstanding,key=int)
        for start in range(0,len(ids),100):
            uri='https://statsapi.mlb.com/api/v1/schedule?sportId=1&gamePks='+','.join(ids[start:start+100])
            with urlopen(uri,timeout=30) as response: batch=json.loads(response.read())
            for day_record in batch.get('dates',[]):
                for game in day_record.get('games',[]): game['_source_uri']=uri
                schedule['dates'].append(day_record)
    except Exception as exc: settlement_error=type(exc).__name__
    seen=datetime.now(timezone.utc).isoformat()
    report_days={}
    for archive in sorted(ledger.glob('????-??-??.sql')):
        day=archive.stem; m=open_ledger(day,state,ledger)
        try:
            changed=settle_from_schedule(m,schedule,seen,uri)
            settled+=changed
            if changed: export_ledger(m,archive)
            report_days[day]=m.report()
        finally: m.close()
    public_status={k:v for k,v in status.items() if k not in {'raw_snapshot','schedule_snapshot'}}
    public_status.update({'model_id':artifact['model_id'],'model_training_through':artifact['training_through'],
        'feature_snapshots':len(snapshots),'decision_counts':dict(Counter(d['kind'] for d in decisions)),
        'prediction_rows_recorded':sum('prediction_id' in d for d in decisions),
        'settlements_added':settled,'settlement_error':settlement_error,
        'monitor_mode':'aggregator paper observations; model unproven',
        'betting_alerts_enabled':False,'notifications_sent':0})
    Path('reports').mkdir(exist_ok=True)
    Path('reports/live-status.json').write_text(json.dumps(public_status,indent=2)+'\n')
    Path('reports/forward-report.json').write_text(json.dumps({'assessment':'No proven edge. Prospective aggregator observations are not execution-verified evidence.',
                                                            'days':report_days},indent=2)+'\n')
    Path('reports/latest-decisions.json').write_text(json.dumps(decisions,indent=2)+'\n')
    return public_status


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
