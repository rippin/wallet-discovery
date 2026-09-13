import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from wallet_observatory.db import Store,SCHEMA
from wallet_observatory.rules import classify,cohort_stats
from wallet_observatory.analytics import evaluate
from wallet_observatory.collector import Collector
from wallet_observatory.config import Config
from test_observatory import transaction,key

class ObservationRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite3';self.store=Store(self.path)
        self.now=2000000000.;self.wallet=key(1)
        self.store.execute('INSERT INTO wallets(address,first_seen,last_seen) VALUES(?,?,?)',(self.wallet,self.now-40*86400,self.now))
    def tearDown(self):self.tmp.cleanup()
    def signal(self,mint,at,cohort='delayed',ret=15):
        sid=self.store.execute('INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible,observation_class,rule_version) VALUES(?,?,?,?,1,?,2)',
                               (int(at),self.wallet,mint,at,cohort))
        if ret is not None:
            self.store.execute('INSERT INTO outcomes VALUES(?,?,?,?,?,?,?,?,?)',(sid,900,86400,at+900,at+87300,1,1.2,ret,'estimated'))
        return sid
    def test_classification_boundaries(self):
        for age,kind in [(0,'fresh'),(600,'fresh'),(601,'delayed'),(3600,'delayed'),(3601,'late'),(86400,'late')]:
            self.assertEqual(classify(self.now-1e6,self.now-age,self.now),(kind,True))
        self.assertEqual(classify(None,self.now-10,self.now),('discovery',False))
        self.assertEqual(classify(self.now-10,self.now-11,self.now),('backfill',False))
        self.assertEqual(classify(self.now-10,self.now+1,self.now),('future',False))
    def test_thirty_minute_lag_is_eligible_and_measured_from_detection(self):
        with patch('wallet_observatory.collector.time.time',return_value=self.now):
            Collector(self.store,Config(min_purchase_usd=0,)).ingest('slow',transaction(stamp=self.now-1800),'tracking',self.wallet)
        s=self.store.one('SELECT * FROM signals')
        self.assertEqual((s['eligible'],s['observation_class'],s['rule_version']),(1,'delayed',2))
        self.assertEqual(s['detected_at'],self.now)
        for at,price in [(self.now-900,0.01),(self.now+901,1),(self.now+87301,1.2)]:
            self.store.execute('INSERT INTO snapshots(mint,observed_at,price,liquidity,status) VALUES(?,?,?,?,?)',(key(30),at,price,1e6,'observed'))
        evaluate(self.store,self.now+88000)
        o=self.store.one('SELECT * FROM outcomes WHERE delay=900 AND horizon=86400')
        self.assertEqual(o['entry_price'],1)
    def test_rediscovery_of_known_wallet_can_qualify(self):
        with patch('wallet_observatory.collector.time.time',return_value=self.now):
            c=Collector(self.store,Config(min_purchase_usd=0,));tx=transaction(stamp=self.now-1800)
            c.ingest('known-discovery',tx,'discovery');c.ingest('known-discovery',tx,'tracking',self.wallet)
        self.assertEqual(self.store.one('SELECT COUNT(*) n FROM signals')['n'],1)
        self.assertEqual(self.store.one('SELECT observation_class FROM signals')['observation_class'],'delayed')
    def test_cohorts_not_combined_for_promotion(self):
        for i in range(8):self.signal(key(i+30),self.now-2*86400-i,'fresh' if i<4 else 'delayed')
        evaluate(self.store,self.now)
        self.assertEqual(self.store.one('SELECT status FROM wallets')['status'],'candidate')
        stats=cohort_stats(self.store,self.wallet,self.now)
        self.assertEqual([s['priced_samples'] for s in stats[:2]],[4,4])
    def test_delayed_cohort_can_qualify(self):
        for i in range(8):self.signal(key(i+30),self.now-2*86400-i)
        evaluate(self.store,self.now)
        w=self.store.one('SELECT * FROM wallets')
        self.assertEqual(w['status'],'active');self.assertIn('delayed',w['reason'])
    def test_inactive_winner_goes_dormant(self):
        for i in range(8):self.signal(key(i+30),self.now-10*86400-i)
        self.store.execute('UPDATE wallets SET last_seen=?',(self.now-8*86400,))
        evaluate(self.store,self.now)
        self.assertEqual(self.store.one('SELECT status FROM wallets')['status'],'dormant')
    def test_old_first_signal_does_not_block_new_window(self):
        self.signal(key(30),self.now-40*86400,ret=-50)
        self.signal(key(30),self.now-2*86400,ret=20)
        self.signal(key(30),self.now-86400-2000,ret=100)
        group=cohort_stats(self.store,self.wallet,self.now)[1]
        self.assertEqual(group['priced_samples'],1);self.assertEqual(group['mean_return'],20)
    def test_missing_outcome_counts_against_coverage(self):
        self.signal(key(30),self.now-2*86400,ret=10)
        self.signal(key(31),self.now-2*86400-1,ret=None)
        group=cohort_stats(self.store,self.wallet,self.now)[1]
        self.assertEqual(group['coverage'],50)
    def test_promising_candidates_get_fifteen_minute_schedule(self):
        for i in range(3):self.signal(key(i+30),self.now-2*86400-i)
        class EmptyProvider:
            def signatures(self,*args):return []
        wallet=self.store.one('SELECT * FROM wallets')
        with patch('wallet_observatory.collector.time.time',return_value=self.now):
            Collector(self.store,Config(min_purchase_usd=0,),EmptyProvider()).scan_wallet(wallet,'tracking')
        self.assertEqual(self.store.one('SELECT next_scan FROM wallets')['next_scan'],self.now+900)
    def test_legacy_winners_do_not_promote_under_new_rules(self):
        for i in range(8):self.signal(key(i+30),self.now-2*86400-i,'legacy')
        evaluate(self.store,self.now)
        self.assertEqual(self.store.one('SELECT status FROM wallets')['status'],'candidate')
        self.assertEqual(cohort_stats(self.store,self.wallet,self.now)[3]['priced_samples'],8)

    def test_migration_preserves_legacy_eligibility(self):
        old=Path(self.tmp.name)/'v1.sqlite3'
        with sqlite3.connect(old) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible) VALUES(1,'wallet','mint',1,0)")
        first=Store(old);second=Store(old)
        s=second.one('SELECT * FROM signals')
        self.assertEqual((s['eligible'],s['observation_class'],s['rule_version']),(0,'legacy',1))
        self.assertEqual(second.meta('schema_version'),3)
