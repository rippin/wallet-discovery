import base64
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from wallet_observatory.db import Store
from wallet_observatory.config import Config
from wallet_observatory.chain import PUMP,LAB,USDC,IDL,parse,ALPHABET
from wallet_observatory.demo import key
from wallet_observatory.collector import Collector
from wallet_observatory.providers import Providers,BudgetExceeded
from wallet_observatory.analytics import evaluate,paper_open,paper_close
from wallet_observatory.server import make_server


def encode(raw):
    n=int.from_bytes(raw,'big'); s=''
    while n:
        n,r=divmod(n,58);s=ALPHABET[r]+s
    return '1'*(len(raw)-len(raw.lstrip(b'\0')))+s


def transaction(program=PUMP,side='buy',stamp=None):
    mint=key(30);wallet=key(1)
    name=side if program==PUMP else side+'_exact_in'
    venue='pumpfun' if program==PUMP else 'launchlab'
    discriminator=next(d for d,s in IDL[venue].items() if s['name']==name)
    accounts=[]
    for account in IDL[venue][discriminator]['accounts']:
        accounts.append(wallet if account in ('user','payer') else mint if account in ('mint','base_mint','base_token_mint') else USDC if account in ('quote_mint','quote_token_mint') else key(20))
    if program==PUMP:
        # Use v2 explicit-quote instructions for this stablecoin fixture.
        name=side+'_v2'
        discriminator=next(d for d,s in IDL[venue].items() if s['name']==name)
        accounts=[wallet if a=='user' else mint if a=='base_mint' else USDC if a=='quote_mint' else key(20) for a in IDL[venue][discriminator]['accounts']]
    def bal(mint,amount):return {'owner':wallet,'mint':mint,'uiTokenAmount':{'amount':str(amount),'decimals':6},'accountIndex':1 if mint!=USDC else 2}
    return {'blockTime':stamp or time.time(),'transaction':{'message':{'accountKeys':[{'pubkey':wallet,'signer':True}],
          'instructions':[{'programId':program,'data':encode(bytes.fromhex(discriminator)+bytes(16)),
                           'accounts':accounts}]}},
          'meta':{'err':None,'fee':5000,'preBalances':[1000000000],'postBalances':[999995000],
                  'preTokenBalances':[bal(mint,0 if side=='buy' else 10000000),bal(USDC,1000000000 if side=='buy' else 0)],
                  'postTokenBalances':[bal(mint,10000000 if side=='buy' else 0),bal(USDC,0 if side=='buy' else 1000000000)]}}

class Case(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.cfg=Config(db=self.store.path)
    def tearDown(self):self.tmp.cleanup()
    def snap(self,mint,at,price=1,liquidity=1e6,status='observed'):
        self.store.execute('INSERT INTO snapshots(mint,observed_at,price,liquidity,status) VALUES(?,?,?,?,?)',(mint,at,price,liquidity,status))
    def signal(self,at):
        w=key(1);mint=key(30)
        self.store.execute('INSERT OR IGNORE INTO wallets(address,first_seen,last_seen) VALUES(?,?,?)',(w,at-10,at))
        sid=self.store.execute('INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible) VALUES(?,?,?,?,1)',(int(at),w,mint,at))
        return sid,mint
    def test_real_finalized_launchlab_fixtures(self):
        for name in ('launchlab_arbitrary_quote','launchlab_sol_quote'):
            tx=json.loads((Path(__file__).parent/'fixtures'/'observatory'/(name+'.json')).read_text())
            trades,_,status=parse(tx)
            self.assertEqual(status,'swap_observed')
            self.assertEqual(trades[0]['venue'],'launchlab')
            self.assertEqual(trades[0]['side'],'buy')
            self.assertGreater(trades[0]['quantity'],0)

    def test_scan_retry_retains_cursor_and_deduplicates(self):
        now=time.time();w=key(1)
        self.store.execute('INSERT INTO wallets(address,first_seen,last_seen,cursor) VALUES(?,?,?,?)',(w,now-60,now,'old'))
        tx=transaction(stamp=now)
        class Fake:
            fail=True
            def signatures(self,*args):return [{'signature':'new','err':None},{'signature':'old','err':None}]
            def transaction(inner,*args):return None if inner.fail else tx
        fake=Fake();c=Collector(self.store,self.cfg,fake)
        wallet=self.store.one('SELECT * FROM wallets')
        c.scan_wallet(wallet,'tracking')
        self.assertEqual(self.store.one('SELECT cursor FROM wallets')['cursor'],'old')
        fake.fail=False;c.scan_wallet(wallet,'tracking')
        self.assertEqual(self.store.one('SELECT cursor FROM wallets')['cursor'],'new')
        c.scan_wallet(wallet,'tracking')
        self.assertEqual(self.store.one('SELECT COUNT(*) n FROM trades')['n'],1)

    def test_decode_pump_and_lab(self):
        for program in (PUMP,LAB):
            for side in ('buy','sell'):
                trades,links,state=parse(transaction(program,side))
                self.assertEqual(state,'swap_observed');self.assertEqual(trades[0]['side'],side)
                self.assertEqual(trades[0]['quote_quantity'],1000)
                if program==LAB:self.assertIsNotNone(trades[0]['platform'])
    def test_launchlab_arbitrary_quote_and_user_attribution(self):
        tx=transaction(LAB);quote=key(42)
        ix=tx['transaction']['message']['instructions'][0]
        ix['accounts'][10]=quote
        for side in ('preTokenBalances','postTokenBalances'):
            tx['meta'][side][1]['mint']=quote
        trades,_,_=parse(tx)
        self.assertEqual(trades[0]['quote_mint'],quote)
        self.assertEqual(trades[0]['mint'],key(30))
        ix['accounts'][0]=key(2)
        self.assertFalse(parse(tx)[0])

    def test_failed_and_plain_transfer_not_trades(self):
        tx=transaction();tx['meta']['err']={'InstructionError':[0,'failed']}
        self.assertEqual(parse(tx)[0],[])
        tx=transaction();tx['transaction']['message']['instructions']=[{'program':'system','parsed':{'type':'transfer','info':{'source':key(1),'destination':key(2),'lamports':100}}}]
        trades,links,_=parse(tx);self.assertFalse(trades);self.assertEqual(len(links),1)
    def test_unsupported_instruction_not_swap(self):
        tx=transaction();tx['transaction']['message']['instructions'][0]['data']=encode(bytes(24))
        self.assertFalse(parse(tx)[0])
    def test_complex_multi_token_is_ambiguous(self):
        tx=transaction();tx['transaction']['message']['instructions']=[{'programId':'CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C','data':encode(hashlib.sha256(b'global:swap_base_input').digest()[:8]),'accounts':[]}];extra=dict(tx['meta']['postTokenBalances'][0]);extra['mint']=key(31)
        tx['meta']['postTokenBalances'].append(extra)
        self.assertEqual(parse(tx)[2],'ambiguous_swap')
    def test_idempotent_ingest_and_no_discovery_hindsight(self):
        self.cfg.min_market_cap=0
        c=Collector(self.store,self.cfg); tx=transaction()
        c.ingest('s1',tx,'discovery');c.ingest('s1',tx,'discovery')
        self.assertEqual(self.store.one('SELECT COUNT(*) n FROM trades')['n'],1)
        self.assertEqual(self.store.one('SELECT eligible FROM signals')['eligible'],0)
        time.sleep(.002);tx2=transaction()
        c.ingest('s2',tx2,'tracking',key(1))
        self.assertEqual(self.store.one('SELECT eligible FROM signals ORDER BY id DESC')['eligible'],1)
    def test_old_backfill_not_prospective(self):
        c=Collector(self.store,self.cfg); c.ingest('old',transaction(stamp=time.time()-3600),'tracking',key(1))
        self.assertEqual(self.store.one('SELECT eligible FROM signals')['eligible'],0)
    def test_observed_time_used_and_no_future_cherry_pick(self):
        at=time.time()-100000;sid,mint=self.signal(at)
        self.snap(mint,at+899,0.1);self.snap(mint,at+901,1);self.snap(mint,at+87301,1.2)
        evaluate(self.store)
        o=self.store.one('SELECT * FROM outcomes WHERE signal_id=? AND delay=900 AND horizon=86400',(sid,))
        self.assertEqual(o['entry_price'],1);self.assertEqual(o['status'],'estimated');self.assertLess(o['return_pct'],20)
    def test_missing_data_not_zero_or_winner(self):
        at=time.time()-100000;sid,mint=self.signal(at);evaluate(self.store)
        o=self.store.one('SELECT * FROM outcomes WHERE signal_id=? AND delay=900 AND horizon=86400',(sid,))
        self.assertIsNone(o['return_pct']);self.assertEqual(o['status'],'missing_data')
    def test_low_liquidity_not_fill(self):
        at=time.time()-100000;sid,mint=self.signal(at)
        self.snap(mint,at+901,1,1000);self.snap(mint,at+87301,2,1000);evaluate(self.store)
        self.assertEqual(self.store.one('SELECT status FROM outcomes WHERE signal_id=? AND delay=900 AND horizon=86400',(sid,))['status'],'insufficient_liquidity')
    def test_paper_partial_full_and_minimum(self):
        now=time.time();mint=key(30);self.snap(mint,now)
        with self.assertRaises(ValueError):paper_open(self.store,mint,499)
        pid=paper_open(self.store,mint,500);first=paper_close(self.store,pid,50)
        self.assertLess(first['pnl'],0)
        p=self.store.one('SELECT * FROM paper WHERE id=?',(pid,));self.assertAlmostEqual(p['remaining'],p['quantity']/2)
        paper_close(self.store,pid,100)
        with self.assertRaises(ValueError):paper_close(self.store,pid,100)
        self.assertEqual(self.store.one('SELECT COUNT(*) n FROM paper_exits')['n'],2)
    def test_stale_and_nonfinite_paper_rejected(self):
        mint=key(30);self.snap(mint,time.time()-1000)
        for amount in (500,float('nan'),float('inf')):
            with self.assertRaises(ValueError):paper_open(self.store,mint,amount)
    def test_latest_unpriced_blocks_paper(self):
        mint=key(30);self.snap(mint,time.time()-20);self.snap(mint,time.time(),None,None,'unpriced')
        with self.assertRaises(ValueError):paper_open(self.store,mint,500)
    def test_budget_hard_limit_persists(self):
        cfg=Config(monthly_credits=1000);p=Providers(self.store,cfg)
        p.reserve('tracking',10)
        with self.assertRaises(BudgetExceeded):Providers(Store(self.store.path),cfg).reserve('tracking',1000)
        self.assertEqual(self.store.one('SELECT SUM(credits) n FROM budgets')['n'],10)
    def test_dormant_wallet_can_return(self):
        now=time.time();w=key(1)
        self.store.execute('INSERT INTO wallets(address,first_seen,last_seen) VALUES(?,?,?)',(w,now-1e6,now-1e6))
        evaluate(self.store);self.assertEqual(self.store.one('SELECT status FROM wallets')['status'],'dormant')
        self.store.execute('UPDATE wallets SET last_seen=?',(now,));evaluate(self.store)
        self.assertEqual(self.store.one('SELECT status FROM wallets')['status'],'candidate')
    def test_http_auth_csrf_and_static(self):
        cfg=Config(password='a-very-long-test-password',port=0)
        server=make_server(self.store,cfg);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        root=f'http://127.0.0.1:{server.server_port}'
        auth={'Authorization':'Basic '+base64.b64encode(('research:'+cfg.password).encode()).decode()}
        try:
            with self.assertRaises(HTTPError) as cm:urlopen(root+'/api/summary')
            self.assertEqual(cm.exception.code,401)
            with urlopen(Request(root,headers=auth)) as r:self.assertIn(b'Wallet Observatory',r.read())
            req=Request(root+'/api/watch',data=json.dumps({'address':key(1)}).encode(),headers={**auth,'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as cm:urlopen(req)
            self.assertEqual(cm.exception.code,403)
            req.add_header('X-Observatory','1')
            with urlopen(req) as r:self.assertTrue(json.load(r)['ok'])
            req.add_header('Origin','https://attacker.example')
            with self.assertRaises(HTTPError) as cm:urlopen(req)
            self.assertEqual(cm.exception.code,403)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
