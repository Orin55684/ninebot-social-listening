"""Local historical replay. Source files are always opened read-only."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from .models import DataClassification, ModelRequest
from . import contextual

TZ = dt.timezone(dt.timedelta(hours=8))
TOPICS = ['电池续航', '售后服务', '智能功能', '异响', '动力', '仪表', '安全', '其他']
LEVELS = ['R1', 'R2', 'R3', 'R4']
SIGNALS = re.compile('起火|冒烟|自燃|刹车失灵|制动失效|失控|行驶中断电|鼓包')
KEYWORDS = re.compile('续航|电池|充电|售后|维修|故障|异响|断电|刹车|黑屏|投诉|解锁|漏|坏|失灵|失控|起火|冒烟|自燃|鼓包')


def scrub(text: str) -> str:
    """Best-effort direct identifier removal; not a complete anonymizer."""
    text = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[链接或邮箱]', text)
    text = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '[手机号]', text)
    text = re.sub(r'(?<!\w)\d{17}[\dXx](?!\w)', '[身份证号]', text)
    text = re.sub(r'(?i)(?:wxid_[\w-]+|(?:微信号|手机号|电话|地址|姓名)\s*[:：]\s*\S+)', '[身份信息]', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()[:1500]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    c = sqlite3.connect(path)
    os.chmod(path, 0o600)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS messages(
      id TEXT PRIMARY KEY,source TEXT NOT NULL,group_id TEXT NOT NULL,user_id TEXT NOT NULL,
      time TEXT NOT NULL,text TEXT NOT NULL,candidate INTEGER NOT NULL,safety INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS analysis(
      message_id TEXT PRIMARY KEY,topic TEXT,level TEXT,summary TEXT,confidence REAL,
      status TEXT NOT NULL,error TEXT,model TEXT);
    CREATE TABLE IF NOT EXISTS events(
      id TEXT PRIMARY KEY,source TEXT,group_id TEXT,day TEXT,topic TEXT,level TEXT,
      summary TEXT,message_count INTEGER,user_count INTEGER,review TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS evidence(event_id TEXT,message_id TEXT,PRIMARY KEY(event_id,message_id));
    CREATE TABLE IF NOT EXISTS feedback(
      id INTEGER PRIMARY KEY,event_id TEXT,decision TEXT,level TEXT,note TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS outbox(
      event_id TEXT PRIMARY KEY,channel TEXT,status TEXT,payload TEXT);
    ''')
    additions={
        'messages':{'quote_text':"TEXT NOT NULL DEFAULT ''"},
        'analysis':{'issue':"TEXT DEFAULT '无法判断'",'vehicle':"TEXT DEFAULT '未识别'",
                    'intent':"TEXT DEFAULT '无法判断'",'reason':"TEXT DEFAULT ''",
                    'model_level':"TEXT DEFAULT ''",'version':"TEXT DEFAULT 'single-v1'",
                    'context_json':"TEXT DEFAULT '{}'"},
        'events':{'issue':"TEXT DEFAULT '无法判断'",'vehicle':"TEXT DEFAULT '未识别'"}}
    for table,fields in additions.items():
        existing={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        for field,definition in fields.items():
            if field not in existing:c.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
    c.execute('CREATE INDEX IF NOT EXISTS messages_context ON messages(source,group_id,time)')
    c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('salt', os.urandom(32).hex()))
    c.commit()
    return c


def token(c, value):
    salt = c.execute("SELECT value FROM settings WHERE key='salt'").fetchone()[0]
    return hmac.new(bytes.fromhex(salt), value.encode(), hashlib.sha256).hexdigest()[:24]


def add(c, source, group, sender, native_id, time, text, quote_text=''):
    clean = scrub(text)
    if not clean:
        return 0
    key = token(c, f'{source}|{group}|{native_id}')
    quote_text=scrub(quote_text)
    match_text=clean+' '+quote_text
    return c.execute('INSERT OR IGNORE INTO messages(id,source,group_id,user_id,time,text,candidate,safety,quote_text) VALUES (?,?,?,?,?,?,?,?,?)', (
        key, source, token(c, source+'|'+group), token(c, source+'|'+sender),
        time, clean, int(bool(KEYWORDS.search(match_text))), int(bool(SIGNALS.search(match_text))),quote_text
    )).rowcount


def import_wecom(c, path, start, end, per_group=50, limit=3000):
    counts=collections.Counter({r[0]:r[1] for r in c.execute(
        "SELECT group_id,count(*) FROM messages WHERE source='wecom' GROUP BY group_id")})
    existing=sum(counts.values())
    if existing>=limit:return 0
    src = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    src.execute('PRAGMA query_only=ON')
    imported = 0
    lo = int(dt.datetime.fromisoformat(start).replace(tzinfo=TZ).timestamp())
    hi = int(dt.datetime.fromisoformat(end).replace(tzinfo=TZ).timestamp())
    try:
        rows = src.execute('''SELECT s.target_id,m.from_id,m.original_id,m.time,m.text_content
          FROM wb_message m JOIN wb_session s ON m.staff_id=s.staff_id AND m.session_id=s.id
          WHERE s.session_type='room' AND m.type='text' AND m.time>=? AND m.time<?
          ORDER BY m.time,m.id''', (lo, hi))
        for group, sender, mid, timestamp, text in rows:
            group_key=token(c,'wecom|'+group)
            if counts[group_key] >= per_group or not text:
                continue
            added = add(c,'wecom',group,sender,mid,dt.datetime.fromtimestamp(timestamp,TZ).isoformat(),text)
            counts[group_key] += added; imported += added
            if existing+imported >= limit: break
    finally:
        src.close()
    c.commit(); return imported


def import_wechat(c, directory, start, end, per_group=50, limit=3000):
    counts=collections.Counter({r[0]:r[1] for r in c.execute(
        "SELECT group_id,count(*) FROM messages WHERE source='wechat_export' GROUP BY group_id")})
    existing=sum(counts.values()); imported = 0; invalid = 0
    if existing>=limit:return {'imported':0,'invalid':0}
    for path in sorted(Path(directory).rglob('*.jsonl')):
        with path.open(encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    if d['kind'] not in ('text','quote'): continue
                    stamp = dt.datetime.fromtimestamp(d['create_time'],TZ).isoformat()
                    if not start <= stamp[:10] < end: continue
                    group = d['id']['talker']; mid = d['id']['server_id_str']
                    if not group or not mid or mid=='0': raise ValueError('missing id')
                    group_key=token(c,'wechat_export|'+group)
                    if counts[group_key] >= per_group: continue
                    # Export has nicknames only. Identity is deliberately group-scoped.
                    sender = group+'|'+(d.get('sender') or 'unknown:'+mid)
                    quoted=d.get('quote',{})
                    quote_text=quoted.get('text','') if isinstance(quoted,dict) else ''
                    added = add(c,'wechat_export',group,sender,mid,stamp,d['text'],quote_text)
                    counts[group_key] += added; imported += added
                    if existing+imported >= limit:
                        c.commit(); return {'imported':imported,'invalid':invalid}
                except (KeyError,TypeError,ValueError): invalid += 1
    c.commit(); return {'imported':imported,'invalid':invalid}


def analyze(c, gateway, limit=40, request_interval=0):
    """One request per message, persistent checkpoints, no external fallback."""
    if c.execute("SELECT 1 FROM analysis WHERE status='ok' AND version!=? LIMIT 1",(contextual.VERSION,)).fetchone():
        raise ValueError('Use a separate V2 database; existing V1 reviews are preserved')
    rows = c.execute('''SELECT m.* FROM messages m LEFT JOIN analysis a ON m.id=a.message_id
       WHERE m.candidate=1 AND (a.status IS NULL OR a.status='failed')
       ORDER BY m.safety DESC,m.time,m.id''').fetchall()
    # Balance channels so one larger source does not exhaust the demo budget.
    queues = {s:collections.deque(r for r in rows if r['source']==s)
              for s in ('wecom','wechat_export')}
    selected=[]
    while len(selected)<limit and any(queues.values()):
        for q in queues.values():
            if q and len(selected)<limit: selected.append(q.popleft())
    failures=0; succeeded=0
    for index,r in enumerate(selected):
        if index and request_interval:time.sleep(request_interval)
        try:
            context=contextual.context_for(c,r)
            response=gateway.analyze_json(ModelRequest(
                system_prompt=contextual.prompt(TOPICS),
                user_prompt=json.dumps(context,ensure_ascii=False),
                data_classification=DataClassification.COMPANY_APPROVED,max_tokens=500))
            d=response.payload
            level=contextual.validate(d,TOPICS)
            reason=scrub(d['reason'])[:200]
            if level!=d['level']:
                reason+='；系统校验调整等级：咨询/否认等不升级，R1必须有明确安全反馈依据。'
            c.execute('''INSERT OR REPLACE INTO analysis
                (message_id,topic,level,summary,confidence,status,error,model,issue,vehicle,intent,reason,model_level,version,context_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (r['id'],d['topic'],level,scrub(d['summary'])[:200],d['confidence'],'ok',None,response.model,
                 d['issue'],scrub(d['vehicle']).upper(),d['intent'],reason,d['level'],
                 contextual.VERSION,json.dumps(context,ensure_ascii=False)))
            succeeded+=1; failures=0
        except Exception as exc:
            # Do not persist exception bodies, HTTP responses, credentials or source text.
            cause=exc.__cause__
            error=type(exc).__name__
            if cause is not None:
                error+=':'+type(cause).__name__
                if isinstance(getattr(cause,'code',None),int):error+=':'+str(cause.code)
            c.execute('INSERT OR REPLACE INTO analysis(message_id,status,error) VALUES (?,?,?)',
                      (r['id'],'failed',error))
            failures+=1
        c.commit()
        print(json.dumps({'analyzed_ok':succeeded,'consecutive_failures':failures}),flush=True)
        if failures>=2: break
    return succeeded


def aggregate(c):
    """Conservative same-source, same-group, same-day topic candidates."""
    groups=collections.defaultdict(list)
    for r in c.execute('''SELECT m.*,a.topic,a.level,a.summary,a.issue,a.vehicle FROM messages m
                         JOIN analysis a ON a.message_id=m.id WHERE a.status='ok' '''):
        groups[(r['source'],r['group_id'],r['time'][:10],r['topic'],r['issue'],r['vehicle'])].append(r)
    for key,rows in groups.items():
        eid=hashlib.sha256('|'.join(key).encode()).hexdigest()[:20]
        severity=min(r['level'] for r in rows)
        representative=min(rows,key=lambda r:(r['level'],r['time']))
        prior=c.execute('SELECT message_count FROM events WHERE id=?',(eid,)).fetchone()
        c.execute('''INSERT INTO events(id,source,group_id,day,topic,level,summary,message_count,user_count)
          VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          level=CASE WHEN events.review='pending' THEN excluded.level ELSE events.level END,
          summary=excluded.summary,message_count=excluded.message_count,
          user_count=excluded.user_count''',
          (eid,*key[:4],severity,representative['summary'],len(rows),len({r['user_id'] for r in rows})))
        c.execute('UPDATE events SET issue=?,vehicle=? WHERE id=?',(key[4],key[5],eid))
        if prior and prior[0]!=len(rows):
            c.execute("UPDATE events SET review='pending',level=? WHERE id=?",(severity,eid))
            c.execute('DELETE FROM outbox WHERE event_id=?',(eid,))
        for r in rows:c.execute('INSERT OR IGNORE INTO evidence VALUES (?,?)',(eid,r['id']))
    c.commit()


def review(c,event_id,decision,level,note):
    if decision not in ('confirmed','rejected') or level not in LEVELS: raise ValueError('invalid review')
    row=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
    if row is None: raise ValueError('unknown event')
    with c:
        c.execute('UPDATE events SET review=?,level=? WHERE id=?',(decision,level,event_id))
        c.execute('INSERT INTO feedback(event_id,decision,level,note,created_at) VALUES (?,?,?,?,?)',
            (event_id,decision,level,scrub(note),dt.datetime.now(TZ).isoformat()))
        c.execute('DELETE FROM outbox WHERE event_id=?',(event_id,))
        if decision=='confirmed' and level in ('R1','R2'):
            c.execute('INSERT INTO outbox VALUES (?,?,?,?)', (event_id,'simulation','simulated_only',
              json.dumps({'event_id':event_id,'level':level,'summary':row['summary'],'historical_demo':True},ensure_ascii=False)))


def stats(c):
    return {'sources':[dict(r) for r in c.execute('''SELECT source,count(*) messages,
      count(DISTINCT group_id) groups,sum(candidate) candidates FROM messages GROUP BY source''')],
      'analysis':[dict(r) for r in c.execute('SELECT status,count(*) n FROM analysis GROUP BY status')],
      'events':c.execute('SELECT count(*) FROM events').fetchone()[0],
      'simulated_notifications':c.execute('SELECT count(*) FROM outbox').fetchone()[0]}
