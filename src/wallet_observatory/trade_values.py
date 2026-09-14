"""Frozen quote conversions, explicitly separate from historical execution prices."""
import math
import time
from .chain import WSOL, USDC, USDT


def value_trades(store):
    now=time.time()
    with store.connect() as db:
        rows=db.execute('''SELECT t.id,t.quote_quantity,q.price,q.observed_at
          FROM trades t JOIN quote_prices q ON q.mint=t.quote_mint
          LEFT JOIN trade_values v ON v.trade_id=t.id
          WHERE v.trade_id IS NULL AND q.observed_at>=?''',(now-600,)).fetchall()
        for row in rows:
            amount=row['quote_quantity'];price=row['price']
            if amount is None or price is None:continue
            value=amount*price
            if not math.isfinite(value) or amount<0 or price<=0:continue
            db.execute('INSERT OR IGNORE INTO trade_values VALUES(?,?,?)',(row['id'],value,row['observed_at']))


def recent_trades(store,wallet=None):
    rows=store.rows('''SELECT t.*,k.symbol,v.usd_amount,v.price_at
      FROM trades t LEFT JOIN tokens k ON k.mint=t.mint
      LEFT JOIN trade_values v ON v.trade_id=t.id
      '''+('WHERE t.wallet=? ' if wallet else '')+'ORDER BY t.chain_time DESC,t.id DESC LIMIT 200',
      (wallet,) if wallet else ())
    for row in rows:
        row['quote_symbol']={WSOL:'SOL',USDC:'USDC',USDT:'USDT'}.get(row['quote_mint'],row['quote_mint'])
        row['usd_basis']='unavailable' if row['usd_amount'] is None else ('near trade time' if abs(row['price_at']-row['chain_time'])<=600 else 'later price conversion')
    return rows
