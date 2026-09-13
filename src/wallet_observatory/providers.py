import calendar
from datetime import datetime, timezone
import json
import math
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError

class ProviderError(Exception):
    pass

class RateLimited(ProviderError):
    pass

class BudgetExceeded(ProviderError):
    pass

class Providers:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.lock = threading.Lock()
        self.last_request = 0

    def reserve(self, bucket, cost):
        if cost <= 0:
            raise ValueError('Credit cost must be positive')
        today = datetime.now(timezone.utc)
        day = today.strftime('%Y-%m-%d'); month = day[:7]
        fraction = {'tracking':.5,'discovery':.3,'revisit':.2}[bucket]
        month_cap = int(self.config.monthly_credits*fraction)
        daily_cap = month_cap//calendar.monthrange(today.year,today.month)[1]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            monthly = db.execute('SELECT COALESCE(SUM(credits),0) FROM budgets WHERE day LIKE ? AND bucket=?', (month+'%',bucket)).fetchone()[0]
            daily = db.execute('SELECT credits FROM budgets WHERE day=? AND bucket=?',(day,bucket)).fetchone()
            if monthly+cost>month_cap or (daily[0] if daily else 0)+cost>daily_cap:
                raise BudgetExceeded(f'{bucket} credit allowance reached; resumes on next UTC day/month')
            db.execute('INSERT INTO budgets VALUES(?,?,?) ON CONFLICT(day,bucket) DO UPDATE SET credits=credits+excluded.credits',(day,bucket,cost))

    def request(self,url,payload=None,headers=None):
        # Single process-wide provider lock bounds request rate, including browser paper actions.
        with self.lock:
            time.sleep(max(0, .55-(time.monotonic()-self.last_request)))
            self.last_request=time.monotonic()
            req=Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                        headers={'User-Agent':'WalletObservatory/0.1','Accept':'application/json',
                                 'Content-Type':'application/json', **(headers or {})})
            try:
                with urlopen(req,timeout=20) as response:
                    return json.loads(response.read(12_000_000))
            except HTTPError as e:
                if e.code==429:
                    raise RateLimited('Provider rate or quota limit reached') from None
                raise ProviderError(f'Provider HTTP {e.code}; no immediate retry') from None
            except (URLError, TimeoutError, ValueError, OSError):
                # URLs can include API keys; never log exception strings.
                raise ProviderError('Provider unavailable or invalid response') from None

    def rpc(self,method,params,bucket):
        if not self.config.rpc_url:
            raise ProviderError('Configure HELIUS_API_KEY or OBS_RPC_URL to collect live data')
        if method not in {'getSignaturesForAddress','getTransaction'}:
            raise ValueError('RPC method is not in the read-only allowlist')
        payload={'jsonrpc':'2.0','id':1,'method':method,'params':params}
        helius=(urlsplit(self.config.rpc_url).hostname or '').endswith('.helius-rpc.com')
        state=self.store.meta('rpc_primary_cooldown') or {}
        try:
            if helius and state.get('until',0)>time.time():
                raise RateLimited('Primary provider cooldown')
            self.reserve(bucket,self.config.rpc_credit_cost)
            data=self.request(self.config.rpc_url,payload)
            if isinstance(data.get('error'),dict) and data['error'].get('code')==429:
                raise RateLimited('Primary RPC rate or quota limit reached')
        except (BudgetExceeded,RateLimited) as e:
            if not helius: raise
            if isinstance(e,RateLimited) and state.get('until',0)<=time.time():
                self.store.meta('rpc_primary_cooldown',{'until':time.time()+3600})
            return self.fallback(payload,bucket)
        if data.get('error'):
            raise ProviderError('RPC returned an error; check provider configuration and quota')
        self.route('primary')
        return data.get('result')

    def route(self,name):
        previous=self.store.meta('rpc_route') or {}
        if previous.get('provider')!=name:
            self.store.event('provider','RPC switched to '+name)
        self.store.meta('rpc_route',{'provider':name,'at':time.time()})

    def fallback(self,payload,bucket):
        state=self.store.meta('rpc_fallback_usage') or {}
        now=time.time(); day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if state.get('until',0)>now:
            raise ProviderError('PublicNode cooling down after an error')
        count=state.get('requests',0) if state.get('day')==day else 0
        if count>=10000:
            raise BudgetExceeded('PublicNode daily safety cap reached; resumes next UTC day')
        # Independent accounting: public requests do not consume Helius credits.
        self.store.meta('rpc_fallback_usage',{'day':day,'requests':count+1})
        self.route('PublicNode fallback')
        try:
            # request() also serializes traffic; public requests are at most one/second.
            time.sleep(1)
            data=self.request('https://solana-rpc.publicnode.com',payload)
            if data.get('error'):
                raise ProviderError('PublicNode RPC rejected request')
        except ProviderError:
            self.store.meta('rpc_fallback_usage',{'day':day,'requests':count+1,'until':now+300})
            raise ProviderError('PublicNode request failed; paused for five minutes') from None
        return data.get('result')

    def signatures(self,wallet,bucket,before=None,limit=None):
        args={'limit':limit or self.config.page_limit,'commitment':'finalized'}
        if before:
            args['before']=before
        return self.rpc('getSignaturesForAddress',[wallet,args],bucket) or []

    def transaction(self,sig,bucket):
        return self.rpc('getTransaction',[sig,{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':0}],bucket)

    def market(self,mints):
        if not mints:
            return []
        data=self.request('https://api.dexscreener.com/tokens/v1/solana/'+','.join(mints))
        if not isinstance(data,list):
            raise ProviderError('Unexpected market response')
        result=[]
        for mint in mints:
            pairs=[p for p in data if p.get('chainId')=='solana' and (p.get('baseToken') or {}).get('address')==mint]
            pairs.sort(key=lambda p:float((p.get('liquidity') or {}).get('usd') or 0),reverse=True)
            p=pairs[0] if pairs else {}
            market_cap=float(p['marketCap']) if p.get('marketCap') is not None else None
            if market_cap is not None and (not math.isfinite(market_cap) or market_cap<0): market_cap=None
            result.append({'mint':mint,'price':float(p.get('priceUsd') or 0) or None,
                           'liquidity':float((p.get('liquidity') or {}).get('usd') or 0) or None,
                           'volume':float(p['volume']['h24']) if (p.get('volume') or {}).get('h24') is not None else None,
                           'market_cap_usd':market_cap,
                           'pair':p.get('pairAddress'),'symbol':(p.get('baseToken') or {}).get('symbol','')[:40],
                           'status':'observed' if p.get('priceUsd') else 'unpriced'})
        return result
