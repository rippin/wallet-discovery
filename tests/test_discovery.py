import json,time,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
from wallet_observatory.db import Store
from wallet_observatory.config import Config
from wallet_observatory.collector import Collector
from wallet_observatory.discovery import Discovery,coverage
from wallet_observatory.chain import PUMP,LAB,parse
from wallet_observatory.providers import ProviderError
from test_observatory import transaction,key

class Fake:
    def __init__(self):self.pages={};self.transactions={};self.requests=[];self.fail=False;self.cap=20000
    def signatures(self,program,bucket,before=None,limit=None):
        self.requests.append(('page',program,before))
        return self.pages.get((program,before),[])
    def transaction(self,sig,bucket):
        self.requests.append(('tx',sig))
        if self.fail:raise ProviderError('temporary')
        return self.transactions.get(sig)
    def market(self,mints):
        return [{'mint':m,'price':1,'liquidity':100000,'volume':1,'pair':'test','symbol':'TEST','status':'observed','market_cap_usd':self.cap} for m in mints]

def sig(name,failed=False):return {'signature':name,'blockTime':time.time(),'err':{'failed':1} if failed else None}

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store(self.tmp.name+'/db');self.cfg=Config(min_purchase_usd=0,min_market_cap=0,discovery_page_size=2)
        self.f=Fake();self.c=Collector(self.s,self.cfg,self.f);self.d=Discovery(self.c)
    def seed(self):
        self.f.pages[(PUMP,None)]=[sig('old')];self.d.enumerate_page(PUMP)
        self.s.execute("UPDATE discovery_queue SET status='inspected'")
    def test_cursor_window_spans_restart_and_processes_oldest_first(self):
        self.seed();self.f.pages[(PUMP,None)]=[sig('new3'),sig('new2')]
        self.f.pages[(PUMP,'new2')]=[sig('new1'),sig('old')]
        self.d.enumerate_page(PUMP);self.assertFalse(self.d.inspect_one(PUMP))
        Discovery(Collector(self.s,self.cfg,self.f)).enumerate_page(PUMP)
        for name in ('new1','new2','new3'):self.f.transactions[name]=transaction()
        for _ in range(3):self.d.inspect_one(PUMP)
        self.assertEqual([r[1] for r in self.f.requests if r[0]=='tx'],['new1','new2','new3'])
        self.d.enumerate_page(PUMP)
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM discovery_queue')['n'],4)
    def test_network_failure_keeps_item_pending(self):
        self.f.pages[(PUMP,None)]=[sig('a')];self.d.enumerate_page(PUMP);self.f.fail=True
        with self.assertRaises(ProviderError):self.d.inspect_one(PUMP)
        self.assertEqual(self.s.one('SELECT status FROM discovery_queue')['status'],'pending')
        self.f.fail=False;self.f.transactions['a']=transaction();self.d.inspect_one(PUMP)
        self.assertEqual(self.s.one('SELECT status FROM discovery_queue')['status'],'inspected')
    def test_missing_transaction_bounded_retries(self):
        self.f.pages[(PUMP,None)]=[sig('a')];self.d.enumerate_page(PUMP)
        for _ in range(3):self.d.inspect_one(PUMP)
        self.assertFalse(self.d.inspect_one(PUMP));self.assertEqual(coverage(self.s)[0]['unavailable'],1)
    def test_queue_cap_and_failed_are_visible(self):
        self.cfg.discovery_queue_cap=1;self.f.pages[(PUMP,None)]=[sig('a'),sig('b'),sig('c',True)]
        self.d.enumerate_page(PUMP);r=coverage(self.s)[0]
        self.assertEqual((r['available'],r['pending'],r['skipped'],r['failed']),(3,1,1,1))
    def test_page_limit_marks_unknown_gap(self):
        self.seed();self.cfg.discovery_max_pages=1;self.f.pages[(PUMP,None)]=[sig('a'),sig('b')]
        self.d.enumerate_page(PUMP);self.assertEqual(coverage(self.s)[0]['gaps'],1)
    def test_unique_buyers_counted_once_and_tick_is_bounded(self):
        for program in (PUMP,LAB):
            self.f.pages[(program,None)]=[sig(program+'a'),sig(program+'b')]
            for letter in ('a','b'):self.f.transactions[program+letter]=transaction()
        self.d.tick();self.assertLessEqual(len(self.f.requests),self.cfg.discovery_requests)
        self.assertEqual([x['unique_buyers'] for x in coverage(self.s)],[1,1])
    def test_market_cap_admission_unknown_below_then_above(self):
        self.cfg.min_market_cap=10000;tx=transaction();self.c.ingest('a',tx,'discovery')
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM wallets')['n'],0)
        self.f.cap=None;self.c.markets();self.assertEqual(self.s.one('SELECT COUNT(*) n FROM wallets')['n'],0)
        self.f.cap=10000;self.c.markets();self.assertEqual(self.s.one('SELECT COUNT(*) n FROM wallets')['n'],0)
        self.f.cap=10001;self.c.markets();self.assertEqual(self.s.one('SELECT COUNT(*) n FROM wallets')['n'],1)
        self.assertEqual(self.s.one('SELECT eligible FROM signals')['eligible'],0)
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM admission_pending')['n'],0)
    def test_tracked_wallet_bypasses_admission_filter(self):
        self.cfg.min_market_cap=10000;self.c.ingest('a',transaction(),'tracking',key(1))
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM wallets')['n'],1)

class RoutedLaunchLabTests(unittest.TestCase):
    def test_real_routed_transactions_recovered(self):
        rows=json.loads((Path(__file__).parent/'fixtures/observatory/launchlab_routed.json').read_text())
        for row,side in zip(rows,('buy','sell')):
            trades,_,status=parse(row['tx']);self.assertEqual(status,'swap_observed')
            self.assertEqual(trades[0]['venue'],'launchlab');self.assertEqual(trades[0]['side'],side)
            self.assertIn('instruction-local',trades[0]['quality'])
    def test_unscoped_transfers_do_not_supply_quote(self):
        row=json.loads((Path(__file__).parent/'fixtures/observatory/launchlab_routed.json').read_text())[0]
        tx=copy.deepcopy(row['tx'])
        for group in tx['meta']['innerInstructions']:
            for ix in group['instructions']:ix.pop('stackHeight',None)
        self.assertEqual(parse(tx)[2],'ambiguous_swap')
