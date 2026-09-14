"""Versioned observation eligibility and shared ranking calculations."""
from statistics import mean, median

COHORTS=('fresh','delayed','late')
COHORT_LABELS={'fresh':'≤10m old','delayed':'10–60m old','late':'>60m old','legacy':'Legacy rules'}

def classify(known_at,chain_time,detected_at):
    if chain_time>detected_at:
        return 'future',False
    if known_at is None:
        return 'discovery',False
    if chain_time<known_at:
        return 'backfill',False
    age=detected_at-chain_time
    return ('fresh' if age<=600 else 'delayed' if age<=3600 else 'late'),True

def cohort_stats(store,wallet,now,horizon=86400):
    cutoff=now-30*86400
    rows=store.rows('''SELECT s.observation_class cohort,s.detected_at,o.status,o.return_pct FROM signals s
      LEFT JOIN outcomes o ON o.signal_id=s.id AND o.delay=900 AND o.horizon=?
      WHERE s.wallet=? AND s.eligible=1 AND s.detected_at>?
      AND s.id=(SELECT s2.id FROM signals s2 WHERE s2.wallet=s.wallet AND s2.mint=s.mint
        AND s2.observation_class=s.observation_class AND s2.eligible=1 AND s2.detected_at>?
        ORDER BY s2.detected_at,s2.id LIMIT 1)''',(horizon,wallet,cutoff,cutoff))
    results=[]
    for cohort in (*COHORTS,'legacy'):
        all_group=[r for r in rows if r['cohort']==cohort]
        group=[r for r in all_group if r['detected_at']+900+horizon+600<=now]
        waiting=[r for r in all_group if r['detected_at']+900+horizon+600>now]
        values=[r['return_pct'] for r in group if r['status']=='estimated' and r['return_pct'] is not None]
        n=len(values);coverage=100*n/len(group) if group else None
        med=median(values) if n else None
        win=100*sum(v>0 for v in values)/n if n else None
        qualifies=horizon==86400 and cohort in COHORTS and n>=8 and coverage>=80 and med>0 and win>=60
        results.append({'cohort':cohort,'label':COHORT_LABELS[cohort],'samples':len(group),'priced_samples':n,
                        'mean_return':mean(values) if n else None,'median_return':med,
                        'coverage':coverage,'win_rate':win,'qualifies':qualifies,
                        'waiting_samples':len(waiting),'total_samples':len(all_group),
                        'next_matures_at':min((r['detected_at']+900+horizon+600 for r in waiting),default=None),
                        'awaiting_calculation':sum(r['status'] is None or r['status']=='pending' for r in group),
                        'missing_samples':sum(r['status']=='missing_data' for r in group),
                        'illiquid_samples':sum(r['status']=='insufficient_liquidity' for r in group),
                        'mean_pnl_usd':mean(values)*5 if n else None,
                        'promising':horizon==86400 and cohort in COHORTS and n>=3 and coverage>=80 and med>0 and win>=60})
    return results

def display_cohort(stats):
    # Fixed priority among qualifying cohorts, otherwise largest mature sample.
    # Never combine fast and slow detections into a single performance figure.
    return next((s for s in stats if s['qualifies']),max(stats,key=lambda s:(s['samples'],s.get('total_samples',0))))


def following_evidence(store,wallet,now,day_stats=None):
    results=[]
    for horizon,label in ((3600,'1h'),(21600,'6h'),(86400,'24h')):
        groups=day_stats if horizon==86400 and day_stats is not None else cohort_stats(store,wallet,now,horizon)
        results.append({'horizon':horizon,'label':label,'cohorts':groups,'selected':display_cohort(groups)})
    activity=store.one("""SELECT COUNT(*) trades,SUM(side='buy') buys,SUM(side='sell') sells,
                         COUNT(DISTINCT mint) tokens,MAX(observed_at) last_observed FROM trades WHERE wallet=?""",(wallet,))
    observations=store.one("""SELECT COUNT(*) observations,SUM(eligible=1) eligible,
                            SUM(eligible=0) excluded FROM signals WHERE wallet=?""",(wallet,))
    return {'following':results,'activity':activity,'observations':observations}
