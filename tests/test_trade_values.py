import tempfile,time,unittest
from wallet_observatory.db import Store
from wallet_observatory.config import Config
from wallet_observatory.collector import Collector
from wallet_observatory.trade_values import value_trades,recent_trades
from test_observatory import transaction,key

class TradeValueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store(self.tmp.name+'/db')
        Collector(self.s,Config()).ingest('buy',transaction(),'tracking',key(1))
        self.t=self.s.one('SELECT * FROM trades')
    def price(self,value,at=None):
        self.s.execute('INSERT OR REPLACE INTO quote_prices VALUES(?,?,?)',(self.t['quote_mint'],value,at or time.time()))
    def test_buys_and_sells_frozen_and_later_conversion_labeled(self):
        self.s.execute("UPDATE trades SET chain_time=?",(time.time()-86400,))
        self.s.execute('''INSERT INTO trades(signature,wallet,mint,side,quantity,quote_mint,quote_quantity,chain_time,observed_at,venue,quality)
          SELECT 'sell',wallet,mint,'sell',quantity,quote_mint,quote_quantity,chain_time+10,observed_at,venue,quality FROM trades''')
        self.price(150);value_trades(self.s)
        rows=recent_trades(self.s,key(1))
        self.assertEqual([r['side'] for r in rows],['sell','buy'])
        self.assertTrue(all(r['usd_basis']=='later price conversion' for r in rows))
        self.assertAlmostEqual(rows[0]['usd_amount'],self.t['quote_quantity']*150)
        self.price(200);value_trades(self.s)
        self.assertEqual(recent_trades(self.s)[0]['usd_amount'],rows[0]['usd_amount'])
    def test_missing_stale_and_invalid_prices_not_zero_dollars(self):
        for price,at in [(None,time.time()),(100,time.time()-700),(-1,time.time())]:
            self.price(price,at);value_trades(self.s)
            self.assertIsNone(recent_trades(self.s)[0]['usd_amount'])
        self.assertEqual(recent_trades(self.s,key(2)),[])
