"""Optional Jupiter V2 quote-only checks. No taker, signing or execution endpoint."""
import time,math
from urllib.parse import urlencode
from .chain import USDC
from .providers import ProviderError


def order(provider,config,input_mint,output_mint,amount):
    day=time.strftime('%Y-%m-%d',time.gmtime())
    with provider.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT requests FROM quote_budget WHERE day=?',(day,)).fetchone()
        if (row[0] if row else 0)>=config.quote_daily_cap:raise ProviderError('Quote daily cap reached')
        db.execute('INSERT INTO quote_budget VALUES(?,1) ON CONFLICT(day) DO UPDATE SET requests=requests+1',(day,))
    data=provider.request('https://api.jup.ag/swap/v2/order?'+urlencode({'inputMint':input_mint,'outputMint':output_mint,'amount':str(amount)}),headers={'x-api-key':config.jupiter_api_key})
    try:
        out=int(data.get('outAmount',0))
        if data.get('errorCode') or out<=0:raise ValueError()
        impact=float(data['priceImpactPct']) if data.get('priceImpactPct') is not None else None
        if impact is not None and not math.isfinite(impact):impact=None
        return out,impact,str(data.get('router','unknown'))[:40]
    except (ValueError,TypeError,AttributeError):raise ProviderError('Quote unavailable') from None


def check_routes(store,provider,config,mints,now=None):
    if not config.jupiter_api_key:return
    now=now or time.time()
    for mint in mints[:2]:
        latest=store.one('SELECT at FROM route_checks WHERE mint=? ORDER BY at DESC LIMIT 1',(mint,))
        if latest and latest['at']>now-300:continue
        status='quote_unavailable';amount=buy_impact=sell_impact=router=None
        try:
            raw,buy_impact,router=order(provider,config,USDC,mint,500_000_000)
            status='exit_quote_unavailable'
            out,sell_impact,_=order(provider,config,mint,USDC,raw)
            amount=out/1e6;status='quoted'
        except ProviderError:pass
        store.execute('INSERT INTO route_checks(mint,at,size_usdc,status,roundtrip_usdc,buy_impact,sell_impact,router) VALUES(?,?,?,?,?,?,?,?)',
          (mint,time.time(),500,status,amount,buy_impact,sell_impact,router))
