"""Prospective fixed-horizon selection metrics, separate from manual paper trades."""
import math
from .rules import cohort_stats,display_cohort
import time

DELAYS=(300,900,3600)
HORIZONS=(3600,21600,86400,604800,2419200)
TOLERANCE=600

def entry_fill(price,liquidity,usd):
    if not all(isinstance(x,(float,int)) and math.isfinite(x) and x>0 for x in (price,liquidity,usd)):
        raise ValueError('A fresh positive price and liquidity estimate are required')
    if usd>liquidity*.01:
        raise ValueError('Position exceeds 1% of reported liquidity; model refuses this fill')
    # Explicit research approximation, not a route quote or execution guarantee.
    return usd/(price*(1.01+2*usd/liquidity))

def exit_fill(price,liquidity,quantity):
    notional=price*quantity
    entry_fill(price,liquidity,notional)
    return notional*max(0,1-.01-2*notional/liquidity)

def evaluate(store,now=None):
    now=now or time.time()
    signals=store.rows('SELECT * FROM signals WHERE eligible=1 AND detected_at>?',(now-36*86400,))
    for s in signals:
        for delay in DELAYS:
            et=s['detected_at']+delay
            entry=store.one("SELECT * FROM snapshots WHERE mint=? AND observed_at>=? AND observed_at<=? AND status='observed' ORDER BY observed_at LIMIT 1",(s['mint'],et,et+TOLERANCE))
            for horizon in HORIZONS:
                existing=store.one('SELECT status FROM outcomes WHERE signal_id=? AND delay=? AND horizon=?',(s['id'],delay,horizon))
                if existing and existing['status']!='pending':
                    continue
                xt=et+horizon
                if now<xt+TOLERANCE:
                    continue
                end=store.one("SELECT * FROM snapshots WHERE mint=? AND observed_at>=? AND observed_at<=? AND status='observed' ORDER BY observed_at LIMIT 1",(s['mint'],xt,xt+TOLERANCE))
                ret=None; status='missing_data'
                if entry and end:
                    try:
                        quantity=entry_fill(entry['price'],entry['liquidity'],500)
                        ret=(exit_fill(end['price'],end['liquidity'],quantity)/500-1)*100
                        status='estimated'
                    except (ValueError,TypeError):
                        status='insufficient_liquidity'
                store.execute('INSERT OR REPLACE INTO outcomes VALUES(?,?,?,?,?,?,?,?,?)',
                    (s['id'],delay,horizon,entry['observed_at'] if entry else None,end['observed_at'] if end else None,
                     entry['price'] if entry else None,end['price'] if end else None,ret,status))

    for w in store.rows('SELECT * FROM wallets'):
        stats=cohort_stats(store,w['address'],now)
        chosen=display_cohort(stats)
        score=chosen['median_return']
        values_count=chosen['priced_samples']
        previous=w['status']
        # Inactivity takes precedence; old wins must not consume fast polling forever.
        if w['last_seen']<now-7*86400:
            status='dormant'; reason='No recent observed activity; periodic reassessment remains enabled'
        elif any(s['qualifies'] for s in stats):
            status='active'; reason=f"Qualifies in {chosen['cohort']} detections: ≥8 tokens, positive median, ≥60% wins, ≥80% coverage"
        elif any(s['priced_samples']>=8 and (s['coverage'] or 0)>=80 for s in stats if s['cohort']!='legacy'):
            status='cooldown'; reason='Mature observed samples currently below promotion thresholds'
        else:
            status='candidate'; reason='Insufficient prospective evidence; not a negative verdict'
        store.execute('UPDATE wallets SET status=?,reason=? WHERE address=?',(status,reason,w['address']))
        if status!=previous:
            store.execute('INSERT INTO assessments(wallet,at,status,reason,samples,median_return) VALUES(?,?,?,?,?,?)',(w['address'],now,status,reason,values_count,score))
            store.event('assessment',f'{w["address"]}: {previous} → {status}')
            if status=='active' or (status=='candidate' and previous in ('cooldown','dormant')):
                store.execute('UPDATE wallets SET next_scan=MIN(next_scan,?) WHERE address=?',(now,w['address']))

def paper_open(store,mint,usd,notes='',signal_id=None,now=None):
    now=now or time.time()
    if not isinstance(usd,(float,int)) or not math.isfinite(usd) or usd<500 or usd>1e9:
        raise ValueError('Paper entries must be between $500 and $1 billion')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        snap=db.execute("SELECT * FROM snapshots WHERE mint=? ORDER BY observed_at DESC LIMIT 1",(mint,)).fetchone()
        if not snap or snap['status']!='observed' or not 0<=now-snap['observed_at']<=600:
            raise ValueError('No market observation within the last 10 minutes; entry not recorded')
        qty=entry_fill(snap['price'],snap['liquidity'],usd)
        if signal_id is not None and not db.execute('SELECT 1 FROM signals WHERE id=? AND mint=?',(signal_id,mint)).fetchone():
            raise ValueError('Signal does not match token')
        return db.execute('INSERT INTO paper(mint,opened_at,entry_price,invested,quantity,remaining,notes,signal_id,model) VALUES(?,?,?,?,?,?,?,?,?)',
                          (mint,now,usd/qty,usd,qty,qty,notes[:4000],signal_id,'estimate-v1: 1% cost + 2×notional/liquidity impact per side')).lastrowid

def paper_close(store,position_id,percent,notes='',now=None):
    now=now or time.time()
    if not isinstance(percent,(float,int)) or not math.isfinite(percent) or not 0<percent<=100:
        raise ValueError('Exit percent must be greater than 0 and at most 100')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        p=db.execute('SELECT * FROM paper WHERE id=?',(position_id,)).fetchone()
        if not p or p['remaining']<=0:
            raise ValueError('No open position')
        snap=db.execute('SELECT * FROM snapshots WHERE mint=? ORDER BY observed_at DESC LIMIT 1',(p['mint'],)).fetchone()
        if not snap or snap['status']!='observed' or not 0<=now-snap['observed_at']<=600:
            raise ValueError('No fresh market observation; exit not recorded')
        qty=p['remaining']*percent/100
        proceeds=exit_fill(snap['price'],snap['liquidity'],qty)
        pnl=proceeds-qty*p['entry_price']
        db.execute('INSERT INTO paper_exits(position_id,closed_at,quantity,price,proceeds,pnl,notes) VALUES(?,?,?,?,?,?,?)',
                   (position_id,now,qty,proceeds/qty,proceeds,pnl,notes[:4000]))
        db.execute('UPDATE paper SET remaining=?,realized=realized+? WHERE id=?',(0 if percent==100 else p['remaining']-qty,pnl,position_id))
        return {'proceeds':proceeds,'pnl':pnl}
