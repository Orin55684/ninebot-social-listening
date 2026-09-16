"""Persistent shared historical clock and message-level risk replay."""
import datetime as dt
import json
import sqlite3
import time
from pathlib import Path
from .reporting import SOURCES, detail_rows, item

TZ=dt.timezone(dt.timedelta(hours=8))
START=dt.datetime(2026,8,15,11,tzinfo=TZ)
END=dt.datetime(2026,8,31,23,59,59,tzinfo=TZ)

class SimulationClock:
    def __init__(self,path,wall=time.time):
        self.path=Path(path);self.wall=wall
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS clock(id INTEGER PRIMARY KEY CHECK(id=1), simulated REAL, wall REAL, speed REAL)')
            c.execute('INSERT OR IGNORE INTO clock VALUES(1,?,?,1)',(START.timestamp(),wall()))
    def connect(self):return sqlite3.connect(self.path,timeout=30)
    def state(self):
        with self.connect() as c:s,w,speed=c.execute('SELECT simulated,wall,speed FROM clock WHERE id=1').fetchone()
        stamp=min(END.timestamp(),s+max(0,self.wall()-w)*speed)
        return {'now':dt.datetime.fromtimestamp(stamp,TZ).isoformat(timespec='seconds'),'speed':0 if stamp>=END.timestamp() else speed,'end':END.isoformat(),'start':START.isoformat()}
    def now(self):return self.state()['now']
    def update(self,d):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            s,w,speed=c.execute('SELECT simulated,wall,speed FROM clock WHERE id=1').fetchone();now=min(END.timestamp(),s+max(0,self.wall()-w)*speed)
            action=d.get('action')
            if action=='reset':now=START.timestamp();speed=1
            elif action=='pause':speed=0
            elif action=='resume':speed=1
            elif action=='advance':
                seconds=d.get('seconds')
                if seconds not in (3600,86400):raise ValueError('仅支持快进1小时或1天')
                now=min(END.timestamp(),now+seconds)
            elif action=='speed':
                speed=d.get('speed')
                if speed not in (1,60,3600):raise ValueError('不支持的速度')
            else:raise ValueError('未知时钟操作')
            c.execute('UPDATE clock SET simulated=?,wall=?,speed=? WHERE id=1',(now,self.wall(),speed))
        return self.state()

class Simulation:
    def __init__(self,reporting,clock):self.reporting=reporting;self.clock=clock
    def dashboard(self):
        state=self.clock.state();now=dt.datetime.fromisoformat(state['now']);lo=now-dt.timedelta(days=1);week=now-dt.timedelta(days=7)
        with self.reporting.source(cutoff=state['now']) as c:
            sources={r[0]:r[1] for r in c.execute('SELECT source,count(*) FROM messages WHERE time>? GROUP BY source',(lo.isoformat(),))}
            records=c.execute("SELECT m.time,a.level FROM analysis a JOIN messages m ON m.id=a.message_id WHERE a.status='ok' AND a.level IN ('R1','R2','R3') AND m.time>?",(week.isoformat(),)).fetchall()
        days=[]
        for i in range(7):
            left=week+dt.timedelta(days=i);right=left+dt.timedelta(days=1)
            days.append({'start':left.isoformat(),'end':right.isoformat(),'label':right.strftime('%m.%d'),'count':sum(left.isoformat()<r[0]<=right.isoformat() for r in records)})
        return {'clock':state,'sources':[{'source':s,'count':sources.get(s,0)} for s in SOURCES], 'metrics':{'voices24':sum(sources.values()),'risks24':sum(r[0]>lo.isoformat() for r in records),'alerts24':sum(r[0]>lo.isoformat() and r[1] in ('R1','R2') for r in records),'alerts7':sum(r[1] in ('R1','R2') for r in records)},'daily':days,'events':[],'reviews':{},'history':[],'simulated_outbox':[]}
    def risks(self,params,reviews):
        level=params.get('level','');source=params.get('source','');status=params.get('status','');q=params.get('q','').strip().lower();page=int(params.get('page',1))
        if level not in ('','R1','R2','R3','R4') or source not in ('',*SOURCES) or status not in ('','pending','confirmed','rejected') or page<1:raise ValueError('筛选条件无效')
        with self.reporting.source() as c:
            found=[]
            for r in c.execute("SELECT m.id,m.time,m.source,a.* FROM analysis a JOIN messages m ON m.id=a.message_id WHERE a.status='ok' AND a.level IN ('R1','R2','R3') ORDER BY m.time DESC,m.id DESC"):
                r=dict(r);review=reviews.get('message:'+r['id'],{})
                if level and review.get('level',r['level'])!=level:continue
                if source and r['source']!=source:continue
                if status and review.get('decision','pending')!=status:continue
                if q and q not in ' '.join(str(r.get(k) or '') for k in ('topic','issue','vehicle','summary')).lower():continue
                found.append(r)
            total=len(found);pages=max(1,(total+19)//20);page=min(page,pages);selected=found[(page-1)*20:page*20]
            originals={r['id']:item(r) for r in detail_rows(c,[r['id'] for r in selected])} if selected else {}
        events=[]
        for r in selected:
            v=originals[r['id']];v.update(message_id=r['id'],intent=r['intent'],reason=r['reason'],confidence=r['confidence'],context_json='{}')
            events.append(dict(id='message:'+r['id'],source=r['source'],day=r['time'],time=r['time'],topic=r['topic'],issue=r['issue'],vehicle=r['vehicle'],level=r['level'],summary=r['summary'],analysis_status='analysed',evidence=[v],taxonomy=[]))
        return {'items':events,'total':total,'page':page,'page_size':20,'pages':pages}
    def valid_risk(self,eid):
        if not eid.startswith('message:'):return False
        with self.reporting.source() as c:
            return c.execute("SELECT 1 FROM messages m JOIN analysis a ON a.message_id=m.id WHERE m.id=? AND a.status='ok' AND a.level IN ('R1','R2','R3')",(eid[8:],)).fetchone() is not None
