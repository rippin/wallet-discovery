"""Clearly synthetic fixtures; never mixed with live observations."""
import time
from .analytics import paper_open

def key(n):
    from .chain import ALPHABET
    raw=bytes([n])*32; number=int.from_bytes(raw,'big'); result=''
    while number:
        number,r=divmod(number,58); result=ALPHABET[r]+result
    return result

def seed(store):
    if store.one('SELECT 1 FROM wallets LIMIT 1'): return
    now=time.time()
    names=['ORBIT','EMBER','MOSS','ECHO','DRIFT','NOVA']
    for i,name in enumerate(names):
        mint=key(i+30)
        store.execute('INSERT INTO tokens(mint,symbol,source,platform,first_seen,last_seen) VALUES(?,?,?,?,?,?)',
                      (mint,name,'pumpfun' if i%2==0 else 'launchlab',None,now-86400*3,now-i*70))
        store.execute('INSERT INTO snapshots(mint,observed_at,price,liquidity,volume,pair,status) VALUES(?,?,?,?,?,?,?)',
                      (mint,now,.002*(i+1),250000+i*50000,150000+i*24000,None,'observed'))
    for i,status in enumerate(['active','active','candidate','candidate','cooldown','dormant']):
        wallet=key(i+1)
        store.execute('INSERT INTO wallets(address,first_seen,last_seen,status,last_scan,reason) VALUES(?,?,?,?,?,?)',
                      (wallet,now-86400*20,now-i*600,status,now-60,'Synthetic example — not a real wallet assessment'))
        for j in range(6):
            mint=key(j+30); at=now-86400*2-j*800
            tid=store.execute('INSERT INTO trades(signature,wallet,mint,side,quantity,quote_mint,quote_quantity,chain_time,observed_at,venue,quality) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (f'demo-{i}-{j}',wallet,mint,'buy',50000,None,2,at-30,at,'pumpfun' if j%2==0 else 'launchlab','synthetic'))
            sid=store.execute('INSERT INTO signals(trade_id,wallet,mint,detected_at,eligible) VALUES(?,?,?,?,1)',(tid,wallet,mint,at))
            ret=([28,16,8,-12,-24,-40][i]+j*3)
            store.execute('INSERT INTO outcomes VALUES(?,?,?,?,?,?,?,?,?)',(sid,900,86400,at+900,at+87300,.002,.002*(1+ret/100),ret,'estimated'))
    paper_open(store,key(30),500,'Synthetic example position')
    store.meta('collector',{'status':'demo','at':now})
    store.event('demo','Synthetic preview. No real wallets, market data, or performance claims.')
