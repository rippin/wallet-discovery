"""Frozen forward experiments; sampled controls, never retrospective wallet selection."""
import json,math,time
from statistics import mean,median
from .rules import cohort_stats,display_cohort
from .analytics import entry_fill,exit_fill

DELAYS=(60,300,900,3600)
HORIZONS=(3600,21600,86400)
TOLERANCE=120
RULES={'version':1,'days':7,'size_usd':500,'delays':DELAYS,'horizons':HORIZONS,
       'tolerance_seconds':TOLERANCE,'selection':'qualifying then promising 24h cohort; recent unproven candidates fill remaining slots',
       'controls':'same sampled tracked universe; different token and wallet; within 6h, factor 2 cap/liquidity, same observed-age bucket',
       'costs':'liquidity model: 1% plus impact per side; route checks separate',
       'token_age':'time since first observed, not launch time'}


def ensure_run(store,config,now):
    run=store.one('SELECT * FROM research_runs ORDER BY id DESC LIMIT 1')
    if run and run['ends_at']>now:return run
    ranked=[]
    for w in store.rows("SELECT * FROM wallets WHERE status IN ('active','candidate') ORDER BY last_seen DESC LIMIT 100"):
        c=display_cohort(cohort_stats(store,w['address'],now))
        rank=2 if c['qualifies'] else 1 if c['promising'] else 0
        ranked.append((rank,c['priced_samples'] if rank else 0,w['last_seen'],w['address'],c))
    ranked.sort(key=lambda x:x[:4],reverse=True)
    with store.connect() as db:
        rid=db.execute('INSERT INTO research_runs(started_at,ends_at,rules) VALUES(?,?,?)',
          (now,now+7*86400,json.dumps({**RULES,'focus_wallets':config.focus_wallets}))).lastrowid
        for rank,_,_,wallet,c in ranked[:config.focus_wallets]:
            reason='Qualified prior evidence' if rank==2 else 'Promising prior evidence' if rank==1 else 'Exploratory; no proven edge'
            db.execute('INSERT INTO research_members VALUES(?,?,?,?)',(rid,wallet,reason,json.dumps(c)))
    return store.one('SELECT * FROM research_runs WHERE id=?',(rid,))


def enroll(store,config,now=None):
    now=now or time.time();run=ensure_run(store,config,now)
    # Freeze attributes at/before detection; never use subsequent market prices to match controls.
    candidates=store.rows('''SELECT s.*,k.first_seen FROM signals s JOIN tokens k ON k.mint=s.mint
       WHERE s.eligible=1 AND s.detected_at>=? AND s.detected_at<? AND s.observation_class='fresh'
       AND NOT EXISTS(SELECT 1 FROM research_samples r WHERE r.signal_id=s.id OR (r.run_id=? AND r.wallet=s.wallet AND r.mint=s.mint))
       ORDER BY s.detected_at,s.id LIMIT 500''',(run['started_at'],run['ends_at'],run['id']))
    members={r['wallet'] for r in store.rows('SELECT wallet FROM research_members WHERE run_id=?',(run['id'],))}
    with store.connect() as db:
        for s in candidates:
            snap=db.execute('SELECT * FROM snapshots WHERE mint=? AND observed_at<=? AND observed_at>=? ORDER BY observed_at DESC,id DESC LIMIT 1',
              (s['mint'],s['detected_at'],s['detected_at']-600)).fetchone()
            db.execute('INSERT OR IGNORE INTO research_samples(run_id,signal_id,wallet,mint,arm,detected_at,market_cap,liquidity,token_age) VALUES(?,?,?,?,?,?,?,?,?)',
              (run['id'],s['id'],s['wallet'],s['mint'],'selected' if s['wallet'] in members else 'control',s['detected_at'],
               snap['market_cap_usd'] if snap else None,snap['liquidity'] if snap else None,max(0,s['detected_at']-s['first_seen'])))
    return run


def evaluate_research(store,now=None):
    now=now or time.time()
    samples=store.rows('''WITH delays(d) AS (VALUES(60),(300),(900),(3600)), holds(h) AS (VALUES(3600),(21600),(86400))
      SELECT s.* FROM research_samples s WHERE s.detected_at>? AND EXISTS
       (SELECT 1 FROM delays CROSS JOIN holds WHERE s.detected_at+d+h+120<=?
        AND NOT EXISTS(SELECT 1 FROM research_results r WHERE r.sample_id=s.id AND r.delay=d AND r.horizon=h))
      ORDER BY s.detected_at,s.id LIMIT 50''',(now-9*86400,now))
    for sample in samples:
        for delay in DELAYS:
            target=sample['detected_at']+delay
            if now<target+3600+TOLERANCE:continue
            entry=store.one("SELECT * FROM snapshots WHERE mint=? AND observed_at BETWEEN ? AND ? AND status='observed' ORDER BY observed_at,id LIMIT 1",(sample['mint'],target,target+TOLERANCE))
            for horizon in HORIZONS:
                end_target=target+horizon
                if now<end_target+TOLERANCE:continue
                if store.one('SELECT 1 FROM research_results WHERE sample_id=? AND delay=? AND horizon=?',(sample['id'],delay,horizon)):continue
                end=store.one("SELECT * FROM snapshots WHERE mint=? AND observed_at BETWEEN ? AND ? AND status='observed' ORDER BY observed_at,id LIMIT 1",(sample['mint'],end_target,end_target+TOLERANCE))
                status='missing_entry' if not entry else 'missing_exit' if not end else 'estimated'
                ret=worst=best=profitable=max_gap=disadvantage=sold=None;path=[]
                if entry:
                    source=store.one('''SELECT t.quantity,v.usd_amount,v.price_at,t.chain_time FROM signals s JOIN trades t ON t.id=s.trade_id
                       LEFT JOIN trade_values v ON v.trade_id=t.id WHERE s.id=?''',(sample['signal_id'],))
                    if source and source['quantity']>0 and source['usd_amount'] and abs(source['price_at']-source['chain_time'])<=600 and entry['price']:
                        disadvantage=(entry['price']/(source['usd_amount']/source['quantity'])-1)*100
                    flow=store.one("SELECT COALESCE(SUM(quantity),0) q FROM trades WHERE wallet=? AND mint=? AND side='sell' AND chain_time>=? AND chain_time<=?",(sample['wallet'],sample['mint'],source['chain_time'] if source else sample['detected_at'],entry['observed_at']))
                    sold=flow['q']
                    try:
                        qty=entry_fill(entry['price'],entry['liquidity'],500)
                        path=store.rows('SELECT * FROM snapshots WHERE mint=? AND observed_at BETWEEN ? AND ? ORDER BY observed_at,id',(sample['mint'],entry['observed_at'],end['observed_at'] if end else end_target+TOLERANCE))
                        values=[];profitable=0.;max_gap=0.;prev=None
                        for point in path:
                            try:v=(exit_fill(point['price'],point['liquidity'],qty)/500-1)*100
                            except (ValueError,TypeError):v=None
                            if prev:
                                gap=point['observed_at']-prev[0];max_gap=max(max_gap,gap)
                                if gap<=120 and v is not None and v>0 and prev[1] is not None and prev[1]>0:profitable+=gap
                            prev=(point['observed_at'],v)
                            if v is not None:values.append(v)
                        if values:worst=min(values);best=max(values)
                        if end:
                            try:ret=(exit_fill(end['price'],end['liquidity'],qty)/500-1)*100
                            except (ValueError,TypeError):status='unexecutable_exit'
                    except (ValueError,TypeError):status='unexecutable_entry'
                store.execute('INSERT INTO research_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (sample['id'],delay,horizon,status,entry['observed_at'] if entry else None,end['observed_at'] if end else None,
                   ret,worst,best,profitable,len(path),max_gap,disadvantage,sold))


def stats(rows):
    values=[r['return_pct'] for r in rows if r['status']=='estimated' and r['return_pct'] is not None]
    return {'mature':len(rows),'priced':len(values),'coverage':100*len(values)/len(rows) if rows else None,
       'mean':mean(values) if values else None,'median':median(values) if values else None,
       'win_rate':100*sum(x>0 for x in values)/len(values) if values else None,
       'mean_loss':mean([x for x in values if x<0]) if any(x<0 for x in values) else None,
       'without_best':mean(sorted(values)[:-1]) if len(values)>1 else None,
       'unresolved':sum(r['status']!='estimated' for r in rows)}


def age_bucket(age):return 0 if age<3600 else 1 if age<86400 else 2

def matched(a,b):
    if a['mint']==b['mint'] or a['wallet']==b['wallet'] or abs(a['detected_at']-b['detected_at'])>21600:return False
    if age_bucket(a['token_age'])!=age_bucket(b['token_age']):return False
    return all(a[k] and b[k] and .5<=a[k]/b[k]<=2 for k in ('market_cap','liquidity'))


def experiment_summary(store,now=None):
    now=now or time.time();run=store.one('SELECT * FROM research_runs ORDER BY id DESC LIMIT 1')
    if not run:return {'run':None,'members':[],'comparisons':[]}
    members=store.rows('''SELECT m.*,w.last_scan,w.next_scan FROM research_members m JOIN wallets w ON w.address=m.wallet WHERE run_id=?''',(run['id'],))
    for m in members:m['prior']=json.loads(m['prior']);m['scan_age']=now-m['last_scan'] if m['last_scan'] else None
    samples=store.rows('SELECT * FROM research_samples WHERE run_id=? ORDER BY detected_at,id',(run['id'],))
    # One token per arm avoids treating a crowd of wallets buying one coin as independent successes.
    selected=[];controls=[];seen=set()
    for sample in samples:
        key=(sample['arm'],sample['mint'])
        if key in seen:continue
        seen.add(key);(selected if sample['arm']=='selected' else controls).append(sample)
    selected_mints={s['mint'] for s in selected}
    controls=[c for c in controls if c['mint'] not in selected_mints]
    # Greedy matching is chronological, deterministic, and independent of outcomes.
    pairs=[];used=set()
    edges={(r['source'],r['target']) for r in store.rows('SELECT DISTINCT source,target FROM links WHERE observed_at<=?',(run['started_at'],))}
    for a in selected:
        options=[b for b in controls if b['id'] not in used and matched(a,b) and (a['wallet'],b['wallet']) not in edges and (b['wallet'],a['wallet']) not in edges]
        if options:
            b=min(options,key=lambda b:(abs(a['detected_at']-b['detected_at']),b['id']));used.add(b['id']);pairs.append((a,b))
    results={(r['sample_id'],r['delay'],r['horizon']):r for r in store.rows('SELECT r.* FROM research_results r JOIN research_samples s ON s.id=r.sample_id WHERE s.run_id=?',(run['id'],))}
    comparisons=[]
    for delay in DELAYS:
        for horizon in HORIZONS:
            arows=[];brows=[];diff=[]
            for a,b in pairs:
                ar=results.get((a['id'],delay,horizon));br=results.get((b['id'],delay,horizon))
                if ar and br:
                    arows.append(ar);brows.append(br)
                    if ar['return_pct'] is not None and br['return_pct'] is not None:diff.append(ar['return_pct']-br['return_pct'])
            comparisons.append({'delay':delay,'horizon':horizon,'selected':stats(arows),'control':stats(brows),
              'paired_priced':len(diff),'excess_mean':mean(diff) if diff else None})
    return {'run':{**run,'rules':json.loads(run['rules'])},'members':members,'comparisons':comparisons,
      'selected_tokens':len(selected),'control_tokens':len(controls),'matched_pairs':len(pairs),
      'unmatched_selected':len(selected)-len(pairs),'distinct_days':len({int(s['detected_at']//86400) for s in selected}),
      'selected_wallets':len({s['wallet'] for s in selected}),'samples':len(samples),
      'note':'Exploratory sampled comparison, not proof of alpha. Token age is time since first observation. Missing match attributes remain unmatched. Links exclude direct pre-run transfers only; common ownership is unknown.'}


def wallet_research(store,wallet):
    rows=store.rows('''SELECT r.*,s.mint,s.detected_at,s.arm,s.run_id FROM research_results r JOIN research_samples s ON s.id=r.sample_id
       WHERE s.wallet=? ORDER BY s.detected_at DESC,r.delay,r.horizon LIMIT 240''',(wallet,))
    summaries=[]
    for delay in DELAYS:
        for horizon in HORIZONS:
            group=[r for r in rows if r['delay']==delay and r['horizon']==horizon]
            summaries.append({'delay':delay,'horizon':horizon,**stats(group)})
    return {'results':rows,'summaries':summaries,'limited_to':240}


def opportunities(store,config,experiment,now=None):
    from .positions import positions
    now=now or time.time();members={m['wallet']:m for m in experiment['members']}
    rows=store.rows('''SELECT s.*,t.chain_time,t.quantity,t.venue,t.quality,v.usd_amount,v.price_at,k.symbol
      FROM signals s JOIN trades t ON t.id=s.trade_id JOIN tokens k ON k.mint=s.mint
      LEFT JOIN trade_values v ON v.trade_id=t.id
      WHERE s.detected_at>? AND s.id=(SELECT MAX(s2.id) FROM signals s2 WHERE s2.wallet=s.wallet AND s2.mint=s.mint)
      ORDER BY s.detected_at DESC LIMIT 30''',(now-86400,))
    cache={};result=[]
    for row in rows:
        wallet=row['wallet']
        if wallet not in cache:cache[wallet]={p['mint']:p for p in positions(store,wallet)}
        p=cache[wallet].get(row['mint']);snap=store.one('SELECT * FROM snapshots WHERE mint=? ORDER BY observed_at DESC,id DESC LIMIT 1',(row['mint'],))
        quote=store.one('SELECT * FROM route_checks WHERE mint=? ORDER BY at DESC LIMIT 1',(row['mint'],))
        fresh=bool(snap and 0<=now-snap['observed_at']<=120)
        move=None
        if fresh and row['usd_amount'] and row['quantity']>0 and abs(row['price_at']-row['chain_time'])<=600 and 'instruction-local' not in row['quality'] and snap['price']:
            move=(snap['price']/(row['usd_amount']/row['quantity'])-1)*100
        flags=[]
        if not fresh:flags.append('Price older than two minutes or unavailable')
        if not snap or not snap['liquidity'] or snap['liquidity']<50000:flags.append('$500 exceeds modeled liquidity limit or liquidity unknown')
        if row['detected_at']-row['chain_time']>600:flags.append('Buy was over ten minutes old when detected')
        if move is not None and move>20:flags.append('Price more than 20% above observed entry estimate')
        if p and p['action'] in ('partial exit','observed exit','unknown token outflow'):flags.append('Wallet has sold or tokens moved out; inspect position history')
        if not row['eligible']:flags.append('Discovery/backfill observation; excluded from prospective tests')
        if not quote or quote['status']!='quoted' or now-quote['at']>120:flags.append('No fresh size-specific round-trip quote')
        result.append({**row,'position':p,'market':snap,'quote':quote,'move_since_buy':move,
          'price_fresh':fresh,'detection_seconds':row['detected_at']-row['chain_time'],
          'shortlisted':wallet in members,'selection_reason':members.get(wallet,{}).get('reason','Unproven discovery candidate'),
          'prior':members.get(wallet,{}).get('prior'),'flags':flags})
    return sorted(result,key=lambda r:(not r['shortlisted'],-r['detected_at']))
