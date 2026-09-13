"""Bounded, durable signature windows. RPC lists backwards; windows advance forwards."""
import time
from .chain import PUMP,LAB,parse
from .providers import ProviderError

PROGRAM_NAMES={PUMP:'Pump.fun',LAB:'LaunchLab'}

class Discovery:
    def __init__(self,collector):
        self.c=collector;self.s=collector.store;self.cfg=collector.config

    def enumerate_page(self,program):
        window=self.s.one("SELECT * FROM discovery_windows WHERE program=? AND state='enumerating' ORDER BY id LIMIT 1",(program,))
        if not window:
            previous=self.s.one("SELECT head FROM discovery_windows WHERE program=? AND state='ready' ORDER BY id DESC LIMIT 1",(program,))
            ident=self.s.execute('INSERT INTO discovery_windows(program,started_at,previous_cursor) VALUES(?,?,?)',
                                 (program,time.time(),previous['head'] if previous else None))
            window=self.s.one('SELECT * FROM discovery_windows WHERE id=?',(ident,))
        page=self.c.providers.signatures(program,'discovery',window['before_signature'],limit=self.cfg.discovery_page_size)
        rows=[];reached=False
        for item in page:
            if item['signature']==window['previous_cursor']:
                reached=True;break
            rows.append(item)
        # Initial bootstrap intentionally starts with one recent page; no historic completeness claim.
        done=reached or len(page)<self.cfg.discovery_page_size or window['previous_cursor'] is None
        pages=window['pages']+1
        capped=not done and pages>=self.cfg.discovery_max_pages
        # A short page before the old cursor is also a coverage gap (history/provider truncation).
        gap=bool(window['previous_cursor'] and not reached and (capped or len(page)<self.cfg.discovery_page_size))
        with self.s.connect() as db:
            pending=db.execute("SELECT COUNT(*) FROM discovery_queue WHERE status='pending'").fetchone()[0]
            capacity=max(0,self.cfg.discovery_queue_cap-pending)
            failed=skipped=0
            for index,item in enumerate(rows):
                if item.get('err'):
                    failed+=1;continue
                if db.execute('SELECT 1 FROM discovery_queue WHERE program=? AND signature=?',(program,item['signature'])).fetchone():continue
                if capacity<=0:
                    skipped+=1;continue
                db.execute('INSERT INTO discovery_queue(program,signature,window_id,chain_time,sequence) VALUES(?,?,?,?,?)',
                           (program,item['signature'],window['id'],item.get('blockTime'),window['available']+index))
                capacity-=1
            db.execute('''UPDATE discovery_windows SET head=COALESCE(head,?),before_signature=?,pages=?,
                       available=available+?,failed=failed+?,skipped=skipped+?,gap=MAX(gap,?),state=?,completed_at=? WHERE id=?''',
                       (page[0]['signature'] if page else window['previous_cursor'],page[-1]['signature'] if page else None,
                        pages,len(rows),failed,skipped,int(gap),'ready' if done or capped else 'enumerating',
                        time.time() if done or capped else None,window['id']))
        if gap:self.s.event('coverage',PROGRAM_NAMES[program]+': signature window ended before its previous cursor; older gap size unknown')
        return window['id']

    def inspect_one(self,program):
        item=self.s.one('''SELECT q.* FROM discovery_queue q JOIN discovery_windows w ON w.id=q.window_id
          WHERE q.program=? AND q.status='pending' AND w.state='ready'
          ORDER BY q.window_id,q.sequence DESC LIMIT 1''',(program,))
        if not item:return False
        tx=self.c.load_tx(item['signature'],'discovery')
        if not tx or tx.get('blockTime') is None:
            attempts=item['attempts']+1
            with self.s.connect() as db:
                db.execute('UPDATE discovery_queue SET attempts=?,status=? WHERE program=? AND signature=?',
                           (attempts,'unavailable' if attempts>=3 else 'pending',program,item['signature']))
                if attempts>=3:db.execute('UPDATE discovery_windows SET unavailable=unavailable+1 WHERE id=?',(item['window_id'],))
            return True
        trades,_,status=parse(tx)
        self.c.ingest(item['signature'],tx,'discovery')
        with self.s.connect() as db:
            db.execute("UPDATE discovery_queue SET status='inspected' WHERE program=? AND signature=?",(program,item['signature']))
            db.execute('UPDATE discovery_windows SET inspected=inspected+1,ambiguous=ambiguous+?,unsupported=unsupported+? WHERE id=?',
                       (int(status=='ambiguous_swap'),int(status=='transfer_or_unsupported'),item['window_id']))
            for t in trades:
                if t['side']=='buy' and t['venue'] in ('pumpfun','launchlab'):
                    db.execute('INSERT OR IGNORE INTO discovery_buyers VALUES(?,?)',(item['window_id'],t['wallet']))
        return True

    def tick(self):
        # Alternate the first launchpad each tick so tight budgets cannot starve LaunchLab.
        turn=self.s.meta('discovery_turn') or 0
        programs=(PUMP,LAB) if turn%2==0 else (LAB,PUMP)
        self.s.meta('discovery_turn',turn+1)
        remaining=self.cfg.discovery_requests
        for program in programs:
            try:self.enumerate_page(program)
            except ProviderError as e:self.s.event('provider',str(e))
            remaining-=1
        while remaining>0 and not self.c.stop.is_set():
            progress=False
            for program in programs:
                if remaining<=0:break
                try:worked=self.inspect_one(program)
                except ProviderError as e:
                    self.s.event('provider',str(e));worked=False
                # Account for at most one primary attempt per inspection (fallback is separately bounded).
                remaining-=1;progress=progress or worked
            if not progress:break
        self.s.meta('discovery_tick',{'at':time.time(),'requests_cap':self.cfg.discovery_requests})


def coverage(store):
    result=[]
    for program,name in PROGRAM_NAMES.items():
        totals=store.one('''SELECT COUNT(*) windows,COALESCE(SUM(available),0) available,
           COALESCE(SUM(inspected),0) inspected,COALESCE(SUM(failed),0) failed,
           COALESCE(SUM(skipped),0) skipped,COALESCE(SUM(unavailable),0) unavailable,
           COALESCE(SUM(ambiguous),0) ambiguous,COALESCE(SUM(unsupported),0) unsupported,
           COALESCE(SUM(gap),0) gaps FROM discovery_windows WHERE program=?''',(program,))
        pending=store.one("SELECT COUNT(*) n,MIN(chain_time) oldest FROM discovery_queue WHERE program=? AND status='pending'",(program,))
        buyers=store.one('''SELECT COUNT(DISTINCT b.wallet) n FROM discovery_buyers b
                            JOIN discovery_windows w ON w.id=b.window_id WHERE w.program=?''',(program,))
        latest=store.one('SELECT * FROM discovery_windows WHERE program=? ORDER BY id DESC LIMIT 1',(program,))
        result.append({**totals,'program':name,'pending':pending['n'],'oldest_pending_at':pending['oldest'],
                       'unique_buyers':buyers['n'],'latest':latest})
    return result
