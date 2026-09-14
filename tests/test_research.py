import json,tempfile,time,unittest
from unittest.mock import patch
from wallet_observatory.db import Store
from wallet_observatory.config import Config
from wallet_observatory.research import enroll,ensure_run,evaluate_research,experiment_summary,stats,matched
from wallet_observatory.positions import positions
from wallet_observatory.focus import poll_focus
from wallet_observatory.quotes import check_routes

class ResearchFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store(self.tmp.name+'/db');self.now=2_000_000_000;self.cfg=Config(focus_wallets=1)
        self.s.execute("INSERT INTO wallets(address,first_seen,last_seen) VALUES('w',?,?)",(self.now-100,self.now))
        self.s.execute("INSERT INTO tokens(mint,source,first_seen,last_seen) VALUES('m','test',?,?)",(self.now-100,self.now))
    def signal(self,wallet='w',mint='m',at=None):
        at=at or self.now+10
        return self.s.execute("INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible,observation_class) VALUES(?,?,?,?,1,'fresh')",(int(at),wallet,mint,at))
    def sample(self,at=None):
        ensure_run(self.s,self.cfg,self.now);sid=self.signal(at=at);enroll(self.s,self.cfg,self.now+20)
        return self.s.one('SELECT * FROM research_samples')
    def snap(self,at,price=1,liquidity=1e6):
        self.s.execute("INSERT INTO snapshots(mint,observed_at,price,liquidity,status,market_cap_usd) VALUES('m',?,?,?,'observed',20000)",(at,price,liquidity))
class ResearchTests(ResearchFixture):
    def test_membership_frozen_and_no_old_signals(self):
        self.signal(at=self.now-20);run=ensure_run(self.s,self.cfg,self.now)
        self.s.execute("INSERT INTO wallets(address,first_seen,last_seen,status) VALUES('new',?,?,'active')",(self.now,self.now+100))
        self.assertEqual(ensure_run(self.s,self.cfg,self.now+100)['id'],run['id'])
        enroll(self.s,self.cfg,self.now+100)
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM research_samples')['n'],0)
        self.assertEqual(self.s.one('SELECT wallet FROM research_members')['wallet'],'w')
    def test_one_wallet_token_and_no_future_matching_attributes(self):
        ensure_run(self.s,self.cfg,self.now);self.signal();self.signal(at=self.now+11)
        self.snap(self.now+12)
        enroll(self.s,self.cfg,self.now+20)
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM research_samples')['n'],1)
        self.assertIsNone(self.s.one('SELECT market_cap FROM research_samples')['market_cap'])
    def test_exact_targets_missing_exit_and_immutable_results(self):
        sample=self.sample();at=sample['detected_at'];self.snap(at+60);self.snap(at+3660,2)
        evaluate_research(self.s,at+3800)
        r=self.s.one('SELECT * FROM research_results WHERE delay=60 AND horizon=3600')
        self.assertEqual(r['status'],'estimated');self.assertGreater(r['return_pct'],80)
        self.assertEqual(r['profitable_seconds'],0);self.assertGreater(r['max_gap'],120)
        self.snap(at+3661,100);evaluate_research(self.s,at+4000)
        self.assertEqual(self.s.one('SELECT return_pct FROM research_results WHERE delay=60 AND horizon=3600')['return_pct'],r['return_pct'])
    def test_unexecutable_exit_is_not_zero_or_win(self):
        sample=self.sample();at=sample['detected_at'];self.snap(at+60);self.snap(at+3660,2,1)
        evaluate_research(self.s,at+3800)
        r=self.s.one('SELECT * FROM research_results WHERE delay=60 AND horizon=3600')
        self.assertEqual(r['status'],'unexecutable_exit');self.assertIsNone(r['return_pct'])
    def test_matching_excludes_same_token_and_unknown_attributes(self):
        a=dict(wallet='a',mint='a',detected_at=0,token_age=100,market_cap=20000,liquidity=100000)
        b={**a,'wallet':'b','mint':'b'}
        self.assertTrue(matched(a,b));self.assertFalse(matched(a,{**b,'mint':'a'}));self.assertFalse(matched(a,{**b,'market_cap':None}))
    def test_biggest_winner_and_missing_coverage(self):
        s=stats([{'return_pct':v,'status':'estimated' if v is not None else 'missing_exit'} for v in (1000,-20,-10,None)])
        self.assertEqual(s['without_best'],-15);self.assertEqual(s['coverage'],75);self.assertEqual(s['mean_loss'],-15)
    def test_summary_pending_is_not_zero_performance(self):
        self.sample();e=experiment_summary(self.s,self.now+30)
        self.assertEqual(e['selected_tokens'],1);self.assertIsNone(e['comparisons'][0]['excess_mean'])

class PositionTests(ResearchFixture):
    def trade(self,side,qty,usd,at,price_age=0):
        tid=self.s.execute('''INSERT INTO trades(signature,wallet,mint,side,quantity,quote_quantity,chain_time,observed_at,venue,quality)
           VALUES(?,'w','m',?,?,1,?,?,'test','balance-delta observation')''',(str(at),side,qty,at,at))
        if usd is not None:self.s.execute('INSERT INTO trade_values VALUES(?,?,?)',(tid,usd,at+price_age))
    def test_fifo_partial_exit_and_unknown_sale(self):
        self.trade('sell',5,100,1);self.trade('buy',10,100,2);self.trade('sell',4,80,3)
        p=positions(self.s,'w')[0]
        self.assertEqual(p['matched_realized_usd'],40);self.assertEqual(p['observed_remaining'],6)
        self.assertEqual(p['unmatched_sold_quantity'],5);self.assertEqual(p['action'],'partial exit')
    def test_later_prices_cannot_become_historical_profit(self):
        self.trade('buy',10,100,1,86400);self.trade('sell',10,200,2,86400)
        p=positions(self.s,'w')[0];self.assertIsNone(p['matched_realized_usd']);self.assertEqual(p['cost_coverage'],0)
    def test_incoming_unknown_tokens_not_free_profit(self):
        self.s.execute("INSERT INTO token_flows VALUES('transfer','w','m',1,20)")
        self.trade('buy',10,100,2);self.trade('sell',20,500,3)
        p=positions(self.s,'w')[0];self.assertIsNone(p['matched_realized_usd']);self.assertEqual(p['observed_remaining'],10)
    def test_outgoing_transfer_invalidates_remaining_cost(self):
        self.trade('buy',10,100,1);self.s.execute("INSERT INTO token_flows VALUES('transfer','w','m',2,-4)")
        self.trade('sell',6,120,3)
        self.assertIsNone(positions(self.s,'w')[0]['matched_realized_usd'])

class QuoteTests(ResearchFixture):
    def test_disabled_never_requests_and_failed_exit_visible(self):
        class P:
            store=self.s
            def request(self,url,**kwargs):
                self.calls=getattr(self,'calls',0)+1
                assert '/order?' in url and 'taker' not in url and 'execute' not in url
                return {'outAmount':'123'} if self.calls==1 else {'outAmount':'0'}
        p=P();check_routes(self.s,p,self.cfg,['m']);self.assertFalse(hasattr(p,'calls'))
        self.cfg.jupiter_api_key='fake';check_routes(self.s,p,self.cfg,['m'])
        self.assertEqual(self.s.one('SELECT status FROM route_checks')['status'],'exit_quote_unavailable')
        self.assertEqual(self.s.one('SELECT requests FROM quote_budget')['requests'],2)
    def test_quote_cap_counts_failed_attempts(self):
        class P:
            store=self.s
            def request(self,*args,**kwargs):return {'outAmount':'123'}
        self.cfg.jupiter_api_key='fake';self.cfg.quote_daily_cap=1
        check_routes(self.s,P(),self.cfg,['m'])
        self.assertEqual(self.s.one('SELECT requests FROM quote_budget')['requests'],1)
        self.assertIsNone(self.s.one('SELECT roundtrip_usdc FROM route_checks')['roundtrip_usdc'])

class FocusTests(ResearchFixture):
    def test_poll_is_bounded_and_preserves_unprocessed_transactions(self):
        from wallet_observatory.collector import Collector
        from test_observatory import transaction
        class P:
            def __init__(self):self.calls=[]
            def signatures(self,*args,**kwargs):
                self.calls.append('page');return [{'signature':str(i),'blockTime':i} for i in range(19,-1,-1)]
            def transaction(self,sig,bucket):self.calls.append('tx');return transaction()
        p=P();c=Collector(self.s,self.cfg,p);run=ensure_run(self.s,self.cfg,self.now)
        with patch.object(c,'ingest',return_value=True):poll_focus(c,run,self.now)
        self.assertEqual(p.calls,['page','tx','tx'])
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM focus_queue')['n'],18)
        self.assertEqual(self.s.one('SELECT cursor FROM focus_state')['cursor'],'19')
        poll_focus(c,run,self.now+1);self.assertEqual(len(p.calls),3)
    def test_initial_holdings_do_not_have_zero_cost_basis(self):
        from wallet_observatory.positions import record_flows
        from test_observatory import transaction,key
        tx=transaction()
        with self.s.connect() as db:record_flows(db,'x',tx,key(1))
        self.assertIsNotNone(self.s.one('SELECT * FROM token_openings'))
