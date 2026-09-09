"""Independent exported-artifact chronology audit. Never fits a model."""
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.special import expit

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = {'calibration':['market_logit'],
           'set_shape':['market_logit','structure_gap'],
           'workload':['market_logit','structure_gap','workload_total','workload_difference']}
PENALTIES = [.001,.01,.1,1.]


def stamp(value):
    answer=datetime.fromisoformat(value)
    if answer.tzinfo is None:
        raise ValueError('naive_timestamp')
    return answer.astimezone(timezone.utc)


def graded(row):
    return row['y'] not in ('','nan','NaN')


def id_hash(rows):
    return hashlib.sha256(('\n'.join(sorted(row['event_id'] for row in rows))+'\n').encode()).hexdigest()


def raw_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(experiment):
    features_path=ROOT/f'reports/tennis-{experiment}-features.csv'
    forecasts_path=ROOT/f'reports/tennis-{experiment}-forecasts.csv'
    fit_path=ROOT/f'reports/tennis-{experiment}-fit.json'
    rows=list(csv.DictReader(features_path.open()))
    forecasts=list(csv.DictReader(forecasts_path.open()))
    fit=json.loads(fit_path.read_text())
    rows.sort(key=lambda row:(stamp(row['opening_at']),row['event_id']))
    failures=[]

    def check(condition, reason):
        if not condition:
            failures.append(reason)

    check(len(rows)==len({row['event_id'] for row in rows}), 'duplicate_feature_ids')
    check(len(forecasts)==len({row['event_id'] for row in forecasts}), 'duplicate_forecast_ids')
    check(fit['features']==COLUMNS,'candidate_feature_schema')
    for row in rows:
        check(int(row['date'][:4])==int(row['year']),'feature_year_date_discrepancy:'+row['event_id'])
        check(stamp(row['opening_at'])<stamp(row['start_at']),'feature_opening_not_prestart:'+row['event_id'])
        if graded(row):
            check(float(row['y']) in (0.,1.),'nonbinary_label:'+row['event_id'])
            source_midnight=datetime.fromisoformat(row['label_source_date']).replace(tzinfo=ZoneInfo('Europe/Prague'))+timedelta(days=1)
            available=source_midnight.astimezone(timezone.utc)+timedelta(hours=48)
            check(stamp(row['label_available_at'])==available,'label_availability_source_date:'+row['event_id'])
        else:
            check(not row['label_available_at'] and not row['label_source_date'],'ungraded_has_label_timestamp:'+row['event_id'])

    validation=[row for row in rows if int(row['year'])==2023 and graded(row)]
    first_validation=min(stamp(row['opening_at']) for row in rows if int(row['year'])==2023)
    development=[row for row in rows if int(row['year']) in (2021,2022) and graded(row) and stamp(row['label_available_at'])<first_validation]
    selection_at=max(stamp(row['label_available_at']) for row in validation)
    check(stamp(fit['selection_available_at'])==selection_at,'selection_availability_cutoff')
    check(Counter((row['candidate'],row['penalty']) for row in fit['validation_trials'])==Counter((name,p) for name in COLUMNS for p in PENALTIES),'validation_candidate_grid')
    for trial in fit['validation_trials']:
        check(trial['development_events']==len(development),'validation_development_count')
        check(trial['validation_events']==len(validation),'validation_event_count')
    winners={name:min((trial for trial in fit['validation_trials'] if trial['candidate']==name),key=lambda t:t['validation_log_loss']) for name in COLUMNS}
    check(fit['selected_penalties']==winners,'validation_penalty_minimum_or_tie_order')
    check(fit['selected_research_candidate']==min(winners,key=lambda name:winners[name]['validation_log_loss']),'validation_research_candidate_minimum')

    def model_check(model, training, columns, name):
        x=np.array([[float(row[column]) for column in columns] for row in training],dtype=float)
        mean=x.mean(axis=0)
        scale=x.std(axis=0)
        scale[scale<1e-8]=1.
        stored_mean=np.asarray(model['mean'])
        stored_scale=np.asarray(model['scale'])
        check(np.allclose(stored_mean,mean,rtol=1e-9,atol=1e-10),'mean_not_eligible_training:'+name)
        check(np.allclose(stored_scale,scale,rtol=1e-9,atol=1e-10),'scale_not_eligible_training:'+name)
        check(model['penalty']==winners[name.split(':')[-1]]['penalty'],'penalty_not_validation_selected:'+name)
        z=np.column_stack([np.ones(len(training)),(x-stored_mean)/stored_scale])
        market=np.clip(np.array([float(row['market_p']) for row in training]),1e-6,1-1e-6)
        y=np.array([float(row['y']) for row in training])
        beta=np.asarray(model['coef'])
        residual=expit(np.log(market/(1-market))+z@beta)-y
        weights=np.ones(len(beta)); weights[0]=.1
        gradient=z.T@residual/len(training)+model['penalty']*weights*beta
        maximum=float(np.max(np.abs(gradient)))
        check(maximum<=1e-5,'eligible_training_L2_gradient_exceeds_1e-5:'+name)
        return {'maximum_mean_abs_error':float(np.max(np.abs(stored_mean-mean))),
                'maximum_scale_abs_error':float(np.max(np.abs(stored_scale-scale))),
                'maximum_L2_score_gradient':maximum}

    years={}
    expected_forecasts=[]
    for year in (2024,2025):
        annual=[row for row in rows if int(row['year'])==year]
        excluded=[row for row in annual if stamp(row['opening_at'])<=selection_at]
        test=[row for row in annual if stamp(row['opening_at'])>selection_at]
        fold=fit['annual_models'][str(year)]
        check(set(fold['model_unavailable_event_ids'])=={row['event_id'] for row in excluded},'annual_model_unavailable_ids:'+str(year))
        if not test:
            check(fold['status']=='missing_feature_valid_test_events','empty_fold_status:'+str(year))
            continue
        first=min(stamp(row['opening_at']) for row in test)
        training=[row for row in rows if 2021<=int(row['year'])<year and graded(row) and stamp(row['label_available_at'])<first]
        check(fold['status']=='fitted','nonempty_fold_status:'+str(year))
        check(stamp(fold['first_forecast_quote'])==first,'annual_first_quote:'+str(year))
        check(fold['training_events']==len(training),'annual_training_count:'+str(year))
        check(fold['training_years']==sorted({int(row['year']) for row in training}),'annual_training_years:'+str(year))
        check(stamp(fold['maximum_label_available_at'])==max(stamp(row['label_available_at']) for row in training),'annual_max_label_cutoff:'+str(year))
        check(selection_at<first,'validation_selection_unavailable_at_annual_fit:'+str(year))
        expected_forecasts.extend(test)
        years[str(year)]={'training_events':len(training),'training_id_sha256':id_hash(training),
            'forecasts':len(test),'unavailable_model_events':len(excluded),
            'first_forecast_quote':first.isoformat(),
            'maximum_training_label_available_at':max(stamp(row['label_available_at']) for row in training).isoformat(),
            'models':{name:model_check(fold['models'][name],training,columns,str(year)+':'+name) for name,columns in COLUMNS.items()}}

    check({row['event_id'] for row in forecasts}=={row['event_id'] for row in expected_forecasts},'holdout_forecast_population')
    original={row['event_id']:row for row in rows}
    numeric={'year','y','odds_a','odds_b','market_p','market_logit','kernel_p','structure_gap','workload_total','workload_difference',
             'hold1','hold2','kernel_residual','history_sets_player1','history_sets_player2','close_a','close_b'}
    for row in forecasts:
        source=original[row['event_id']]
        for key,value in source.items():
            other=row.get(key)
            if key in numeric and value and other:
                equal=np.isclose(float(value),float(other),rtol=1e-12,atol=1e-12,equal_nan=True)
            elif key=='date':
                equal=value[:10]==other[:10]
            else:
                equal=value==other
            check(equal,'forecast_feature_drift:'+row['event_id']+':'+key)

    final_as_of=stamp(fit['final_fit_as_of'])
    final_training=[row for row in rows if graded(row) and stamp(row['label_available_at'])<final_as_of]
    check(len(final_training)==sum(graded(row) for row in rows),'known_label_unavailable_at_final_fit')
    check(fit['final_training_events']==len(final_training),'final_training_count')
    check(stamp(fit['final_maximum_label_available_at'])==max(stamp(row['label_available_at']) for row in final_training),'final_maximum_label')
    check(fit['training_through_source_date']==max(row['label_source_date'] for row in final_training),'final_source_date')
    check(fit['split_counts']=={str(year):sum(int(row['year'])==year for row in rows) for year in sorted({int(row['year']) for row in rows})},'feature_split_counts')
    final_checks={name:model_check(fit['final_models'][name],final_training,columns,'final:'+name) for name,columns in COLUMNS.items()}
    return {'experiment':experiment.upper(),'feature_events':len(rows),'forecast_events':len(forecasts),
            'development_events':len(development),'development_id_sha256':id_hash(development),'validation_events':len(validation),
            'first_validation_quote':first_validation.isoformat(),'selection_available_at':selection_at.isoformat(),
            'ungraded_holdout_forecasts_retained':sum(not graded(row) for row in forecasts),
            'missing_close_holdout_forecasts_retained':sum(row['closing_valid'].lower()!='true' for row in forecasts),
            'annual_fits':years,'final_fit_as_of':final_as_of.isoformat(),'final_training_events':len(final_training),
            'final_training_id_sha256':id_hash(final_training),'final_model_checks':final_checks,
            'mismatch_count':len(failures),'first_mismatch':failures[0] if failures else None,
            'files':{path.name:raw_hash(path) for path in (features_path,forecasts_path,fit_path)}}


if __name__=='__main__':
    report={'scope':'Independent exported feature/fit/forecast chronology, membership, normalization and stored-fit L2 gradient verification; no model fitting or strategy evaluation',
            'created_at':datetime.now(timezone.utc).isoformat(),
            'audit_script_sha256':raw_hash(Path(__file__)),
            'experiments':[main(experiment) for experiment in ('n2','n3')],
            'limitations':['Validation-development coefficients/normalizers and per-row training membership were not exported; development eligibility/counts and reported validation minima were checked, without refitting.',
                'Annual/final membership is independently reconstructed from feature rows; matching normalizers and a stationary stored L2 fit support that membership, but do not provide a historical runtime log.',
                'This audit begins at exported accepted features; it does not rerun source reconstruction or decide which rejected raw events should have features.']}
    path=ROOT/'reports/tennis-training-audit.json'
    path.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
    raise SystemExit(1 if any(row['mismatch_count'] for row in report['experiments']) else 0)
