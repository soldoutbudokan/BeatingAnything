import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from beating.forward import open_ledger,open_forward_ledger,export_ledger,score_quotes,run,settle_from_schedule
from beating.monitor import Monitor


class ForwardTests(unittest.TestCase):
    def quote(self, now, event='mlb:123', start=None):
        return {'event_id':event,'sport':'MLB','bookmaker':'FanDuel','market':'moneyline',
                'home_team':'H','away_team':'A','home_team_id':1,'away_team_id':2,
                'starts_at':(start or now+timedelta(hours=2)).isoformat(),'observed_at':now.isoformat(),
                'status':'open','is_live':False,'decimal_home':1.91,'decimal_away':1.91,
                'source':{'uri':'test://quotes','provider':'synthetic fixture','verified':False,'synthetic':True}}

    def feature(self, quote):
        return {'event_id':quote['event_id'],'input_data_complete':True,'home_team_id':1,'away_team_id':2,
                'start_time':quote['starts_at'],'feature_cutoff_at':quote['observed_at'],
                'model_feature_version':'mlb_lagged_workload_v1'}

    def artifact(self, root):
        path=root/'synthetic-model.json'
        path.write_text(json.dumps({'model_id':'synthetic-model','feature_columns':[],
            'training_through':'2025-01-01','model':{'penalty':1,'mean':[],'scale':[],'coef':[.5]}}))
        return path

    def seed(self, state, ledger, now, name='forward', event='mlb:123', start=None):
        m=open_ledger(name,state,ledger)
        quote=self.quote(now,event,start)
        m.ingest_quote(quote,now=now)
        m.predict({'event_id':event,'model_id':'old-synthetic','probability_home':.6,
                   'generated_at':now.isoformat(),'feature_cutoff_at':now.isoformat()},now=now)
        Path(ledger).mkdir(parents=True,exist_ok=True)
        export_ledger(m,Path(ledger)/f'{name}.sql')
        m.close()

    def game(self):
        return {'gamePk':123,'gameType':'R','scheduledInnings':9,'doubleHeader':'N',
                'status':{'detailedState':'Final'},'linescore':{'currentInning':9},
                'teams':{'home':{'team':{'id':1},'score':3},'away':{'team':{'id':2},'score':1}}}

    def test_feature_identity_fails_closed_and_ledger_restores(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); state=root/'state'; ledger=root/'ledger'
            state.mkdir(); ledger.mkdir()
            now=datetime.now(timezone.utc)
            start=(now+timedelta(hours=2)).isoformat()
            quote={'event_id':'mlb:123','sport':'MLB','bookmaker':'FanDuel','market':'moneyline',
                   'home_team':'H','away_team':'A','home_team_id':1,'away_team_id':2,
                   'starts_at':start,'observed_at':now.isoformat(),'status':'open','is_live':False,
                   'decimal_home':1.91,'decimal_away':1.91,
                   'source':{'uri':'https://example.invalid','provider':'synthetic test','verified':False,'synthetic':True}}
            model={'model_id':'test','feature_columns':[],
                   'model':{'penalty':1,'mean':[],'scale':[],'coef':[0]}}
            feature={'event_id':'mlb:123','input_data_complete':True,'home_team_id':99,'away_team_id':2,
                     'start_time':start,'feature_cutoff_at':(now-timedelta(minutes=1)).isoformat(),
                     'model_feature_version':'mlb_lagged_workload_v1'}
            m=open_ledger('2030-01-01',state,ledger)
            result=score_quotes(m,[quote],[feature],model,'0'*64,now=now)
            self.assertEqual(result[0]['reasons'],['feature_quote_identity_or_schedule_mismatch'])
            self.assertEqual(m.db.execute('select count(*) from predictions').fetchone()[0],0)
            feature['home_team_id']=1
            result=score_quotes(m,[quote],[feature],model,'0'*64,now=now)
            self.assertIn('edge_below_threshold',result[0]['reasons'])
            export_ledger(m,ledger/'2030-01-01.sql');m.close()
            restored=root/'fresh';restored.mkdir()
            m=open_ledger('2030-01-01',restored,ledger)
            self.assertEqual(m.db.execute('select count(*) from predictions').fetchone()[0],1)
            with self.assertRaises(Exception):m.db.execute('delete from predictions')
            m.close()

    def test_date_rollover_and_fresh_runner_keep_one_registry_and_first_forecast(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ledger=root/'ledger'; model=self.artifact(root)
            first=datetime(2026,9,9,3,50,tzinfo=timezone.utc)  # 23:50 New York.
            second=first+timedelta(minutes=20)
            start=first+timedelta(hours=2)
            for index,now in enumerate((first,second)):
                quote=self.quote(now,start=start)

                def collect(state):
                    (state/'quotes.json').write_text(json.dumps([quote]))
                    return {'status':'observational','observed_at':now.isoformat()}

                with patch('beating.forward.collect',side_effect=collect), \
                        patch('beating.forward.build_live_snapshot',return_value=[self.feature(quote)]), \
                        patch('beating.forward.urlopen',side_effect=lambda *a,**k:io.BytesIO(b'{"dates":[]}')):
                    run(root/f'state-{index}',ledger,model,root/'reports',now=now)
            m=open_forward_ledger(root/'state-1',ledger)
            try:
                self.assertEqual(m.db.execute('SELECT count(*) FROM models').fetchone()[0],1)
                self.assertEqual(m.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
                self.assertEqual(m.db.execute('SELECT count(*) FROM predictions').fetchone()[0],2)
                self.assertEqual(len(m.forecast_report(now=second)['events']),1)
                original=m.db.execute('SELECT registered_at FROM models').fetchone()[0]
                self.assertEqual(datetime.fromisoformat(original.replace('Z','+00:00')),first)
            finally:m.close()
            decisions=json.loads((root/'reports/latest-decisions.json').read_text())
            self.assertIn('event_already_signaled',decisions[0]['reasons'])
            self.assertEqual(list(ledger.glob('????-??-??.sql')),[])
            self.assertTrue((ledger/'forward.sql').exists())

    def test_existing_outcomes_grade_despite_feature_or_quote_failure(self):
        for phase in ('features','quotes','model'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as directory:
                root=Path(directory); state=root/'state'; ledger=root/'ledger'; model=self.artifact(root)
                now=datetime(2026,9,9,12,tzinfo=timezone.utc)
                self.seed(state,ledger,now-timedelta(hours=8))
                if phase=='model':model=root/'missing-model.json'
                with patch('beating.forward.build_live_snapshot',side_effect=RuntimeError('unavailable') if phase=='features' else None,
                           return_value=[]) as features, \
                        patch('beating.forward.collect',side_effect=RuntimeError('unavailable')) as collect, \
                        patch('beating.forward.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(
                            {'dates':[{'games':[self.game()]}]}).encode())) as network:
                    result=run(state,ledger,model,root/'reports',now=now)
                self.assertEqual(result['observation_error']['phase'],phase)
                self.assertEqual(result['settlements_added'],1)
                self.assertEqual(result['prediction_rows_recorded'],0)
                self.assertIn('hydrate=linescore',network.call_args.args[0])
                if phase!='quotes':collect.assert_not_called()
                report=json.loads((root/'reports/forward-report.json').read_text())
                self.assertEqual(report['cumulative']['settled_signals'],1)

    def test_unexported_legacy_records_remain_separate_and_cannot_be_counted_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); state=root/'state'; ledger=root/'ledger'; model=self.artifact(root)
            now=datetime(2026,9,9,12,tzinfo=timezone.utc)
            self.seed(state,ledger,now-timedelta(minutes=10),name='2026-09-08',start=now+timedelta(hours=2))
            (ledger/'2026-09-08.sql').unlink()  # Simulate a crash before the old daily export.
            quotes=[self.quote(now),self.quote(now,event='mlb:456')]

            def collect(state):
                (state/'quotes.json').write_text(json.dumps(quotes))
                return {'status':'observational'}

            with patch('beating.forward.collect',side_effect=collect), \
                    patch('beating.forward.build_live_snapshot',return_value=[self.feature(q) for q in quotes]), \
                    patch('beating.forward.urlopen',side_effect=lambda *a,**k:io.BytesIO(b'{"dates":[]}')):
                run(state,ledger,model,root/'reports',now=now)
            decisions=json.loads((root/'reports/latest-decisions.json').read_text())
            self.assertEqual(decisions[0]['reasons'],['event_in_legacy_ledger'])
            report=json.loads((root/'reports/forward-report.json').read_text())
            self.assertEqual([r['event_id'] for r in report['cumulative']['all_forecasts']['events']],['mlb:456'])
            self.assertEqual([r['event_id'] for r in report['legacy_days']['2026-09-08']['all_forecasts']['events']],['mlb:123'])
            self.assertTrue((ledger/'2026-09-08.sql').exists())

    def test_different_state_directories_cannot_write_the_same_archive_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)

            def first_writer(*args):
                with self.assertRaises(BlockingIOError):
                    run(root/'second-state',root/'shared-ledger')
                return {'status':'synthetic-first-writer'}

            with patch('beating.forward._run',side_effect=first_writer) as cycle:
                result=run(root/'first-state',root/'shared-ledger')
            self.assertEqual(result['status'],'synthetic-first-writer')
            self.assertEqual(cycle.call_count,1)

    def test_failed_restore_never_publishes_a_partial_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); state=root/'state'; ledger=root/'ledger'; ledger.mkdir()
            archive=ledger/'forward.sql'
            archive.write_text('CREATE TABLE partial (value TEXT); INVALID SQL;')
            with self.assertRaises(Exception):open_forward_ledger(state,ledger)
            self.assertFalse((state/'forward.sqlite3').exists())
            now=datetime(2026,9,9,12,tzinfo=timezone.utc)
            m=Monitor(':memory:')
            m.ingest_quote(self.quote(now),now=now)
            export_ledger(m,archive);m.close()
            restored=open_forward_ledger(state,ledger)
            try:
                self.assertEqual(restored.db.execute('SELECT count(*) FROM quotes').fetchone()[0],1)
                with self.assertRaises(Exception):restored.db.execute('DELETE FROM quotes')
            finally:restored.close()

    def test_unclear_final_or_wrong_identity_stays_unresolved(self):
        now=datetime(2026,9,9,12,tzinfo=timezone.utc)
        m=Monitor(':memory:')
        try:
            m.ingest_quote(self.quote(now-timedelta(hours=8)),now=now-timedelta(hours=8))
            cases=[{'status':{'detailedState':'Completed Early'}},{'linescore':{'currentInning':8}},
                   {'resumeDate':'2026-09-09'},{'doubleHeader':'Y'},{'scheduledInnings':None}]
            for changes in cases:
                self.assertEqual(settle_from_schedule(m,{'dates':[{'games':[{**self.game(),**changes}]}]},
                                                     now.isoformat(),'test://schedule'),0)
            wrong=self.game();wrong['teams']['home']['team']['id']=999
            self.assertEqual(settle_from_schedule(m,{'dates':[{'games':[wrong]}]},now.isoformat(),'test://schedule'),0)
            self.assertEqual(settle_from_schedule(m,{'dates':[{'games':[self.game()]}]},now.isoformat(),'test://schedule'),1)
        finally:m.close()


if __name__=='__main__':unittest.main()
