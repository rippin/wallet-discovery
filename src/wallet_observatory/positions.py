"""FIFO matching of observed trades; never an assertion of full account holdings."""
from collections import defaultdict, deque
import math
import json
from decimal import Decimal


def record_flows(db,signature,tx,wallet):
    delta=defaultdict(Decimal);before=defaultdict(Decimal)
    for name,sign in (('preTokenBalances',-1),('postTokenBalances',1)):
        for b in (tx.get('meta') or {}).get(name) or []:
            if b.get('owner')!=wallet:continue
            amount=b['uiTokenAmount']
            value=Decimal(amount['amount'])/(10**int(amount['decimals']))
            delta[b['mint']]+=sign*value
            if sign==-1:before[b['mint']]+=value
    for mint,value in delta.items():
        db.execute('''INSERT INTO token_openings VALUES(?,?,?,?) ON CONFLICT(wallet,mint) DO UPDATE
          SET chain_time=excluded.chain_time,quantity=excluded.quantity WHERE excluded.chain_time<token_openings.chain_time''',
          (wallet,mint,tx['blockTime'],float(before[mint])))
        if value:
            db.execute('INSERT OR IGNORE INTO token_flows VALUES(?,?,?,?,?)',(signature,wallet,mint,tx['blockTime'],float(value)))


def backfill_flows(store,limit=100):
    cursor=store.meta('flow_backfill_cursor') or 0
    rows=store.rows('SELECT rowid,signature,raw FROM transactions WHERE rowid>? ORDER BY rowid LIMIT ?',(cursor,limit))
    wallets={w['address'] for w in store.rows('SELECT address FROM wallets')}
    with store.connect() as db:
        for row in rows:
            tx=json.loads(row['raw'])
            if tx.get('blockTime') is not None:
                owners={b.get('owner') for side in ('preTokenBalances','postTokenBalances') for b in (tx.get('meta') or {}).get(side) or []}
                for wallet in wallets & owners:record_flows(db,row['signature'],tx,wallet)
    if rows:store.meta('flow_backfill_cursor',rows[-1]['rowid'])


def positions(store,wallet):
    trades=store.rows('''SELECT t.*,v.usd_amount,v.price_at,k.symbol FROM trades t
      LEFT JOIN trade_values v ON v.trade_id=t.id LEFT JOIN tokens k ON k.mint=t.mint
      WHERE t.wallet=? ORDER BY t.chain_time,t.id''',(wallet,))
    groups=defaultdict(list)
    for t in trades:groups[t['mint']].append(t)
    # Non-trade token movements preserve unknown acquisitions and remove inventory
    # without inventing sale proceeds. Unsupported swaps also remain unknown flows.
    for flow in store.rows('''SELECT f.* FROM token_flows f WHERE wallet=? AND NOT EXISTS
      (SELECT 1 FROM trades t WHERE t.signature=f.signature AND t.wallet=f.wallet AND t.mint=f.mint)''',(wallet,)):
        if flow['mint'] in groups:
            groups[flow['mint']].append({'side':'flow','quantity':abs(flow['delta']),'delta':flow['delta'],
              'chain_time':flow['chain_time'],'usd_amount':None,'price_at':None,'quality':'unknown flow','symbol':None,'id':0})
    for opening in store.rows('SELECT * FROM token_openings WHERE wallet=? AND quantity>0',(wallet,)):
        if opening['mint'] in groups:
            groups[opening['mint']].append({'side':'flow','quantity':opening['quantity'],'delta':opening['quantity'],
              'chain_time':opening['chain_time']-.001,'usd_amount':None,'price_at':None,'quality':'pre-existing inventory','symbol':None,'id':0})
    result=[]
    for mint,rows in groups.items():
        rows.sort(key=lambda t:(t['chain_time'],t['id']))
        times=defaultdict(int)
        for t in rows:times[t['chain_time']]+=1
        lots=deque();buy_qty=sell_qty=buy_usd=sell_usd=0.;priced_buy_qty=priced_sell_qty=0.
        matched_qty=matched_proceeds=matched_cost=unmatched=0.;priced_buys=priced_sells=0
        uncertain=False;last_action='unknown';last_time=None
        for t in rows:
            qty=t['quantity']
            if not math.isfinite(qty) or qty<=0:continue
            # A quote sampled much later cannot supply historical P&L/cost basis.
            usable=times[t['chain_time']]==1 and t['usd_amount'] is not None and abs(t['price_at']-t['chain_time'])<=600 and 'instruction-local' not in t['quality']
            value=t['usd_amount'] if usable else None
            before=sum(l[0] for l in lots)
            if last_time==t['chain_time']:
                # Equal block timestamps do not establish intra-block ordering.
                lots=deque([[before,None]]) if before else deque();uncertain=True
            if t['side']=='flow':
                uncertain=True
                if t['delta']>0:lots.append([qty,None]);last_action='unknown token inflow'
                else:
                    # A transfer can remove any lot: invalidate remaining basis.
                    remaining=max(0,before-qty);lots=deque([[remaining,None]]) if remaining else deque()
                    last_action='unknown token outflow'
                last_time=t['chain_time'];continue
            if t['side']=='buy':
                buy_qty+=qty
                if value is not None:buy_usd+=value;priced_buy_qty+=qty;priced_buys+=1
                lots.append([qty,value/qty if value is not None else None])
                last_action='adding' if before>1e-9 else 'new observed position'
            else:
                sell_qty+=qty
                if value is not None:sell_usd+=value;priced_sell_qty+=qty;priced_sells+=1
                left=qty
                while left>1e-9 and lots:
                    lot=lots[0];take=min(left,lot[0]);left-=take;lot[0]-=take
                    if lot[1] is not None and value is not None:
                        matched_qty+=take;matched_cost+=take*lot[1];matched_proceeds+=value*take/qty
                    else:unmatched+=take
                    if lot[0]<=1e-9:lots.popleft()
                unmatched+=left
                if left>1e-9:uncertain=True
                last_action='observed exit' if not lots else 'partial exit'
            last_time=t['chain_time']
        remaining=sum(l[0] for l in lots)
        snap=store.one('SELECT price,observed_at FROM snapshots WHERE mint=? ORDER BY observed_at DESC,id DESC LIMIT 1',(mint,))
        result.append({'mint':mint,'symbol':next((t['symbol'] for t in rows if t['symbol']),None),'bought_quantity':buy_qty,'sold_quantity':sell_qty,
          'buy_usd':buy_usd if priced_buys else None,'sell_usd':sell_usd if priced_sells else None,
          'priced_buys':priced_buys,'buys':sum(t['side']=='buy' for t in rows),'priced_sells':priced_sells,'sells':sum(t['side']=='sell' for t in rows),
          'average_entry':buy_usd/priced_buy_qty if priced_buy_qty else None,
          'average_exit':sell_usd/priced_sell_qty if priced_sell_qty else None,
          'observed_remaining':remaining,'matched_realized_usd':matched_proceeds-matched_cost if matched_qty else None,
          'matched_sold_quantity':matched_qty,'unmatched_sold_quantity':unmatched,
          'cost_coverage':100*matched_qty/sell_qty if sell_qty else None,
          'action':last_action,'last_trade_at':rows[-1]['chain_time'],'history_gap':uncertain,
          'balance_status':'Unverified trade-derived inventory; transfers and earlier holdings may be missing',
          'mark_price':snap['price'] if snap else None,'mark_at':snap['observed_at'] if snap else None})
    return sorted(result,key=lambda p:p['last_trade_at'],reverse=True)
