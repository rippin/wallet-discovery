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

def cohort_stats(store,wallet,now):
    cutoff=now-30*86400
    rows=store.rows('''SELECT s.observation_class cohort,o.status,o.return_pct FROM signals s
      LEFT JOIN outcomes o ON o.signal_id=s.id AND o.delay=900 AND o.horizon=86400
      WHERE s.wallet=? AND s.eligible=1 AND s.detected_at>? AND s.detected_at<=?
      AND s.id=(SELECT s2.id FROM signals s2 WHERE s2.wallet=s.wallet AND s2.mint=s.mint
        AND s2.observation_class=s.observation_class AND s2.eligible=1 AND s2.detected_at>?
        ORDER BY s2.detected_at,s2.id LIMIT 1)''',(wallet,cutoff,now-900-86400-600,cutoff))
    results=[]
    for cohort in (*COHORTS,'legacy'):
        group=[r for r in rows if r['cohort']==cohort]
        values=[r['return_pct'] for r in group if r['status']=='estimated' and r['return_pct'] is not None]
        n=len(values);coverage=100*n/len(group) if group else None
        med=median(values) if n else None
        win=100*sum(v>0 for v in values)/n if n else None
        qualifies=cohort in COHORTS and n>=8 and coverage>=80 and med>0 and win>=60
        results.append({'cohort':cohort,'label':COHORT_LABELS[cohort],'samples':len(group),'priced_samples':n,
                        'mean_return':mean(values) if n else None,'median_return':med,
                        'coverage':coverage,'win_rate':win,'qualifies':qualifies,
                        'promising':cohort in COHORTS and n>=3 and coverage>=80 and med>0 and win>=60})
    return results

def display_cohort(stats):
    # Fixed priority among qualifying cohorts, otherwise largest mature sample.
    # Never combine fast and slow detections into a single performance figure.
    return next((s for s in stats if s['qualifies']),max(stats,key=lambda s:s['samples']))
