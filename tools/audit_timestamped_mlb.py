"""Independent F1 audit: stdlib arithmetic, no imports from beating."""
import argparse, csv, json, math, hashlib, datetime as dt, statistics
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
ROOT = parser.parse_args().root.resolve()
SOURCE = ROOT/'data/raw/mlb-2026-f1'
REPORT = ROOT/'reports'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
stamp=lambda s:dt.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(dt.timezone.utc)
num=lambda s:float(s) if s not in ('',None) else None
mean=lambda a:statistics.fmean(a) if a else None
near=lambda a,b: (a is None and b is None) or (a is not None and b is not None and math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-12))
name=lambda s:'Athletics' if s=='Oakland Athletics' else s
errors=[]
checks=Counter()
def check(label, truth, detail=None):
    checks['checks']+=1
    if not truth:errors.append({'check':label,'detail':detail})
def eq(label,a,b):check(label,near(a,b) if isinstance(a,(int,float)) and not isinstance(a,bool) else a==b, {'actual':a,'expected':b})

metrics=read(REPORT/'timestamped-mlb-metrics.json')
artifact=read(REPORT/'physical_model.json')
features=read(REPORT/'timestamped-mlb-features.json')
forecasts=list(csv.DictReader((REPORT/'timestamped-mlb-forecasts.csv').open()))
raw=list(csv.DictReader((ROOT/'data/raw/oddsgap-mlb-f1.csv').open()))
hashes={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/raw/oddsgap-mlb-f1.csv',REPORT/'timestamped-mlb-forecasts.csv',REPORT/'timestamped-mlb-metrics.json',REPORT/'timestamped-mlb-features.json',REPORT/'physical_model.json',ROOT/'docs/protocol-mlb-timestamped-v1.md',ROOT/'requirements-lock.txt',SOURCE/'source_manifest.json',SOURCE/'first-pitch/manifest.json']}
for key,path in [('odds_sha256','data/raw/oddsgap-mlb-f1.csv'),('forecasts_sha256','reports/timestamped-mlb-forecasts.csv'),('model_sha256','reports/physical_model.json'),('protocol_sha256','docs/protocol-mlb-timestamped-v1.md')]:
    eq('frozen_'+key,hashes[path],metrics['sources'][key])
eq('original_export_sha',hashes['data/raw/oddsgap-mlb-f1.csv'],'3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e')
eq('original_artifact_sha',hashes['reports/physical_model.json'],'c035a7a44c70dc7f16db6624ffebe1b691f2bd76177dfeaf1548813003540f5f')
eq('model_id',artifact['model_id'],'a7ceefe2db3c13ea')
eq('training_through',artifact['training_through'],'2025-08-16')
manifest=read(SOURCE/'source_manifest.json')
eq('official_manifest_embedded',manifest,metrics['sources']['official_manifest'])
for f in manifest['files']:
    p=SOURCE/f['file'];eq('source_hash_'+f['file'],sha(p),f['sha256']);eq('source_bytes_'+f['file'],p.stat().st_size,f['bytes'])
pitch_manifest=read(SOURCE/'first-pitch/manifest.json')
eq('first_pitch_manifest_embedded',pitch_manifest,metrics['sources']['first_pitch_manifest'])
pitches={}
for r in pitch_manifest['rows']:
    if r['status']!='retrieved':continue
    p=SOURCE/'first-pitch'/f"{r['game_pk']}.json";eq('pitch_source_hash_'+str(r['game_pk']),sha(p),r['sha256'])
    payload=read(p);eq('pitch_game_id',payload['gamePk'],r['game_pk'])
    times=[stamp(e['startTime']) for play in payload.get('liveData',{}).get('plays',{}).get('allPlays',[]) for e in play.get('playEvents',[]) if e.get('isPitch') is True and e.get('startTime')]
    first=min(times) if times else None
    eq('literal_first_pitch_'+str(r['game_pk']),first.isoformat() if first else None,r['first_pitch_at'])
    if first:pitches[r['game_pk']]=first

# Independently group official fixture identities, never source-price endpoints.
schedule=read(SOURCE/'schedule_2026.json');by_pk=defaultdict(list)
for day in schedule['dates']:
    for game in day['games']:by_pk[game['gamePk']].append(game)
def identity(g):
    return (g['gameDate'],g['officialDate'],g.get('gameType'),g.get('scheduledInnings'),g.get('doubleHeader'),g['venue']['id'],*((g['teams'][s]['team']['id'],name(g['teams'][s]['team']['name'])) for s in ['home','away']))
ambiguous={pk for pk,gs in by_pk.items() if len({identity(g) for g in gs})>1}
games={pk:gs[-1] for pk,gs in by_pk.items()}
by_team=defaultdict(list)
for pk,g in games.items():by_team[(name(g['teams']['home']['team']['name']),name(g['teams']['away']['team']['name']))].append(pk)

# Pair raw American prices using exact raw timestamps, never supplied fair fields.
counts=Counter();groups=defaultdict(lambda:defaultdict(set));group_rows=Counter();invalid=set()
for r in raw:
    counts['source_rows']+=1
    if r['sport']!='baseball_mlb' or r['market']!='ml' or r['line']:
        counts['out_of_scope_rows']+=1;continue
    if r['book'] not in {'fanduel','pinnacle'}:
        counts['other_book_rows']+=1;continue
    k=(name(r['home']),name(r['away']),stamp(r['commence_time']),stamp(r['snapshot_ts']),r['book'])
    american=float(r['american_odds']);group_rows[k]+=1
    if r['side'] not in {'home','away'} or not math.isfinite(american) or abs(american)<100:
        invalid.add(k);counts['invalid_rows']+=1;continue
    decimal=1+american/100 if american>0 else 1+100/abs(american)
    groups[k][r['side']].add(decimal)
pairs=[]
for k,sides in groups.items():
    if k in invalid:counts['invalid_side_row_pairs']+=1;continue
    if set(sides)!={'home','away'} or any(len(x)!=1 for x in sides.values()):counts['incomplete_or_conflicting_pairs']+=1;continue
    if k[3]>=k[2]:counts['at_or_after_source_start_pairs']+=1;continue
    a,b=next(iter(sides['home'])),next(iter(sides['away']))
    pair={'home':k[0],'away':k[1],'start':k[2],'at':k[3],'book':k[4],'a':a,'b':b,'vig':1/a+1/b-1,'prob':b/(a+b)}
    pairs.append(pair);counts['identical_duplicate_side_rows']+=group_rows[k]-2
counts['paired_snapshots']=len(pairs)
mapped=[]
for p in pairs:
    matches=[pk for pk in by_team[(p['home'],p['away'])] if abs((stamp(games[pk]['gameDate'])-p['start']).total_seconds())<=900]
    if len(matches)!=1:counts['unmatched_or_ambiguous_schedule_pairs']+=1;continue
    pk=matches[0];g=games[pk]
    if pk in ambiguous or g.get('gameType')!='R' or g.get('scheduledInnings')!=9 or g.get('doubleHeader')!='N':counts['outside_model_fixture_contract_pairs']+=1;continue
    official=stamp(g['gameDate'])
    if p['at']>=official:counts['at_or_after_official_start_pairs']+=1;continue
    if pk in pitches and p['at']>=pitches[pk]:counts['at_or_after_recorded_first_pitch_pairs']+=1;continue
    mapped.append(dict(p,pk=pk,official=official,date=g['officialDate']))
counts['mapped_pairs']=len(mapped)
eligible=defaultdict(list)
for p in mapped:
    if p['book']!='fanduel':continue
    counts['fanduel_mapped_pairs']+=1
    lead=(p['start']-p['at']).total_seconds()
    if not 1800<=lead<=21600:counts['outside_entry_time_window_pairs']+=1
    elif p['at'].astimezone(ZoneInfo('America/New_York')).date().isoformat()!=p['date']:counts['entry_not_on_official_calendar_date_pairs']+=1
    elif not -1e-10<=p['vig']<=.08+1e-10:counts['entry_overround_invalid_pairs']+=1
    else:eligible[p['pk']].append(p)
entries={}
for pk,ps in eligible.items():
    first_time=min(p['at'] for p in ps);first=[p for p in ps if p['at']==first_time]
    if len({(p['start'],p['a'],p['b']) for p in first})>1:counts['conflicting_first_event_snapshot']+=1
    else:entries[pk]=first[0]
counts['entry_events']=len(entries)
for k in set(counts)|set(metrics['audit']):eq('reconciliation_'+k,counts[k],metrics['audit'].get(k,0))
eq('canonical_forecast_events',{r['event_id'] for r in forecasts},{'mlb:'+str(pk) for pk in entries})
eq('no_repeated_forecasts',len({r['event_id'] for r in forecasts}),len(forecasts))
eq('no_repeated_feature_ids',len({f['game_pk'] for f in features}),len(features))
feature_map={f['game_pk']:f for f in features}
errors_p=[];entry_leads=[];close_leads=defaultdict(list);outcomes=Counter();unknown_ids=[];close_missing=defaultdict(list);missing_control=[]
for r in forecasts:
    pk=int(r['game_pk']);p=entries[pk];g=games[pk];f=feature_map[pk]
    eq('event_id_'+str(pk),r['event_id'],'mlb:'+str(pk));eq('date_'+str(pk),r['date'],g['officialDate'])
    eq('entry_time_'+str(pk),stamp(r['entry_observed_at']),p['at']);eq('entry_source_start_'+str(pk),stamp(r['source_start_at_entry']),p['start'])
    eq('entry_official_start_'+str(pk),stamp(r['official_start']),p['official'])
    for col,v in [('odds_a',p['a']),('odds_b',p['b']),('market_p',p['prob'])]:eq('entry_'+col+'_'+str(pk),num(r[col]),v)
    first=pitches.get(pk);eq('recorded_first_pitch_'+str(pk),stamp(r['recorded_first_pitch_at']) if r['recorded_first_pitch_at'] else None,first)
    entry_leads.append((p['start']-p['at']).total_seconds()/60)
    controls=[t for t in mapped if t['pk']==pk and t['book']=='pinnacle' and t['at']==p['at'] and t['start']==p['start'] and -1e-10<=t['vig']<=.15+1e-10]
    control=controls[0]['prob'] if len({(t['a'],t['b']) for t in controls})==1 else None
    eq('control_prob_'+str(pk),num(r['p_pinnacle']),control)
    if control is None:missing_control.append(r['event_id'])
    for book in ['pinnacle','fanduel']:
        candidates=[]
        for t in mapped:
            if t['pk']!=pk or t['book']!=book:continue
            bound=min(t['official'],t['start'],p['start'],pitches.get(pk,dt.datetime.max.replace(tzinfo=dt.timezone.utc)))
            lag=(bound-t['at']).total_seconds()
            if 60<=lag<=1800 and t['at']>=p['at'] and -1e-10<=t['vig']<=.15+1e-10:candidates.append((t,lag))
        latest=[]
        if candidates:
            last=max(t['at'] for t,_ in candidates);latest=[(t,lag) for t,lag in candidates if t['at']==last]
        chosen=latest[0] if len({(t['a'],t['b']) for t,_ in latest})==1 else None
        if chosen:
            t,lag=chosen;close_leads[book].append(lag/60)
            eq('close_time_'+book+'_'+str(pk),stamp(r[book+'_close_at']),t['at'])
            eq('close_home_'+book+'_'+str(pk),num(r[book+'_close_a']),t['a']);eq('close_away_'+book+'_'+str(pk),num(r[book+'_close_b']),t['b'])
        else:
            close_missing[book].append(r['event_id'])
            check('missing_close_preserved_'+book+'_'+str(pk),all(not r[book+x] for x in ['_close_at','_close_a','_close_b']))
    h,a=g['teams']['home'].get('score'),g['teams']['away'].get('score');inning=g.get('linescore',{}).get('currentInning')
    ordinary=(g['status']['detailedState']=='Final' and type(inning)is int and inning>=9 and all(type(s)is int and s>=0 for s in [h,a]) and h!=a and not any(g.get(k) for k in ['rescheduleDate','resumeDate','resumedFrom']))
    y=float(h>a) if ordinary else None
    eq('grading_'+str(pk),num(r['y']),y);outcomes[g['status']['detailedState']]+=1
    if y is None:unknown_ids.append(r['event_id'])
    check('feature_availability_'+str(pk),dt.date.fromisoformat(f['feature_cutoff_date'])<p['at'].astimezone(ZoneInfo('America/New_York')).date())
    eq('feature_cutoff_'+str(pk),f['feature_cutoff_date'],(dt.date.fromisoformat(r['date'])-dt.timedelta(days=1)).isoformat())
    eq('feature_cutoff_forecast_'+str(pk),r['feature_cutoff_date'],f['feature_cutoff_date'])
    check('feature_completeness_'+str(pk),f['feature_travel_complete'] and not f['home_bullpen_recent_missing'] and not f['away_bullpen_recent_missing'])
    eq('feature_version_'+str(pk),f['model_feature_version'],'mlb_lagged_workload_v1')
    vector={c:f[c] for c in artifact['feature_columns']}
    eq('feature_sha_'+str(pk),hashlib.sha256(json.dumps(vector,sort_keys=True).encode()).hexdigest(),r['feature_sha256'])
    for c,v in vector.items():eq('home_away_difference_'+c+'_'+str(pk),v,f[c.replace('diff_','home_',1)]-f[c.replace('diff_','away_',1)])
    model=artifact['model'];eta=math.log(p['prob']/(1-p['prob']))+model['coef'][0]
    eta+=sum(beta*(vector[c]-center)/scale for c,beta,center,scale in zip(artifact['feature_columns'],model['coef'][1:],model['mean'],model['scale']))
    physical=1/(1+math.exp(-eta));errors_p.append(abs(physical-float(r['p_physical'])));eq('frozen_physical_probability_'+str(pk),physical,float(r['p_physical']))

# Plain math metrics. No numpy/scipy/pandas or project evaluator imported.
def loss(y,p):return -math.log(p if y else 1-p)
def fair(a,b,power=False):
    if a is None or b is None or not (a>1 and b>1) or not -1e-10<=1/a+1/b-1<=.15+1e-10:return None
    if not power:return b/(a+b)
    lo,hi=0.,100.
    for _ in range(100):
        mid=(lo+hi)/2
        if (1/a)**mid+(1/b)**mid>1:lo=mid
        else:hi=mid
    return (1/a)**((lo+hi)/2)
def stats(rows,col):
    completed=[r for r in rows if r['y']!=''];ps=[float(r[col]) for r in rows]
    bets=[];evs=[]
    for r,p in zip(rows,ps):
        a,b=float(r['odds_a']),float(r['odds_b']);home=p*a-1>=(1-p)*b-1;price=a if home else b;ev=max(p*a-1,(1-p)*b-1);evs.append(ev)
        if ev>=.03 and 1.2<=price<=6 and -1e-10<=1/a+1/b-1<=.08+1e-10:bets.append((r,home,price))
    graded=[(r,h,o) for r,h,o in bets if r['y']!=''];unknown=[(r,h,o) for r,h,o in bets if r['y']=='']
    profits=[o-1 if h==(float(r['y'])==1) else -1 for r,h,o in graded];haircuts=[.98*(o-1) if h==(float(r['y'])==1) else -1 for r,h,o in graded]
    days=defaultdict(float)
    for (r,h,o),v in zip(graded,profits):days[r['date']]+=v
    balance=peak=drawdown=0
    for day in sorted(days):balance+=days[day];peak=max(peak,balance);drawdown=max(drawdown,peak-balance)
    n=len(bets);out={'events':len(rows),'settled_events':len(completed),'unresolved_events':len(rows)-len(completed),'bets':n,'turnover_units':n,'settled_bets':len(graded),'ungraded_bets':len(unknown),'profit_units_settled':sum(profits),'roi':sum(profits)/n if n and not unknown else None,'haircut_roi':sum(haircuts)/n if n and not unknown else None,'roi_unresolved_outcome_bounds':[(sum(profits)-len(unknown))/n,(sum(profits)+sum(o-1 for r,h,o in unknown))/n] if n else [None,None], 'log_loss':mean([loss(float(r['y']),float(r[col])) for r in completed]),'market_log_loss':mean([loss(float(r['y']),float(r['market_p'])) for r in completed]),'brier':mean([(float(r[col])-float(r['y']))**2 for r in completed]),'paired_log_loss_delta':mean([loss(float(r['y']),float(r[col]))-loss(float(r['y']),float(r['market_p'])) for r in completed]),'max_model_ev':max(evs) if evs else None,'max_drawdown_daily_units':drawdown if not unknown else None,'max_drawdown_daily_settled_units':drawdown,'independent_calendar_weeks':len({(dt.date.fromisoformat(r['date'])-dt.timedelta(days=dt.date.fromisoformat(r['date']).weekday())).isoformat() for r in rows})}
    for book in ['pinnacle','fanduel']:
        for power in [False,True]:
            qs={r['event_id']:fair(num(r[book+'_close_a']),num(r[book+'_close_b']),power) for r in rows}
            cover=[(r,h,o) for r,h,o in bets if qs[r['event_id']] is not None];both=[r for r in completed if qs[r['event_id']] is not None]
            out['closing_'+book+('_power' if power else '')]={'covered_bets':len(cover),'missing_bets':n-len(cover),'all_event_close_coverage':sum(v is not None for v in qs.values()),'mean_closing_ev':mean([o*(qs[r['event_id']] if h else 1-qs[r['event_id']])-1 for r,h,o in cover]),'mean_raw_price_ratio':mean([o/float(r[book+('_close_a' if h else '_close_b')])-1 for r,h,o in cover]),'paired_loss_events':len(both),'paired_log_loss_delta_vs_close':mean([loss(float(r['y']),float(r[col]))-loss(float(r['y']),qs[r['event_id']]) for r in both])}
    return out
columns={'fanduel':'market_p','physical':'p_physical','pinnacle':'p_pinnacle'}
shared=[r for r in forecasts if all(r[c]!='' for c in columns.values())]
recomputed={}
def compare(path,actual,expected):
    for key,value in actual.items():
        if key not in expected:
            if key != 'unresolved_events':check('required_metric_'+path+'/'+key,False,'Missing reported metric')
            continue
        if isinstance(value,dict):compare(path+'/'+key,value,expected[key])
        else:eq(path+'/'+key,value,expected[key])
for scope in ['own_available_population','shared_population']:
    recomputed[scope]={}
    for model,col in columns.items():
        rs=[r for r in forecasts if r[col]!=''] if scope=='own_available_population' else shared
        s=stats(rs,col);recomputed[scope][model]=s;compare(scope+'/'+model,s,metrics[scope][model])
        check('insufficient_weeks_'+scope+'/'+model,metrics[scope][model]['inference_status']=='insufficient_calendar_weeks' and s['independent_calendar_weeks']<8)
        for key in ['roi_ci','paired_log_loss_delta_ci']:eq('no_inference_'+scope+'/'+model+'/'+key,metrics[scope][model][key],[None,None])
for model,col in columns.items():
    grouped=defaultdict(list)
    for r in forecasts:
        if r[col]!='':grouped[r['date']].append(r)
    eq('day_population_'+model,set(grouped),set(metrics['by_day'][model]))
    for day,rs in grouped.items():compare('by_day/'+model+'/'+day,stats(rs,col),metrics['by_day'][model][day])
check('no_alert_or_promotion',metrics['status']=='unproven' and metrics['alerts_enabled'] is False and all(not node['passes_forward_promotion'] and not node['execution_verified'] for scope in ['own_available_population','shared_population'] for node in metrics[scope].values()))
eq('accepted_first_pitch_count',sum(int(r['game_pk']) in pitches for r in forecasts),metrics['accepted_events_with_recorded_first_pitch'])

def compact(a):return {'min':min(a),'median':statistics.median(a),'max':max(a)} if a else None
output={'audit_status':'pass' if not errors else 'fail','observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'method':'Independent standard-library CSV/JSON grouping and arithmetic; no beating, NumPy, pandas, or SciPy imports','auditor_script_sha256':sha(__file__),'artifacts':hashes,'checks_run':checks['checks'],'failures':errors,'reconciliation':dict(counts),'official_source_files_hashed':len(manifest['files']),'first_pitch_sources_hashed':sum(r['status']=='retrieved' for r in pitch_manifest['rows']),'first_pitch_times_available':len(pitches),'official_ambiguous_fixture_ids':sorted(ambiguous),'accepted_events':len(forecasts),'canonical_event_ids':sorted(r['event_id'] for r in forecasts),'unknown_outcome_ids':sorted(unknown_ids),'official_status_counts':dict(outcomes),'missing_synchronized_pinnacle_control_ids':sorted(missing_control),'missing_close_ids':dict(close_missing),'timing_minutes':{'entry_before_source_start':compact(entry_leads),**{book+'_close_before_conservative_boundary':compact(v) for book,v in close_leads.items()}},'physical_prediction_max_abs_error':max(errors_p),'recomputed':recomputed,'limitations':['Source sportsbook freshness and executability are not independently established by publisher capture timestamps.','Independent reconstruction verifies saved 21-feature vectors, their home-away differences, cutoff metadata, hashes and frozen-artifact probabilities; it does not duplicate all raw workload/travel feature engineering.','This frozen artifact contains 15 ungraded events at its source-retrieval vintage. They remain forecasts; no strategy selected any bets.','Only two calendar weeks and zero selected bets: no ROI, selected CLV, statistical edge, or forward-promotion claim.']}
(REPORT/'timestamped-mlb-independent-audit.json').write_text(json.dumps(output,indent=2,allow_nan=False,default=str)+'\n')
print(json.dumps({'status':output['audit_status'],'checks':output['checks_run'],'failures':errors,'reconciliation':dict(counts),'timing':output['timing_minutes'],'model_max_error':max(errors_p),'outcomes':dict(outcomes),'unresolved':len(unknown_ids),'shared_metrics':{k:{z:v for z,v in n.items() if z in ['events','settled_events','bets','log_loss','brier','paired_log_loss_delta','max_model_ev']} for k,n in recomputed['shared_population'].items()}},indent=2,default=str))

raise SystemExit(1 if errors else 0)
