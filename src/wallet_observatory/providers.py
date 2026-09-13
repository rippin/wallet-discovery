import calendar
from datetime import datetime, timezone
import json
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class ProviderError(Exception):
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
                raise ProviderError(f'Provider HTTP {e.code}; no immediate retry') from None
            except (URLError, TimeoutError, ValueError, OSError):
                # URLs can include API keys; never log exception strings.
                raise ProviderError('Provider unavailable or invalid response') from None

    def rpc(self,method,params,bucket):
        if not self.config.rpc_url:
            raise ProviderError('Configure HELIUS_API_KEY or OBS_RPC_URL to collect live data')
        if method not in {'getSignaturesForAddress','getTransaction'}:
            raise ValueError('RPC method is not in the read-only allowlist')
        self.reserve(bucket,self.config.rpc_credit_cost)
        data=self.request(self.config.rpc_url,{'jsonrpc':'2.0','id':1,'method':method,'params':params})
        if data.get('error'):
            raise ProviderError('RPC returned an error; check provider configuration and quota')
        return data.get('result')

    def signatures(self,wallet,bucket,before=None):
        args={'limit':self.config.page_limit,'commitment':'finalized'}
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
            result.append({'mint':mint,'price':float(p.get('priceUsd') or 0) or None,
                           'liquidity':float((p.get('liquidity') or {}).get('usd') or 0) or None,
                           'volume':float((p.get('volume') or {}).get('h24') or 0),
                           'pair':p.get('pairAddress'),'symbol':(p.get('baseToken') or {}).get('symbol','')[:40],
                           'status':'observed' if p.get('priceUsd') else 'unpriced'})
        return result
