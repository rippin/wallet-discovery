import tempfile
import unittest
from unittest.mock import patch
from wallet_observatory.config import Config
from wallet_observatory.db import Store
from wallet_observatory.providers import Providers,ProviderError,RateLimited,BudgetExceeded

class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store(self.tmp.name+'/test.sqlite3')
        self.p=Providers(self.s,Config(rpc_url='https://mainnet.helius-rpc.com/?api-key=test'))
        self.sleep=patch('wallet_observatory.providers.time.sleep');self.sleep.start();self.addCleanup(self.sleep.stop)
    def call(self):return self.p.rpc('getSignaturesForAddress',['test'],'discovery')
    def test_local_budget_fallback(self):
        with patch.object(self.p,'reserve',side_effect=BudgetExceeded()),patch.object(self.p,'request',return_value={'result':[]}) as req:
            self.assertEqual(self.call(),[])
            self.assertEqual(req.call_args.args[0],'https://solana-rpc.publicnode.com')
        self.assertEqual(self.s.meta('rpc_fallback_usage')['requests'],1)
    def test_429_persists_cooldown(self):
        with patch.object(self.p,'request',side_effect=[RateLimited(),{'result':[]}]):self.call()
        p=Providers(self.s,self.p.config)
        with patch.object(p,'request',return_value={'result':[]}) as req:
            p.rpc('getTransaction',[],'tracking')
            self.assertEqual(req.call_args.args[0],'https://solana-rpc.publicnode.com')
    def test_auth_error_not_hidden(self):
        with patch.object(self.p,'request',side_effect=ProviderError('401')) as req:
            with self.assertRaises(ProviderError):self.call()
            self.assertEqual(req.call_count,1)
    def test_public_failure_backoff(self):
        with patch.object(self.p,'reserve',side_effect=BudgetExceeded()),patch.object(self.p,'request',side_effect=ProviderError()) as req:
            for _ in range(2):
                with self.assertRaises(ProviderError):self.call()
            self.assertEqual(req.call_count,1)
    def test_primary_success_does_not_fallback(self):
        with patch.object(self.p,'request',return_value={'result':[]}) as req:
            self.call();self.assertEqual(req.call_count,1)
        self.assertEqual(self.s.meta('rpc_route')['provider'],'primary')
    def test_non_helius_budget_does_not_fallback(self):
        self.p.config.rpc_url='https://rpc.example.com'
        with patch.object(self.p,'reserve',side_effect=BudgetExceeded()),patch.object(self.p,'request') as req:
            with self.assertRaises(BudgetExceeded):self.call()
            req.assert_not_called()
    def test_public_daily_cap(self):
        from datetime import datetime,timezone
        self.s.meta('rpc_fallback_usage',{'day':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'requests':10000})
        with patch.object(self.p,'reserve',side_effect=BudgetExceeded()),patch.object(self.p,'request') as req:
            with self.assertRaises(BudgetExceeded):self.call()
            req.assert_not_called()
