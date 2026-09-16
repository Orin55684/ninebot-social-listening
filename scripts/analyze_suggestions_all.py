"""Rate-limited concurrent batches, checkpoints and bounded retries; company only."""
import argparse
import collections
import concurrent.futures as futures
import datetime as dt
import fcntl
import json
import os
import signal
import time
from pathlib import Path
from dataclasses import replace
from community_demo import load_env
from ninebot_listening import august,replay,contextual,batch_analysis
from ninebot_listening.models import CompanyPrivateConfig,CompanyPrivateGateway


def main():
    p=argparse.ArgumentParser();p.add_argument('--rpm',type=int,default=30);p.add_argument('--batch-size',type=int,default=8);p.add_argument('--workers',type=int,default=6);p.add_argument('--limit',type=int,default=0);p.add_argument('--probe-rpm',action='store_true');a=p.parse_args()
    if not 1<=a.rpm<=60 or not 1<=a.batch_size<=10 or not 1<=a.workers<=8:raise ValueError('invalid bounds')
    os.umask(0o077);base=Path('data/august-demo');lock=(base/'suggestions-analysis.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    load_env('.env.local');c=replay.connect(base/'replay.db');august.setup(c)
    gateway=CompanyPrivateGateway(replace(CompanyPrivateConfig.from_env(),allow_production_data=True,timeout_seconds=120))
    rows=c.execute("SELECT m.* FROM messages m LEFT JOIN analysis a ON a.message_id=m.id WHERE m.source='suggestions' AND (a.status IS NULL OR a.status='failed') ORDER BY m.safety DESC,m.time,m.id").fetchall()
    if a.limit:rows=rows[:a.limit]
    queue=collections.deque((contextual.context_for(c,r),0,False) for r in rows)
    started=time.monotonic();rpm=a.rpm;next_send=0;active={};recent=collections.deque();stopping=False;last_snapshot=started
    stage_start=started;stage_requests=0;stage_success=0;stage_throttled=False;probe_enabled=a.probe_rpm;stable_rpm=None;probe_history=[]
    metrics={'requests':0,'successful_requests':0,'errors':0,'rate_limits':0,'completed_this_run':0,'permanently_failed':0,'tokens':0,'latency_seconds':0}
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def progress(status):
        counts=dict(c.execute("SELECT COALESCE(a.status,'pending'),count(*) FROM messages m LEFT JOIN analysis a ON a.message_id=m.id WHERE m.source='suggestions' GROUP BY COALESCE(a.status,'pending')").fetchall())
        d={'status':status,'updated_at':dt.datetime.now(replay.TZ).isoformat(),'counts':counts,'scope':'all_suggestions','rpm_limit':rpm,'batch_size':a.batch_size,'workers':a.workers,'elapsed_seconds':round(time.monotonic()-started,1),'metrics':metrics,'probe_history':probe_history,'stable_rpm':stable_rpm,'requests_last_60s':len(recent)}
        tmp=base/'suggestions-analysis-status.tmp';tmp.write_text(json.dumps(d,ensure_ascii=False));tmp.replace(base/'suggestions-analysis-status.json');print(json.dumps(d,ensure_ascii=False),flush=True)
    def snapshot():
        nonlocal last_snapshot
        replay.aggregate(c);c.execute('BEGIN');data=august.export_snapshot(c);c.commit()
        tmp=base/'snapshot.json.tmp';tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.replace(base/'snapshot.json');last_snapshot=time.monotonic()
    progress('running')
    try:
        with futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            while (queue and not stopping) or active:
                now=time.monotonic()
                while recent and now-recent[0]>=60:recent.popleft()
                if queue and not stopping and len(active)<a.workers and now>=next_send and len(recent)<rpm:
                    first=queue.popleft();batch=[first]
                    # Retry malformed batches as independent single-record requests.
                    if not first[2]:
                        while queue and len(batch)<a.batch_size and queue[0][1]==first[1] and not queue[0][2]:batch.append(queue.popleft())
                    future=pool.submit(batch_analysis.request,gateway,[x[0] for x in batch]);active[future]=(batch,now);recent.append(now);next_send=now+60/rpm;metrics['requests']+=1;stage_requests+=1
                for future in list(active):
                    if not future.done():continue
                    batch,t0=active.pop(future)
                    try:
                        response,results=future.result()
                        for context,attempt,single in batch:batch_analysis.save(c,context,results[context['target']['id']],response.model)
                        stage_success+=1;metrics['successful_requests']+=1;metrics['completed_this_run']+=len(batch);metrics['tokens']+=response.usage.get('total_tokens',0) or 0;metrics['latency_seconds']+=time.monotonic()-t0
                    except Exception as exc:
                        metrics['errors']+=1;cause=exc.__cause__;code=getattr(cause,'code',None)
                        if code==429:
                            metrics['rate_limits']+=1
                            if not stage_throttled:
                                probe_history.append({'rpm':rpm,'result':'rate_limited','requests':stage_requests,'successes':stage_success,'seconds':round(time.monotonic()-stage_start,1)})
                                rpm=stable_rpm if stable_rpm and stable_rpm<rpm else max(2,int(rpm*.65));stage_throttled=True;probe_enabled=False
                            next_send=max(next_send,time.monotonic()+60)
                        if code in (401,403):stopping=True
                        for context,attempt,single in batch:
                            if attempt<2:queue.append((context,attempt+1,isinstance(exc,ValueError)))
                            else:
                                c.execute('INSERT OR REPLACE INTO analysis(message_id,status,error) VALUES (?,?,?)',(context['target']['id'],'failed',type(exc).__name__+(':'+str(code) if code else '')));c.commit();metrics['permanently_failed']+=1
                        print(json.dumps({'error_type':type(exc).__name__,'http_status':code,'retry_records':len(batch),'validation_error':str(exc) if isinstance(exc,ValueError) else None}),flush=True)
                    progress('running' if not stopping else 'stopping')
                if time.monotonic()-stage_start>=90 and stage_success>=rpm and not stage_throttled:
                    if stable_rpm!=rpm:
                        probe_history.append({'rpm':rpm,'result':'observed_no_429','requests':stage_requests,'successes':stage_success,'seconds':round(time.monotonic()-stage_start,1)})
                        stable_rpm=rpm;progress('running')
                    if probe_enabled and rpm<60:
                        rpm=min(60,rpm+10);stage_start=time.monotonic();stage_requests=0;stage_success=0
                if stage_throttled and time.monotonic()>=next_send and not active:
                    stage_throttled=False;stage_start=time.monotonic();stage_requests=0;stage_success=0
                if time.monotonic()-last_snapshot>120:snapshot()
                time.sleep(.1)
        snapshot();progress('paused' if stopping else 'complete_with_errors' if metrics['permanently_failed'] else 'limited_test_complete' if a.limit else 'complete')
    except Exception as exc:progress('stopped_'+type(exc).__name__);raise
    finally:c.close();lock.close()

if __name__=='__main__':main()
