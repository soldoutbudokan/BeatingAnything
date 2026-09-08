import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from beating.forward import open_ledger,export_ledger,score_quotes


class ForwardTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
