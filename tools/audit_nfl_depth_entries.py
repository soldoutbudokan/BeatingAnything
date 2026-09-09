"""Metadata-only fixed NFL entry/depth-chart join; no labels or models."""
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT/'data/raw/nfl-fixture-feasibility/candidate-quote-projection.json'
DEPTH = ROOT/'data/raw/nfl-source-audit/depth_charts_2025.csv.gz'
PBP = ROOT/'data/raw/nfl-source-audit/play_by_play_2024-feature-projection.csv'
PUBLICATION = ROOT/'data/raw/nfl-source-audit/depth-snapshot-run-matches.json'
EXPECTED = {
    ENTRY:'42d33403b24a6223024889166c1f910b03789f6a7ec4e48af48597125ccf6389',
    DEPTH:'5cbc4d088a05c1c7b047ebdd2bacb480c97aac5849d46fc631fa041d09dd8ef7',
    PBP:'f129cef7e21d1e294b60e47e92d0c6b355065358e90f7ee531211f973319908d',
    PUBLICATION:'a6f6eda0b5ecb6947d61bc8283c0b1a4f302e7ec2d37bc4dbd888bccc9e6ba96',
}
BASE_JOIN_SHA256 = 'bb7c9eb9607cdbf711b96549e07ca4e5deacbe517a63be65a000b3091b15f9f6'


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            result.update(chunk)
    return result.hexdigest()


def timestamp(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp lacks timezone')
    return dt.astimezone(timezone.utc)


def quantiles(values):
    if not values:
        return None
    ordered=sorted(values)
    def percentile(p):
        rank=(len(ordered)-1)*p
        lower=int(rank)
        upper=min(lower+1,len(ordered)-1)
        return ordered[lower]+(ordered[upper]-ordered[lower])*(rank-lower)
    return {'count':len(values),'minimum':min(values),'p25':percentile(.25),
            'median':statistics.median(values),'p75':percentile(.75),
            'p90':percentile(.9),'p95':percentile(.95),'maximum':max(values)}


def publication_qualification(snapshot, quote, matched, unmatched):
    """Qualify an already-selected snapshot; never substitute another one."""
    answer={'status':None,'reasons':[],'run_id':None,'availability_proxy_at':None,
            'age_seconds':None,'delay_seconds':None}
    if snapshot is None:
        answer['status']='missing_selected_snapshot'
        answer['reasons'].append('missing_selected_snapshot')
        return answer
    dt=timestamp(snapshot['dt'])
    candidates=matched.get(dt,[])
    if len(candidates)>1 or (not candidates and any(len(row.get('matching_successful_run_ids',[]))>1 for row in unmatched.get(dt,[]))):
        answer['status']='ambiguous_publication_proxy'
        answer['reasons'].append('ambiguous_publication_proxy')
        return answer
    if not candidates:
        answer['status']='missing_publication_proxy'
        answer['reasons'].append('missing_publication_proxy')
        return answer
    row=candidates[0]
    proxy=timestamp(row['availability_proxy_at'])
    start=timestamp(row['run_started_at'])
    if not row.get('run_id') or not row.get('head_sha') or not start<=dt<=proxy or abs((proxy-dt).total_seconds()-row['delay_seconds'])>1e-9:
        answer['status']='invalid_publication_proxy_metadata'
        answer['reasons'].append('invalid_publication_proxy_metadata')
        return answer
    answer.update(run_id=row['run_id'],head_sha=row['head_sha'],html_url=row.get('html_url'),
                  availability_proxy_at=proxy.isoformat(),age_seconds=(quote-proxy).total_seconds(),
                  delay_seconds=(proxy-dt).total_seconds())
    if proxy>=quote:
        answer['status']='publication_run_not_finished_before_entry'
        answer['reasons'].append('publication_run_not_finished_before_entry')
    else:
        answer['status']='matched_run_finished_strictly_prequote'
    return answer


def main():
    sources={}
    for path,expected in EXPECTED.items():
        actual=sha(path)
        if actual!=expected:
            raise ValueError('Pinned source hash mismatch: '+str(path))
        sources[str(path.relative_to(ROOT))]={'sha256':actual,'bytes':path.stat().st_size}
    # Strip prices and last-prestart observations before any analysis.
    entries=[{key:row[key] for key in ('game_id','event_id','week','game_type','entry_at','fixture')}
             for row in json.loads(ENTRY.read_text())]
    if len(entries)!=285 or len({row['game_id'] for row in entries})!=285:
        raise ValueError('Fixed 285-entry population changed')
    publication=json.loads(PUBLICATION.read_text())
    publication_matches,publication_unmatched=defaultdict(list),defaultdict(list)
    for row in publication['matched']:
        publication_matches[timestamp(row['dt'])].append(row)
    for row in publication['unmatched']:
        publication_unmatched[timestamp(row['dt'])].append(row)

    team_times=defaultdict(set)
    quarterback_rows=defaultdict(list)
    depth_rows=0
    with gzip.open(DEPTH,'rt',newline='') as handle:
        for raw in csv.DictReader(handle):
            depth_rows+=1
            # No player names are needed to join identities.
            row={key:raw[key] for key in ('dt','team','gsis_id','espn_id','pos_abb','pos_rank','pos_grp','pos_slot')}
            dt=timestamp(row['dt'])
            team_times[row['team']].add(dt)
            if row['pos_abb']=='QB' and row['pos_rank']=='1':
                quarterback_rows[row['team'],dt].append(row)
    team_times={team:sorted(values) for team,values in team_times.items()}

    snapshots={}
    for team,times in team_times.items():
        for dt in times:
            rows=quarterback_rows[team,dt]
            ids={row['gsis_id'] for row in rows if row['gsis_id']}
            espn={row['espn_id'] for row in rows if row['espn_id']}
            reasons=[]
            if not rows: reasons.append('missing_QB_rank1_in_latest_team_snapshot')
            if rows and any(not row['gsis_id'] for row in rows): reasons.append('missing_GSIS_identity')
            if len(ids)>1 or len(espn)>1: reasons.append('conflicting_QB_rank1_identity')
            snapshots[team,dt]={'dt':dt.isoformat(),'rank1_row_count':len(rows),
                'gsis_id':next(iter(ids)) if len(ids)==1 and not reasons else None,
                'espn_id':next(iter(espn)) if len(espn)==1 and not reasons else None,
                'all_gsis_ids':sorted(ids),'reasons':reasons}

    passer_ids=set()
    dropback_counts=Counter()
    pbp_rows=0
    for raw in csv.DictReader(PBP.open(newline='')):
        pbp_rows+=1
        row={key:raw[key] for key in ('game_id','passer_player_id','rusher_player_id','qb_dropback','qb_scramble')}
        if not row['game_id'].startswith('2024_'):
            raise ValueError('Prior history projection contains non-2024 game')
        passer=row['passer_player_id']
        if passer: passer_ids.add(passer)
        if row['qb_dropback']=='1':
            identity=passer or (row['rusher_player_id'] if row['qb_scramble']=='1' else '')
            if identity: dropback_counts[identity]+=1

    all_sides=[]
    output=[]
    previous_entry={}
    for entry in sorted(entries,key=lambda row:(timestamp(row['entry_at']),row['game_id'])):
        quote=timestamp(entry['entry_at'])
        sides={}
        for role in ('home','away'):
            team=entry['fixture'][role+'_team']
            times=team_times.get(team,[])
            index=bisect_left(times,quote)-1
            one={'team':team,'entry_at':entry['entry_at'],'snapshot':None,
                 'age_seconds':None,'reasons':[],'rookie_status':'unverified_source_has_no_career_status'}
            if index<0:
                one['reasons'].append('no_strictly_prequote_team_snapshot')
            else:
                selected=snapshots[team,times[index]]
                one['snapshot']=selected
                one['age_seconds']=(quote-times[index]).total_seconds()
                assert one['age_seconds']>0
                one['reasons'].extend(selected['reasons'])
                prior=snapshots[team,times[index-1]] if index else None
                one['previous_snapshot_dt']=prior['dt'] if prior else None
                one['rank1_changed_since_previous_snapshot']=(selected['gsis_id']!=prior['gsis_id']) if prior and selected['gsis_id'] and prior['gsis_id'] else None
                # Count only observed transitions available before this quote.
                changes=[]
                for earlier,later in zip(times[:index],times[1:index+1]):
                    before,after=snapshots[team,earlier],snapshots[team,later]
                    if before['gsis_id'] and after['gsis_id'] and before['gsis_id']!=after['gsis_id']:
                        changes.append(later)
                one['observed_prequote_rank1_changes']=len(changes)
                one['last_observed_rank1_change_at']=changes[-1].isoformat() if changes else None
                identifier=selected['gsis_id']
                one['has_2024_passer_identity']=identifier in passer_ids if identifier else None
                one['identified_2024_dropback_rows']=dropback_counts[identifier] if identifier else None
                prev_entry=previous_entry.get(team)
                one['previous_fixed_entry_at']=prev_entry['entry_at'] if prev_entry else None
                previous_id=prev_entry['snapshot']['gsis_id'] if prev_entry and prev_entry['snapshot'] else None
                one['rank1_changed_since_previous_fixed_entry']=(identifier!=previous_id) if identifier and previous_id else None
            previous_entry[team]=one
            sides[role]=one
            all_sides.append(one)
        output.append({key:entry[key] for key in ('game_id','event_id','week','game_type','entry_at')}|sides)

    base_join_sha=hashlib.sha256((json.dumps(output,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()).hexdigest()
    if base_join_sha!=BASE_JOIN_SHA256:
        raise ValueError('Publication qualification changed the already-selected base join')
    for side in all_sides:
        side['publication_proxy']=publication_qualification(side['snapshot'],timestamp(side['entry_at']),publication_matches,publication_unmatched)

    selected=[row for row in all_sides if row['snapshot'] and row['snapshot']['gsis_id'] and not row['reasons']]
    identifiers={row['snapshot']['gsis_id'] for row in selected}
    espn_to_gsis=defaultdict(set)
    gsis_to_espn=defaultdict(set)
    for row in selected:
        espn,gsis=row['snapshot']['espn_id'],row['snapshot']['gsis_id']
        if espn:
            espn_to_gsis[espn].add(gsis)
            gsis_to_espn[gsis].add(espn)
    missing_history={identifier for identifier in identifiers if not dropback_counts[identifier]}
    weeks=[]
    for week in sorted({row['week'] for row in output}):
        subset=[row for row in output if row['week']==week]
        side_subset=[row[role] for row in subset for role in ('home','away')]
        weeks.append({'week':week,'entries':len(subset),
            'both_QBs_unambiguous':sum(all(not row[role]['reasons'] for role in ('home','away')) for row in subset),
            'team_entries_without_2024_dropback_history':sum(row.get('identified_2024_dropback_rows')==0 for row in side_subset),
            'team_entries_with_publication_run_strictly_prequote':sum(row['publication_proxy']['status']=='matched_run_finished_strictly_prequote' for row in side_subset),
            'publication_proxy_age_seconds':quantiles([row['publication_proxy']['age_seconds'] for row in side_subset if row['publication_proxy']['age_seconds'] is not None]),
            'snapshot_age_seconds':quantiles([row['age_seconds'] for row in side_subset if row['age_seconds'] is not None])})

    destination=ROOT/'data/raw/nfl-depth-entry-feasibility'
    destination.mkdir(parents=True,exist_ok=True)
    projection=destination/'entry-depth-metadata.json'
    projection.write_text(json.dumps(output,sort_keys=True,indent=2,allow_nan=False)+'\n')
    report={'scope':'Fixed NFL 285-entry metadata/depth identity feasibility only; no result labels, eventual starters, models, EV, CLV or returns',
        'created_at':datetime.now(timezone.utc).isoformat(),'audit_script_sha256':sha(Path(__file__)),
        'sources':sources,'rules':{
            'snapshot':'Latest team timestamp strictly before fixed entry quote, then QB rank1 in that exact snapshot; no older-snapshot fallback and no age filter',
            'identity':'Unique nonmissing GSIS and no conflicting ESPN identity; names are never used to repair IDs',
            'prior_history':'Any identified 2024 qb_dropback row, using passer_player_id or rusher_player_id only for qb_scramble; no minimum history threshold',
            'changes':'Only transitions between unambiguous snapshots strictly before each entry; never eventual starters or postquote revisions',
            'publication_proxy':'Exact selected dt joins to one matched successful workflow run; use that run availability_proxy_at strictly before entry, without changing selections or imposing a universal delay',
            'rookies':'No career status field exists in retained sources; no-history players cannot be designated rookies'},
        'counts':{'fixed_entries':len(output),'team_entries':len(all_sides),'depth_rows':depth_rows,
            'pbp_projection_rows':pbp_rows,'teams':len(team_times),
            'team_entries_with_prior_snapshot':sum(row['snapshot'] is not None for row in all_sides),
            'unambiguous_QB_team_entries':len(selected),
            'both_QBs_unambiguous_entries':sum(all(not row[role]['reasons'] for role in ('home','away')) for row in output),
            'distinct_selected_QB_GSIS_ids':len(identifiers),
            'distinct_selected_QB_ESPN_ids':len(espn_to_gsis),
            'selected_ESPN_ids_mapping_to_multiple_GSIS_ids':sum(len(values)>1 for values in espn_to_gsis.values()),
            'selected_GSIS_ids_mapping_to_multiple_ESPN_ids':sum(len(values)>1 for values in gsis_to_espn.values()),
            'selected_team_entries_without_ESPN_identity':sum(not row['snapshot']['espn_id'] for row in selected),
            'selected_team_entries_with_duplicate_rank1_rows':sum(row['snapshot']['rank1_row_count']>1 for row in selected),
            'distinct_selected_QBs_with_2024_passer_identity':len(identifiers & passer_ids),
            'distinct_selected_QBs_with_2024_dropback_history':sum(bool(dropback_counts[identifier]) for identifier in identifiers),
            'distinct_selected_QBs_without_2024_dropback_history':len(missing_history),
            'team_entries_without_2024_dropback_history':sum(row.get('identified_2024_dropback_rows')==0 for row in selected),
            'entries_with_either_QB_without_2024_dropback_history':sum(any(row[role].get('identified_2024_dropback_rows')==0 for role in ('home','away')) for row in output),
            'rank1_changed_since_previous_snapshot_team_entries':sum(row.get('rank1_changed_since_previous_snapshot') is True for row in all_sides),
            'rank1_changed_since_previous_fixed_entry_team_entries':sum(row.get('rank1_changed_since_previous_fixed_entry') is True for row in all_sides),
            'rookie_status_unverified_no_prior_history_unique_QBs':len(missing_history)},
        'publication_proxy':{
            'interpretation':'Operational publication proxy from successful public workflow metadata; not proof of exact historical row content or GSIS enrichment',
            'matched_archive_timestamps':len(publication['matched']),
            'unmatched_archive_timestamps':len(publication['unmatched']),
            'base_join_sha256_before_qualification':base_join_sha,
            'team_entry_status_counts':dict(Counter(row['publication_proxy']['status'] for row in all_sides)),
            'missing_proxy_team_entries':sum(row['publication_proxy']['status']=='missing_publication_proxy' for row in all_sides),
            'ambiguous_proxy_team_entries':sum(row['publication_proxy']['status']=='ambiguous_publication_proxy' for row in all_sides),
            'run_not_finished_before_entry_team_entries':sum(row['publication_proxy']['status']=='publication_run_not_finished_before_entry' for row in all_sides),
            'invalid_proxy_metadata_team_entries':sum(row['publication_proxy']['status']=='invalid_publication_proxy_metadata' for row in all_sides),
            'both_selected_snapshots_with_run_strictly_prequote_entries':sum(all(row[role]['publication_proxy']['status']=='matched_run_finished_strictly_prequote' for role in ('home','away')) for row in output),
            'distinct_selected_snapshot_timestamps':len({row['snapshot']['dt'] for row in all_sides if row['snapshot']}),
            'age_seconds':quantiles([row['publication_proxy']['age_seconds'] for row in all_sides if row['publication_proxy']['age_seconds'] is not None]),
            'selected_run_delay_seconds':quantiles([row['publication_proxy']['delay_seconds'] for row in all_sides if row['publication_proxy']['delay_seconds'] is not None])},
        'selected_snapshot_reason_counts':dict(Counter(reason for row in all_sides for reason in row['reasons'])),
        'snapshot_age_seconds':quantiles([row['age_seconds'] for row in all_sides if row['age_seconds'] is not None]),
        'prior_2024_identified_dropback_rows_per_unique_selected_QB':quantiles([dropback_counts[identifier] for identifier in identifiers]),
        'by_nfl_week':weeks,'projection':{'file':str(projection.relative_to(ROOT)),'sha256':sha(projection)},
        'limitations':['dt is retained source snapshot metadata; matched successful workflow completion is an operational availability proxy, not proof of exact historical row-content publication.',
            'GSIS mapping in historical depth snapshots may have been revised by publisher; identity overlap does not certify the mapping vintage.',
            'A listed rank1 QB is not proof of the player who started or played; no eventual starters were used.',
            'No-prior2024-history cases include unknown career status; no rookie designation is inferred.',
            'History row counts measure identity overlap only, not pressure feature quality or sufficient sample size.',
            'All 285 entries are retained; no experiment, filter threshold or model has been selected.']}
    target=ROOT/'reports/nfl-depth-entry-feasibility.json'
    target.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:report[key] for key in ('counts','selected_snapshot_reason_counts','snapshot_age_seconds','publication_proxy')},indent=2))


if __name__=='__main__':
    main()
