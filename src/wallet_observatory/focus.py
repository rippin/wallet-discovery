"""A bounded forward queue for the frozen shortlist; shared tracking quota applies."""
import time
from .providers import ProviderError


def poll_focus(collector,run,now):
    s=collector.store
    members=s.rows('SELECT wallet FROM research_members WHERE run_id=?',(run['id'],))
    with s.connect() as db:
        for m in members:
            db.execute('INSERT OR IGNORE INTO focus_state(wallet,cursor) SELECT address,cursor FROM wallets WHERE address=?',(m['wallet'],))
    state=s.one('''SELECT f.* FROM focus_state f JOIN research_members m ON m.wallet=f.wallet
      WHERE m.run_id=? AND f.next_scan<=? ORDER BY f.next_scan,f.wallet LIMIT 1''',(run['id'],now))
    if not state:return
    wallet=state['wallet']
    # Schedule before work so a provider outage doesn't repeatedly hammer one wallet.
    s.execute('UPDATE focus_state SET next_scan=? WHERE wallet=?',(now+collector.config.focus_seconds,wallet))
    try:
        page=collector.providers.signatures(wallet,'tracking',limit=20)
        pending=[];reached=False
        for item in page:
            if item['signature']==state['cursor']:reached=True;break
            if not item.get('err'):pending.append(item)
        with s.connect() as db:
            capacity=max(0,2000-db.execute('SELECT COUNT(*) FROM focus_queue WHERE wallet=?',(wallet,)).fetchone()[0])
            omitted=0
            for item in pending:
                if db.execute('SELECT 1 FROM focus_queue WHERE wallet=? AND signature=?',(wallet,item['signature'])).fetchone():continue
                if capacity<=0:omitted+=1;continue
                capacity-=1
                db.execute('INSERT OR IGNORE INTO focus_queue(wallet,signature,chain_time) VALUES(?,?,?)',(wallet,item['signature'],item.get('blockTime')))
            if omitted:db.execute('UPDATE focus_state SET gaps=gaps+? WHERE wallet=?',(omitted,wallet))
            db.execute('UPDATE focus_state SET cursor=COALESCE(?,cursor),last_poll=?,gaps=gaps+? WHERE wallet=?',
              (page[0]['signature'] if page else None,time.time(),int(bool(state['cursor']) and len(page)==20 and not reached),wallet))
        for item in s.rows('SELECT * FROM focus_queue WHERE wallet=? ORDER BY chain_time,signature LIMIT 2',(wallet,)):
            tx=collector.load_tx(item['signature'],'tracking')
            if tx and tx.get('blockTime') is not None:
                collector.ingest(item['signature'],tx,'tracking',watch=wallet)
                s.execute('DELETE FROM focus_queue WHERE wallet=? AND signature=?',(wallet,item['signature']))
            elif item['attempts']>=2:
                s.execute('DELETE FROM focus_queue WHERE wallet=? AND signature=?',(wallet,item['signature']))
                s.execute('UPDATE focus_state SET gaps=gaps+1 WHERE wallet=?',(wallet,))
            else:s.execute('UPDATE focus_queue SET attempts=attempts+1 WHERE wallet=? AND signature=?',(wallet,item['signature']))
    except ProviderError as e:s.event('provider',str(e))


def focus_health(store,run_id,now):
    return store.rows('''SELECT f.wallet,f.last_poll,f.next_scan,f.gaps,?-f.last_poll poll_age,
      (SELECT COUNT(*) FROM focus_queue q WHERE q.wallet=f.wallet) pending,
      (SELECT ?-MIN(chain_time) FROM focus_queue q WHERE q.wallet=f.wallet) backlog_age
      FROM focus_state f JOIN research_members m ON m.wallet=f.wallet WHERE m.run_id=?''',(now,now,run_id))
