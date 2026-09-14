import tempfile,unittest
from wallet_observatory.db import Store
from wallet_observatory.rules import cohort_stats,following_evidence

class FollowingResultsTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.s=Store(t.name+'/db');self.now=2000000000
    def signal(self,ident,mint,age,cohort='fresh'):
        self.s.execute("INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible,observation_class,rule_version) VALUES(?,?,?,?,1,?,2)",(ident,'wallet',mint,self.now-age,cohort))
        return self.s.one('SELECT id FROM signals WHERE trade_id=?',(ident,))['id']
    def outcome(self,sid,horizon,ret,status='estimated'):
        self.s.execute('INSERT INTO outcomes(signal_id,delay,horizon,return_pct,status) VALUES(?,900,?,?,?)',(sid,horizon,ret,status))
    def test_short_results_do_not_leak_into_long_horizons(self):
        sid=self.signal(1,'a',7200);self.outcome(sid,3600,20)
        results=following_evidence(self.s,'wallet',self.now)['following']
        early=results[0]['selected'];self.assertEqual(early['mean_pnl_usd'],100)
        self.assertEqual(early['win_rate'],100);self.assertEqual(early['coverage'],100)
        self.assertIsNone(results[1]['selected']['mean_return']);self.assertEqual(results[1]['selected']['waiting_samples'],1)
        self.assertFalse(early['qualifies']);self.assertFalse(early['promising'])
    def test_pending_missing_and_evaluation_distinguished(self):
        sid=self.signal(1,'a',7200);self.outcome(sid,3600,None,'missing_data')
        self.signal(2,'b',7200);self.signal(3,'c',100)
        c=cohort_stats(self.s,'wallet',self.now,3600)[0]
        self.assertEqual(c['samples'],2);self.assertEqual(c['waiting_samples'],1)
        self.assertEqual(c['missing_samples'],1);self.assertEqual(c['awaiting_calculation'],1)
        self.assertEqual(c['coverage'],0);self.assertEqual(c['next_matures_at'],self.now-100+900+3600+600)
    def test_duplicate_tokens_and_cohorts_stay_separate(self):
        for i,mint,cohort,ret in ((1,'a','fresh',10),(2,'a','fresh',90),(3,'a','delayed',-20)):
            sid=self.signal(i,mint,7200-i,cohort);self.outcome(sid,3600,ret)
        groups=cohort_stats(self.s,'wallet',self.now,3600)
        self.assertEqual(groups[0]['priced_samples'],1);self.assertEqual(groups[0]['mean_return'],10)
        self.assertEqual(groups[1]['mean_return'],-20)
    def test_many_short_wins_cannot_qualify(self):
        for i in range(10):
            sid=self.signal(i,str(i),7200);self.outcome(sid,3600,30)
        self.assertFalse(cohort_stats(self.s,'wallet',self.now,3600)[0]['qualifies'])
        self.assertEqual(cohort_stats(self.s,'wallet',self.now)[0]['samples'],0)
