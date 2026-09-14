import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit, parse_qs

from .chain import address
from .analytics import paper_open,paper_close
from .rules import cohort_stats,display_cohort,following_evidence
from .discovery import coverage
from .trade_values import recent_trades
from .positions import positions
from .research import experiment_summary,opportunities,wallet_research
from .focus import focus_health

STATIC=Path(__file__).with_name('static')

def summary(store,config):
    counts={t:store.one(f'SELECT COUNT(*) n FROM {t}')["n"] for t in ('wallets','tokens','trades','signals')}
    wallets=store.rows('''SELECT w.*,COUNT(DISTINCT t.mint) tokens FROM wallets w LEFT JOIN trades t ON t.wallet=w.address
        GROUP BY w.address ORDER BY CASE w.status WHEN 'active' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END,w.last_seen DESC LIMIT 200''')
    for w in wallets:
        w['cohorts']=cohort_stats(store,w['address'],time.time())
        w.update(display_cohort(w['cohorts']))
        w.update(following_evidence(store,w['address'],time.time(),w['cohorts']))
        speed=store.one('''SELECT COUNT(*) buys,
          SUM(EXISTS(SELECT 1 FROM trades sell WHERE sell.wallet=b.wallet AND sell.mint=b.mint
            AND sell.side='sell' AND sell.chain_time>b.chain_time AND sell.chain_time<=b.chain_time+900)) quick_exits
          FROM trades b WHERE b.wallet=? AND b.side='buy' AND b.chain_time>? AND b.chain_time<?''',
          (w['address'],time.time()-30*86400,time.time()-900))
        w['quick_exit_observations']=speed['quick_exits'] or 0
        w['mature_buy_observations']=speed['buys']

    signals=store.rows('''SELECT s.*,t.side,t.chain_time,(s.detected_at-t.chain_time) detection_age_seconds,t.venue,k.symbol,w.status wallet_status FROM signals s
      JOIN trades t ON t.id=s.trade_id JOIN tokens k ON k.mint=s.mint JOIN wallets w ON w.address=s.wallet
      ORDER BY s.id DESC LIMIT 100''')
    tokens=store.rows('''SELECT t.*,s.price,s.liquidity,CASE WHEN s.pair IS NULL THEN NULL ELSE s.volume END volume,s.market_cap_usd,s.observed_at,s.status market_status FROM tokens t
       LEFT JOIN snapshots s ON s.id=(SELECT id FROM snapshots WHERE mint=t.mint ORDER BY observed_at DESC LIMIT 1)
       ORDER BY t.last_seen DESC LIMIT 150''')
    positions=store.rows('SELECT * FROM paper ORDER BY id DESC LIMIT 200')
    discovery_funnel=store.one('''SELECT
      (SELECT COUNT(*) FROM wallets WHERE first_seen>?) added_24h,
      (SELECT COUNT(DISTINCT wallet) FROM admission_values) evaluated_wallets,
      (SELECT COUNT(*) FROM admission_values WHERE estimated_usd>=?) qualifying_purchases,
      (SELECT COUNT(DISTINCT wallet) FROM admission_pending a WHERE NOT EXISTS(SELECT 1 FROM wallets w WHERE w.address=a.wallet)) pending_wallets''',
      (time.time()-86400,config.min_purchase_usd))
    discovery_funnel['inspection_ages']=store.rows('''SELECT program,MAX(chain_time) latest_chain_time FROM discovery_queue WHERE status='inspected' GROUP BY program''')
    experiment=experiment_summary(store)
    experiment['focus']=focus_health(store,experiment['run']['id'],time.time()) if experiment['run'] else []
    return {'discovery_funnel':discovery_funnel,'experiment':experiment,'opportunities':opportunities(store,config,experiment),
            'quote_enabled':bool(config.jupiter_api_key),'research_health':store.meta('research_health'),
            'trades':recent_trades(store),'counts':counts,'wallets':wallets,'signals':signals,'tokens':tokens,'paper':positions,
            'exits':store.rows('SELECT * FROM paper_exits ORDER BY id DESC LIMIT 100'),
            'events':store.rows('SELECT * FROM events ORDER BY id DESC LIMIT 30'),
            'budgets':store.rows('SELECT bucket,SUM(credits) credits FROM budgets WHERE day LIKE ? GROUP BY bucket',(time.strftime('%Y-%m',time.gmtime())+'%',)),
            'collector':store.meta('collector'),'mode':store.meta('mode') or 'live',
            'live_enabled':config.live,'credit_limit':config.monthly_credits,
            'discovery':coverage(store),'admission_pending':store.one('SELECT COUNT(DISTINCT wallet) n FROM admission_pending a WHERE NOT EXISTS(SELECT 1 FROM wallets w WHERE w.address=a.wallet)')['n'],
            'min_purchase_usd':config.min_purchase_usd,
            'purchase_filter':store.one('SELECT SUM(estimated_usd IS NULL) unknown,SUM(estimated_usd<?) below FROM admission_values',(config.min_purchase_usd,)),
            'min_market_cap_usd':config.min_market_cap,'discovery_interval':config.discovery_interval,
            'rpc_route':store.meta('rpc_route'),'rpc_fallback_usage':store.meta('rpc_fallback_usage'),
            'as_of':time.time(),'model':'Each result names its detection-age cohort; cohorts are never pooled. Hypothetical $500 entries 15 minutes after detection, held 1h/6h/24h; 24h determines qualification. Costs include 1% plus liquidity impact per side. Not actual wallet P&L or executable quotes.'}

def make_server(store,config):
    class Handler(BaseHTTPRequestHandler):
        server_version='WalletObservatory'
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self,*args):
            pass  # No auth headers, API keys, or query strings in logs.

        def send(self,code,data,content_type='application/json'):
            body=json.dumps(data,allow_nan=False).encode() if content_type=='application/json' else data
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers(); self.wfile.write(body)

        def auth(self):
            if not config.password:
                return True
            raw=self.headers.get('Authorization','')
            try:
                value=base64.b64decode(raw.split(' ',1)[1],validate=True).decode()
            except (ValueError,IndexError,UnicodeError):
                value=''
            if not hmac.compare_digest(value.encode(),('research:'+config.password).encode()):
                time.sleep(.15)
                self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="Wallet Observatory", charset="UTF-8"')
                self.send_header('Content-Length','0'); self.end_headers()
                return False
            return True

        def do_GET(self):
            if not self.auth(): return
            parts=urlsplit(self.path); path=parts.path
            if path=='/api/summary': return self.send(200,summary(store,config))
            if path=='/api/wallet':
                wallet=parse_qs(parts.query).get('address',[''])[0]
                if not address(wallet): return self.send(400,{'error':'Invalid Solana address'})
                return self.send(200,{'wallet':store.one('SELECT * FROM wallets WHERE address=?',(wallet,)),
                  'cohorts':cohort_stats(store,wallet,time.time()),
                  **following_evidence(store,wallet,time.time()),
                  'trades':recent_trades(store,wallet),'positions':positions(store,wallet),'research':wallet_research(store,wallet),
                  'links':store.rows('SELECT * FROM links WHERE source=? OR target=? ORDER BY observed_at DESC LIMIT 100',(wallet,wallet)),
                  'assessments':store.rows('SELECT * FROM assessments WHERE wallet=? ORDER BY at DESC LIMIT 100',(wallet,)),
                  'outcomes':store.rows('SELECT o.*,s.mint FROM outcomes o JOIN signals s ON s.id=o.signal_id WHERE s.wallet=? ORDER BY s.id DESC LIMIT 300',(wallet,))})
            if path=='/api/export':
                return self.send(200,{'exported_at':time.time(),'summary':summary(store,config),
                  'note':'Dashboard export is capped. Use SQLite backup for complete history.'})
            files={'/':'index.html','/app.js':'app.js','/pagination.js':'pagination.js','/style.css':'style.css'}
            if path not in files: return self.send(404,{'error':'Not found'})
            types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
            file=STATIC/files[path]
            self.send(200,file.read_bytes(),types[file.suffix])

        def do_POST(self):
            if not self.auth(): return
            # Custom header + JSON blocks cross-origin form/fetch writes; no CORS is enabled.
            if self.headers.get('X-Observatory')!='1' or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self.send(403,{'error':'Same-origin JSON request required'})
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
                return self.send(403,{'error':'Origin mismatch'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384: raise ValueError('Invalid request size')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected JSON object')
                path=urlsplit(self.path).path
                if path=='/api/watch':
                    wallet=body.get('address','')
                    if not address(wallet): raise ValueError('Invalid Solana wallet address')
                    now=time.time()
                    store.execute('''INSERT INTO wallets(address,first_seen,last_seen) VALUES(?,?,?)
                       ON CONFLICT(address) DO UPDATE SET next_scan=0,status='candidate',reason='Manual reassessment requested' ''',(wallet,now,now))
                    return self.send(200,{'ok':True})
                if path=='/api/paper/open':
                    mint=body.get('mint','')
                    if not address(mint): raise ValueError('Invalid token address')
                    if not store.one('SELECT 1 FROM tokens WHERE mint=?',(mint,)): raise ValueError('Select a discovered token')
                    return self.send(200,{'id':paper_open(store,mint,float(body.get('usd',500)),str(body.get('notes','')),body.get('signal_id'))})
                if path=='/api/paper/close':
                    return self.send(200,paper_close(store,int(body['id']),float(body.get('percent',100)),str(body.get('notes',''))))
                if path=='/api/read':
                    store.execute('UPDATE signals SET read=1 WHERE id=?',(int(body['id']),))
                    return self.send(200,{'ok':True})
                return self.send(404,{'error':'Not found'})
            except (ValueError,KeyError,TypeError,OverflowError) as e:
                self.send(400,{'error':str(e)[:240]})
            except Exception:
                store.event('error','Dashboard action failed; no provider credentials logged')
                self.send(500,{'error':'Action failed; inspect system events'})

    server=ThreadingHTTPServer((config.host,config.port),Handler)
    server.daemon_threads=True
    return server
