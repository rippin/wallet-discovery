import hashlib
import json
import threading
import time

from .chain import PUMP, LAB, parse
from .providers import Providers, ProviderError, BudgetExceeded
from .analytics import evaluate

class Collector:
    def __init__(self,store,config,providers=None):
        self.store,self.config=store,config
        self.providers=providers or Providers(store,config)
        self.stop=threading.Event()

    def ingest(self,signature,tx,bucket,watch=None):
        if not tx or tx.get('blockTime') is None:
            self.store.event('coverage','Transaction unavailable; historical coverage incomplete')
            return False
        now=time.time(); chain_time=tx['blockTime']
        trades,links,status=parse(tx)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?)',
                       (signature,chain_time,now,json.dumps(tx,separators=(',',':')),status))
            for t in trades:
                discovery=watch is None
                if discovery and not(t['venue'] in ('pumpfun','launchlab') and t['side']=='buy'):
                    continue
                if watch and t['wallet']!=watch:
                    continue
                # Discovery is an activity sample, not a claim that this is the first buyer or launch.
                db.execute('''INSERT INTO wallets(address,first_seen,last_seen,cursor) VALUES(?,?,?,?)
                    ON CONFLICT(address) DO UPDATE SET last_seen=MAX(last_seen,excluded.last_seen)''',
                    (t['wallet'],now,chain_time,signature))
                db.execute('''INSERT INTO tokens(mint,source,platform,first_seen,last_seen) VALUES(?,?,?,?,?)
                    ON CONFLICT(mint) DO UPDATE SET last_seen=MAX(last_seen,excluded.last_seen)''',
                    (t['mint'],t['venue'],t['platform'],now,now))
                cur=db.execute('''INSERT OR IGNORE INTO trades(signature,wallet,mint,side,quantity,quote_mint,quote_quantity,chain_time,
                    observed_at,venue,platform,quality) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (signature,t['wallet'],t['mint'],t['side'],t['quantity'],t['quote_mint'],t['quote_quantity'],chain_time,now,t['venue'],t['platform'],t['quality']))
                if cur.rowcount and t['side']=='buy':
                    # No retrospective selection of the discovery trade; evaluate subsequent fresh buys only.
                    known=db.execute('SELECT first_seen FROM wallets WHERE address=?',(t['wallet'],)).fetchone()[0]
                    eligible=int(not discovery and chain_time>=known and 0<=now-chain_time<=600)
                    db.execute('INSERT OR IGNORE INTO signals(trade_id,wallet,mint,detected_at,eligible) VALUES(?,?,?,?,?)',
                               (cur.lastrowid,t['wallet'],t['mint'],now,eligible))
            if watch:
                for edge in links:
                    if watch in (edge['source'],edge['target']):
                        db.execute('INSERT OR IGNORE INTO links(source,target,signature,observed_at,kind,amount) VALUES(?,?,?,?,?,?)',
                                   (edge['source'],edge['target'],signature,now,edge['kind'],edge['amount']))
        return True

    def load_tx(self,sig,bucket):
        cached=self.store.one('SELECT raw FROM transactions WHERE signature=?',(sig,))
        return json.loads(cached['raw']) if cached else self.providers.transaction(sig,bucket)

    def discover(self):
        for program in (PUMP,LAB):
            page=self.providers.signatures(program,'discovery')
            # Hash sample per time window, before fetching/parsing or knowing token outcomes.
            window=int(time.time()//self.config.cycle_seconds)
            unseen=[p for p in page if not p.get('err') and not self.store.one('SELECT 1 FROM transactions WHERE signature=?',(p['signature'],))]
            sample=sorted(unseen,key=lambda p:hashlib.sha256(f'{window}:{p["signature"]}'.encode()).digest())[:self.config.discovery_sample]
            self.store.meta('sample_'+program,{'at':time.time(),'page_size':len(page),'sampled':len(sample),'method':'hash sample of latest signatures; activity-weighted, not uniform launches'})
            for item in sample:
                self.ingest(item['signature'],self.load_tx(item['signature'],'discovery'),'discovery')

    def scan_wallet(self,wallet,bucket):
        pending=[]; before=None; found=False; newest=None
        for _ in range(self.config.max_pages):
            page=self.providers.signatures(wallet['address'],bucket,before)
            if not page:
                found=True; break
            newest=newest or page[0]['signature']
            for item in page:
                if item['signature']==wallet['cursor']:
                    found=True; break
                pending.append(item)
            if found or len(page)<self.config.page_limit:
                found=True; break
            before=page[-1]['signature']
        if not found:
            self.store.event('coverage',f'{wallet["address"]}: scan page cap reached; older activity omitted')
        for item in reversed(pending):
            if not item.get('err'):
                if not self.ingest(item['signature'],self.load_tx(item['signature'],bucket),bucket,watch=wallet['address']):
                    # Leave the cursor unchanged so temporary unavailable txs can be retried.
                    return
        now=time.time()
        interval={'active':300,'candidate':1800,'cooldown':21600,'dormant':86400}.get(wallet['status'],1800)
        self.store.execute('UPDATE wallets SET cursor=COALESCE(?,cursor),last_scan=?,next_scan=? WHERE address=?',
                           (newest,now,now+interval,wallet['address']))

    def markets(self):
        # Open positions first, then tokens with pending 28-day outcomes; oldest sample first.
        rows=self.store.rows('''SELECT t.mint,MAX(s.observed_at) last_sample,
          EXISTS(SELECT 1 FROM paper p WHERE p.mint=t.mint AND p.remaining>0) held
          FROM tokens t LEFT JOIN snapshots s ON s.mint=t.mint
          WHERE t.last_seen>? OR EXISTS(SELECT 1 FROM paper p WHERE p.mint=t.mint AND p.remaining>0)
          GROUP BY t.mint ORDER BY held DESC,COALESCE(last_sample,0) ASC LIMIT ?''',(time.time()-35*86400,self.config.market_cap))
        for offset in range(0,len(rows),30):
            for s in self.providers.market([r['mint'] for r in rows[offset:offset+30]]):
                with self.store.connect() as db:
                    db.execute('INSERT INTO snapshots(mint,observed_at,price,liquidity,volume,pair,status) VALUES(?,?,?,?,?,?,?)',
                               (s['mint'],time.time(),s['price'],s['liquidity'],s['volume'],s['pair'],s['status']))
                    if s['symbol']:
                        db.execute('UPDATE tokens SET symbol=? WHERE mint=?',(s['symbol'],s['mint']))

    def cycle(self):
        self.store.meta('collector',{'status':'running','at':time.time()})
        for bucket in ('tracking','revisit'):
            statuses=('active','candidate') if bucket=='tracking' else ('cooldown','dormant')
            wallets=self.store.rows('SELECT * FROM wallets WHERE status IN (?,?) AND next_scan<=? ORDER BY next_scan ASC LIMIT ?',
                                   (*statuses,time.time(),self.config.wallets_per_cycle))
            for wallet in wallets:
                try:
                    self.scan_wallet(wallet,bucket)
                except BudgetExceeded as e:
                    self.store.event('quota',str(e)); break
                except ProviderError as e:
                    self.store.event('provider',str(e)); break
        for action in (self.discover,self.markets):
            try:
                action()
            except ProviderError as e:
                self.store.event('provider',str(e))
        evaluate(self.store)
        self.store.meta('collector',{'status':'waiting','at':time.time()})

    def run(self):
        while not self.stop.is_set():
            try:
                self.cycle()
            except Exception:
                self.store.event('error','Collector cycle failed; retained data and cursors. Check application diagnostics/tests.')
                self.store.meta('collector',{'status':'error','at':time.time()})
            self.stop.wait(self.config.cycle_seconds)
