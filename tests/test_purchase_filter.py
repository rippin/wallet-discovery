import tempfile,time,unittest
from wallet_observatory.db import Store
from wallet_observatory.config import Config
from wallet_observatory.collector import Collector
from wallet_observatory.chain import parse
from test_observatory import transaction,key

class PurchaseFilterTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.s=Store(t.name+'/db');self.c=Collector(self.s,Config(min_market_cap=0,min_purchase_usd=100))
        self.tx=transaction();self.trade=parse(self.tx)[0][0]
    def price(self,usd,age=0):
        self.s.execute('INSERT OR REPLACE INTO quote_prices VALUES(?,?,?)',(self.trade['quote_mint'],usd/self.trade['quote_quantity'],time.time()-age))
    def count(self):return self.s.one('SELECT COUNT(*) n FROM wallets')['n']
    def test_exactly_100_admitted(self):
        self.price(100);self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),1)
    def test_small_purchase_stays_small_after_quote_appreciation(self):
        self.price(50);self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),0)
        self.price(200);self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),0)
        self.assertAlmostEqual(self.s.one('SELECT estimated_usd FROM admission_values')['estimated_usd'],50)
    def test_unknown_then_known_price(self):
        self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),0)
        self.price(150);self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),1)
        self.assertEqual(self.s.one('SELECT eligible FROM signals')['eligible'],0)
    def test_stale_quote_remains_unknown(self):
        self.price(200,age=601);self.c.ingest('buy',self.tx,'discovery');self.assertEqual(self.count(),0)
        self.assertIsNone(self.s.one('SELECT estimated_usd FROM admission_values')['estimated_usd'])
    def test_existing_wallet_small_buy_retained(self):
        self.price(150);self.c.ingest('buy',self.tx,'discovery')
        self.price(1);self.c.ingest('small',self.tx,'tracking',key(1))
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM trades')['n'],2)
