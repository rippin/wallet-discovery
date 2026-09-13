import json
import math
import threading
import time

from .chain import PUMP, LAB, parse
from .providers import Providers, ProviderError, BudgetExceeded
from .analytics import evaluate
from .rules import classify,cohort_stats
from .discovery import Discovery

class Collector:
    def __init__(self,store,config,providers=None):
        self.store,self.config=store,config
        self.providers=providers or Providers(store,config)
        self.stop=threading.Event()
        self.next_discovery=None

    def ingest(self,signature,tx,bucket,watch=None):
        if not tx or tx.get('blockTime') is None:
            self.store.event('coverage','Transaction unavailable; historical coverage incomplete')
            return False
        now=time.time(); chain_time=tx['blockTime']
        trades,links,status=parse(tx, {r['mint'] for r in self.store.rows('SELECT mint FROM tokens')})
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?)',
                       (signature,chain_time,now,json.dumps(tx,separators=(',',':')),status))
            for t in trades:
                discovery=watch is None
                if discovery and not(t['venue'] in ('pumpfun','launchlab') and t['side']=='buy'):
                    continue
                if watch and t['wallet']!=watch:
                    continue
                previous=db.execute('SELECT first_seen FROM wallets WHERE address=?',(t['wallet'],)).fetchone()
                known_at=previous['first_seen'] if previous else None
                db.execute("INSERT OR IGNORE INTO tokens(mint,source,platform,first_seen,last_seen) VALUES(?,?,?,?,?)",
                           (t['mint'],t['venue'],t['platform'],now,chain_time))
                if discovery and previous is None and self.config.min_purchase_usd>0:
                    db.execute('INSERT OR IGNORE INTO admission_values(signature,wallet,mint,quote_mint,quote_quantity) VALUES(?,?,?,?,?)',
                               (signature,t['wallet'],t['mint'],t['quote_mint'],t['quote_quantity']))
                    value=db.execute('SELECT estimated_usd FROM admission_values WHERE signature=? AND wallet=? AND mint=?',
                                     (signature,t['wallet'],t['mint'])).fetchone()['estimated_usd']
                    if value is None:
                        rate=db.execute('SELECT price,observed_at FROM quote_prices WHERE mint=?',(t['quote_mint'],)).fetchone()
                        if rate and rate['observed_at']>=now-600 and rate['price'] is not None and math.isfinite(rate['price']) and rate['price']>0:
                            estimate=t['quote_quantity']*rate['price']
                            if math.isfinite(estimate) and estimate>=0:
                                value=estimate
                                db.execute('UPDATE admission_values SET estimated_usd=?,valued_at=? WHERE signature=? AND wallet=? AND mint=?',
                                           (value,now,signature,t['wallet'],t['mint']))
                    if value is None or value<self.config.min_purchase_usd:
                        db.execute('INSERT OR IGNORE INTO admission_pending VALUES(?,?,?,?)',(signature,t['wallet'],t['mint'],now))
                        continue
                if discovery and previous is None and self.config.min_market_cap>0:
                    valuation=db.execute('SELECT market_cap_usd,observed_at FROM snapshots WHERE mint=? ORDER BY observed_at DESC,id DESC LIMIT 1',(t['mint'],)).fetchone()
                    if not valuation or valuation['observed_at']<now-600 or valuation['market_cap_usd'] is None or valuation['market_cap_usd']<=self.config.min_market_cap:
                        db.execute('INSERT OR IGNORE INTO admission_pending VALUES(?,?,?,?)',(signature,t['wallet'],t['mint'],now))
                        continue
                db.execute('DELETE FROM admission_pending WHERE signature=? AND wallet=? AND mint=?',(signature,t['wallet'],t['mint']))
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
                    observation_class,eligible=classify(known_at,chain_time,now)
                    db.execute('INSERT OR IGNORE INTO signals(trade_id,wallet,mint,detected_at,eligible,observation_class,rule_version) VALUES(?,?,?,?,?,?,2)',
                               (cur.lastrowid,t['wallet'],t['mint'],now,int(eligible),observation_class))
            if watch:
                for edge in links:
                    if watch in (edge['source'],edge['target']):
                        db.execute('INSERT OR IGNORE INTO links(source,target,signature,observed_at,kind,amount) VALUES(?,?,?,?,?,?)',
                                   (edge['source'],edge['target'],signature,now,edge['kind'],edge['amount']))
        return True

    def load_tx(self,sig,bucket):
        if bucket!='discovery': self.discovery_due()
        cached=self.store.one('SELECT raw FROM transactions WHERE signature=?',(sig,))
        return json.loads(cached['raw']) if cached else self.providers.transaction(sig,bucket)

    def discovery_due(self):
        if self.next_discovery is not None and time.monotonic()>=self.next_discovery:
            self.discover()
            self.next_discovery=time.monotonic()+self.config.discovery_interval

    def discover(self):
        Discovery(self).tick()

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
        if wallet['status']=='candidate' and any(s['promising'] for s in cohort_stats(self.store,wallet['address'],now)):
            interval=900
        self.store.execute('UPDATE wallets SET cursor=COALESCE(?,cursor),last_scan=?,next_scan=? WHERE address=?',
                           (newest,now,now+interval,wallet['address']))

    def markets(self):
        # Price quote currencies in a separate cache, not the tracked token universe.
        quotes=self.store.rows('''SELECT a.quote_mint FROM admission_values a LEFT JOIN quote_prices q ON q.mint=a.quote_mint
          WHERE a.estimated_usd IS NULL AND a.quote_mint IS NOT NULL
          GROUP BY a.quote_mint ORDER BY COALESCE(MAX(q.observed_at),0) LIMIT 30''')
        if quotes:
            for quote in self.providers.market([r['quote_mint'] for r in quotes]):
                self.store.execute('INSERT OR REPLACE INTO quote_prices VALUES(?,?,?)',(quote['mint'],quote['price'],time.time()))
        # Open positions first, then tokens with pending 28-day outcomes; oldest sample first.
        rows=self.store.rows('''SELECT t.mint,MAX(s.observed_at) last_sample,
          EXISTS(SELECT 1 FROM paper p WHERE p.mint=t.mint AND p.remaining>0) held
          FROM tokens t LEFT JOIN snapshots s ON s.mint=t.mint
          WHERE t.last_seen>? OR EXISTS(SELECT 1 FROM paper p WHERE p.mint=t.mint AND p.remaining>0)
          GROUP BY t.mint ORDER BY held DESC,COALESCE(last_sample,0) ASC LIMIT ?''',(time.time()-35*86400,self.config.market_cap))
        for offset in range(0,len(rows),30):
            for s in self.providers.market([r['mint'] for r in rows[offset:offset+30]]):
                with self.store.connect() as db:
                    db.execute('INSERT INTO snapshots(mint,observed_at,price,liquidity,volume,pair,status,market_cap_usd) VALUES(?,?,?,?,?,?,?,?)',
                               (s['mint'],time.time(),s['price'],s['liquidity'],s['volume'],s['pair'],s['status'],s.get('market_cap_usd')))
                    if s['symbol']:
                        db.execute('UPDATE tokens SET symbol=? WHERE mint=?',(s['symbol'],s['mint']))

        # Admit deferred buyers only once market cap is observed above the threshold.
        # Detection/first-seen time is now, never backdated to the original trade.
        query='''SELECT DISTINCT a.signature FROM admission_pending a
          LEFT JOIN admission_values v ON v.signature=a.signature AND v.wallet=a.wallet AND v.mint=a.mint
          WHERE (?=0 OR v.estimated_usd IS NULL OR v.estimated_usd>=?) AND a.signature>?
          ORDER BY a.signature LIMIT 100'''
        cursor=self.store.meta('admission_recheck_cursor') or ''
        pending=self.store.rows(query,(self.config.min_purchase_usd,self.config.min_purchase_usd,cursor))
        if not pending and cursor:
            pending=self.store.rows(query,(self.config.min_purchase_usd,self.config.min_purchase_usd,''))
        for item in pending:
            self.ingest(item['signature'],self.load_tx(item['signature'],'discovery'),'discovery')
            self.store.meta('admission_recheck_cursor',item['signature'])

    def cycle(self,include_discovery=True):
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
        for action in ((self.discover,self.markets) if include_discovery else (self.markets,)):
            try:
                action()
            except ProviderError as e:
                self.store.event('provider',str(e))
        evaluate(self.store)
        self.store.meta('collector',{'status':'waiting','at':time.time()})

    def run(self):
        next_cycle=0
        self.next_discovery=0
        while not self.stop.is_set():
            now=time.monotonic()
            try:
                self.discovery_due()
                if now>=next_cycle:
                    self.cycle(include_discovery=False)
                    next_cycle=time.monotonic()+self.config.cycle_seconds
            except Exception:
                self.store.event('error','Collector cycle failed; retained data and cursors. Check application diagnostics/tests.')
                self.store.meta('collector',{'status':'error','at':time.time()})
                self.next_discovery=time.monotonic()+self.config.discovery_interval
                next_cycle=time.monotonic()+self.config.cycle_seconds
            self.stop.wait(max(1,min(next_cycle,self.next_discovery)-time.monotonic()))
