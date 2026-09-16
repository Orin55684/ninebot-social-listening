"""August replay ingestion and evidence-only export. Never writes source files."""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
from . import replay, business

START='2026-08-01'
END='2026-09-01'
PLATFORMS={'抖音','小红书','快手','哔哩哔哩弹幕网'}

def setup(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS provenance(message_id TEXT PRIMARY KEY,platform TEXT,kind TEXT,ingested_at TEXT);
    CREATE TABLE IF NOT EXISTS import_audit(source TEXT PRIMARY KEY,details TEXT);''')
    c.commit()
    business.setup(c)

def normalize(name):
    return re.sub(r'[\s_｜|]','',name).casefold()

class Writer:
    def __init__(self,c):
        self.c=c
        self.salt=bytes.fromhex(c.execute("SELECT value FROM settings WHERE key='salt'").fetchone()[0])
        self.groups={};self.count=0;self.seen=0
        self.classifier=business.Classifier(c)
    def token(self,s):return hmac.new(self.salt,s.encode(),hashlib.sha256).hexdigest()[:24]
    def add(self,source,group,user,native,stamp,text,quote='',platform='',kind='text',ingested='',
            source_name='',channel='',group_name='',author='',source_file='',source_row='',raw_fields=None,force_candidate=False):
        raw_text=str(text or '');raw_quote=str(quote or '')
        clean=replay.scrub(raw_text)
        if not clean and not raw_text.strip():return 0
        key=self.token(f'{source}|{group}|{native}')
        gid=self.groups.setdefault((source,group),self.token(source+'|'+group))
        uid=self.token(source+'|'+group+'|'+(user or 'unknown:'+native))
        quote=replay.scrub(raw_quote);combined=raw_text+' '+raw_quote
        added=self.c.execute('INSERT OR IGNORE INTO messages(id,source,group_id,user_id,time,text,candidate,safety,quote_text) VALUES (?,?,?,?,?,?,?,?,?)',
           (key,source,gid,uid,stamp,clean,int(force_candidate or source=='voc' or bool(replay.KEYWORDS.search(combined))),int(bool(replay.SIGNALS.search(combined))),quote)).rowcount
        self.c.execute('INSERT OR REPLACE INTO provenance VALUES (?,?,?,?)',(key,platform,kind,ingested))
        if source=='voc' and raw_fields and ('正文' in raw_fields or '标题' in raw_fields):
            raw_text=raw_fields.get('正文','') if str(raw_fields.get('正文','')).strip() not in ('','--') else raw_fields.get('标题','')
        self.c.execute('INSERT OR REPLACE INTO original_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (key,raw_text,raw_quote,source_name or {'wecom':'企微社群','wechat_export':'民间微信群','voc':'公域 VOC','suggestions':'意见建议'}.get(source,source),
             channel or platform or source_name or source,group_name,platform,str(author or user or ''),str(native) if source!='suggestions' and kind!='md_text' else '',source_file,str(source_row),json.dumps(raw_fields or {},ensure_ascii=False,default=str)))
        topic,tag,method=self.classifier.classify(combined)
        self.c.execute('INSERT OR REPLACE INTO message_catalog VALUES (?,?,?,?)',(key,topic,tag,method))
        self.count+=added;self.seen+=1
        if self.seen%10000==0:self.c.commit()
        return added

def import_wecom(c,path):
    w=Writer(c);src=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    names={normalize(r[0]) for r in src.execute("SELECT name FROM wb_session WHERE session_type='room'") if r[0]}
    lo=int(dt.datetime.fromisoformat(START).replace(tzinfo=replay.TZ).timestamp());hi=int(dt.datetime.fromisoformat(END).replace(tzinfo=replay.TZ).timestamp())
    seen=0;added=0
    for group,user,mid,ts,text,name,record_id,staff_id,session_id,from_name in src.execute('''SELECT s.target_id,m.from_id,m.original_id,m.time,m.text_content,s.name,m.id,m.staff_id,m.session_id,m.from_name FROM wb_message m
       JOIN wb_session s ON m.staff_id=s.staff_id AND m.session_id=s.id
       WHERE s.session_type='room' AND m.type='text' AND m.time>=? AND m.time<? ORDER BY m.time,m.id''',(lo,hi)):
        seen+=1
        if group and mid:added+=w.add('wecom',group,user,mid,dt.datetime.fromtimestamp(ts,replay.TZ).isoformat(),text or '',source_name='企微社群',channel='企业微信',group_name=name or '',platform='企业微信',author=from_name or str(user or ''),source_file=Path(path).name,source_row=str(record_id),raw_fields={'群ID':group,'群名称':name,'发送者ID':user,'发送者名称':from_name,'原消息ID':mid,'原始时间戳':ts,'原文':text,'记录ID':record_id,'员工ID':staff_id,'会话ID':session_id})
    src.close();c.commit()
    audit(c,'wecom',{'source_text_rows':seen,'added':added,'coverage':'8月企微群文本；不含私聊和非文本消息'})
    return names

def audit(c,source,details):
    c.execute('INSERT OR REPLACE INTO import_audit VALUES (?,?)',(source,json.dumps(details,ensure_ascii=False)));c.commit()

def md_messages(path):
    """Two export layouts; parse timestamps without emitting source text."""
    heading=re.compile(r'^### (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) / (.*)$')
    bullet=re.compile(r'^- \[(\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?)\] (.*?): (.*)$')
    current=None;body=[]
    with path.open(encoding='utf-8-sig') as f:
        for line in f:
            m=heading.match(line.rstrip());b=bullet.match(line.rstrip())
            if m or b:
                if current:yield (*current,'\n'.join(body).strip())
                current=(m.group(1),m.group(2)) if m else (b.group(1),b.group(2))
                body=[] if m else [b.group(3)]
            elif current:body.append(line.rstrip())
    if current:yield (*current,'\n'.join(body).strip())

def group_name(path):
    if path.suffix=='.md':
        with path.open(encoding='utf-8-sig') as f:
            for _ in range(6):
                line=next(f,'').strip()
                m=re.match(r'^# (?:聊天记录[:：]\s*)?(.+)$',line)
                if m:return m.group(1)
    return re.sub(r'_\d{4}-\d\d-\d\d.*$','',path.stem)

def import_wechat(c,root,official):
    w=Writer(c);stats=collections.Counter();json_days=set();excluded=set()
    def skip(name):return normalize(name) in official or bool(re.search('官方|核心|售后',name))
    for p in sorted(Path(root).rglob('*.jsonl')):
        name=group_name(p)
        if skip(name):excluded.add(normalize(name));continue
        for line in p.open(encoding='utf-8-sig'):
            if not line.strip():continue
            try:
                d=json.loads(line);stamp=dt.datetime.fromtimestamp(d['create_time'],replay.TZ).isoformat()
                if not START<=stamp[:10]<END:continue
                json_days.add((normalize(name),stamp[:10]))
                if d['kind'] not in ('text','quote'):stats['nontext']+=1;continue
                native=str(d['id']['server_id_str'])
                if native in ('','0'):raise ValueError('id')
                quote=d.get('quote',{});quote=quote.get('text','') if isinstance(quote,dict) else ''
                stats['json_rows']+=1
                stats['json_added']+=w.add('wechat_export',normalize(name),d.get('sender',''),native,stamp,d['text'],quote,kind=d['kind'],source_name='民间微信群',channel='微信',group_name=name,platform='微信',author=d.get('sender',''),source_file=str(p.relative_to(root)),source_row=str(stats['json_rows']),raw_fields=d)
            except (ValueError,TypeError,KeyError):stats['invalid_json_rows']+=1
    for p in sorted(Path(root).rglob('*.md')):
        name=group_name(p)
        if skip(name):excluded.add(normalize(name));continue
        for stamp,user,text in md_messages(p):
            if not START<=stamp[:10]<END:continue
            if (normalize(name),stamp[:10]) in json_days:stats['md_shadowed_by_json_day']+=1;continue
            clean=replay.scrub(text)
            if not clean or re.fullmatch(r'\[.*?\]|!\[.*',clean):stats['md_nontext']+=1;continue
            stamp=dt.datetime.fromisoformat(stamp).replace(tzinfo=replay.TZ).isoformat()
            native='md:'+hashlib.sha256((stamp+'|'+user+'|'+clean).encode()).hexdigest()
            stats['md_rows']+=1
            stats['md_added']+=w.add('wechat_export',normalize(name),user,native,stamp,text,kind='md_text',source_name='民间微信群',channel='微信',group_name=name,platform='微信',author=user,source_file=str(p.relative_to(root)),source_row=stamp,raw_fields={'群名称':name,'时间':stamp,'作者':user,'原文':text})
    stats['excluded_official_or_core_names']=len(excluded);c.commit()
    audit(c,'wechat_export',{**stats,'coverage':'JSONL优先，MD补足未覆盖群日；已剔除同名企微群及官方/核心/售后群。剩余群的民间归属仍待人工核实；MD按时间/作者/文字去重可能合并完全相同消息。'})

def import_voc(c,path):
    w=Writer(c);stats=collections.Counter();names=collections.Counter()
    raw=Path(path).read_bytes()
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:text=raw.decode('gb18030')
    import io
    rows=csv.DictReader(io.StringIO(text))
    required={'ID','整体情感','研判状态','舆情状态','数据来源','发布时间','正文','标题','账号','帖子类型','入库时间'}
    if not required.issubset(rows.fieldnames or []):raise ValueError('VOC columns missing')
    for r in rows:
        stats['rows']+=1
        if not (r['整体情感'].strip()=='负面' and r['研判状态'].strip()=='已研判' and r['舆情状态'].strip() not in ('无需处理','无须处理','','--')):stats['business_excluded']+=1;continue
        if r['数据来源'] not in PLATFORMS:stats['other_platform_excluded']+=1;continue
        stamp=dt.datetime.fromisoformat(r['发布时间']).replace(tzinfo=replay.TZ).isoformat()
        if not START<=stamp[:10]<END:stats['outside_window']+=1;continue
        if not r['ID'].strip():raise ValueError('VOC id missing')
        body=r['正文'].strip();title=r['标题'].strip()
        if body in ('','--'):body=title;stats['title_fallback']+=1
        if body in ('','--'):stats['empty_text']+=1;continue
        if r['帖子类型']!='评论' and title not in ('','--') and title not in body:body=title+'\n'+body
        # Each VOC item remains its own evidence unit; same URL is not a thread.
        group=r['数据来源']+'|'+r['ID']
        stats['added']+=w.add('voc',group,r['账号'],r['ID'],stamp,body,platform=r['数据来源'],kind=r['帖子类型']+' / '+r['舆情状态'],ingested=r['入库时间'],source_name='公域 VOC',channel=r['数据来源'],author=r['账号'],source_file=Path(path).name,source_row=str(stats['rows']+1),raw_fields=r)
        names[r['数据来源']]+=1
    c.commit();audit(c,'voc',{**stats,'platforms':dict(names),'coverage':'发布时间8月；负面且已研判且非无需/无须处理；四平台；已删除仍保留；评论无上下文'})

def import_suggestions(c,root):
    return business.import_suggestions(c,root,Writer,audit)

def import_taxonomy(c,path):
    return business.import_taxonomy(c,path)

def sample(c,per_source=12):
    """Half safety-prioritized, half reproducible varied candidates per source."""
    ids=[]
    for source in ('wecom','wechat_export','voc','suggestions'):
        rows=c.execute('''SELECT m.id,m.safety FROM messages m LEFT JOIN analysis a ON a.message_id=m.id
          WHERE m.source=? AND m.candidate=1 AND a.status IS NULL ORDER BY m.id''',(source,)).fetchall()
        safety=[r['id'] for r in rows if r['safety']][:per_source//2]
        other=[r['id'] for r in rows if r['id'] not in safety and not r['safety']]
        picked=safety+other[:per_source-len(safety)]
        ids.extend(picked)
    return ids

def evidence_record(c,r):
    d=dict(r)
    original=c.execute('SELECT * FROM original_records WHERE message_id=?',(d['message_id'],)).fetchone()
    if original:
        raw=dict(original);raw['raw_fields']=json.loads(raw.pop('raw_json') or '{}');d.update(raw)
        d['original_available']=True
    else:
        d['original_available']=False
        d['raw_text']='';d['raw_quote']='';d['raw_fields']={}
    tag=c.execute('SELECT t.*,mc.classification_method FROM message_catalog mc JOIN business_taxonomy t ON t.id=mc.tag_id WHERE mc.message_id=?',(d['message_id'],)).fetchone()
    d['taxonomy']=dict(tag) if tag else None
    return d

def export_snapshot(c):
    sources=[]
    for r in c.execute("""SELECT source,count(*) imported,sum(candidate) candidates,min(time) first,max(time) last,
        count(DISTINCT substr(time,1,10)) days FROM messages GROUP BY source"""):
        d=dict(r);d['analyzed']=c.execute("SELECT count(*) FROM analysis a JOIN messages m ON m.id=a.message_id WHERE m.source=? AND a.status='ok'",(d['source'],)).fetchone()[0];sources.append(d)
    events=[]
    for row in c.execute("SELECT * FROM events ORDER BY level,day,id"):
        d=dict(row)
        if d['level']=='R4':continue
        d['analysis_status']='analysed'
        d['evidence']=[evidence_record(c,r) for r in c.execute("""SELECT m.id message_id,m.time,m.text,m.quote_text,m.source,a.intent,a.reason,a.confidence,a.context_json,p.platform,p.kind
           FROM evidence e JOIN messages m ON m.id=e.message_id JOIN analysis a ON a.message_id=m.id
           LEFT JOIN provenance p ON p.message_id=m.id WHERE e.event_id=? ORDER BY m.time,m.id""",(d['id'],))]
        d['taxonomy']=list({v['taxonomy']['id']:v['taxonomy'] for v in d['evidence'] if v['taxonomy']}.values())
        events.append(d)
    # A bounded queue of real, unanalysed suggestions is visibly separate from model output.
    for r in c.execute("""SELECT m.*,p.kind,mc.topic business_topic FROM messages m
        LEFT JOIN analysis a ON a.message_id=m.id LEFT JOIN provenance p ON p.message_id=m.id
        LEFT JOIN message_catalog mc ON mc.message_id=m.id
        WHERE m.source='suggestions' AND m.candidate=1 AND (a.status IS NULL OR a.status!='ok')
        ORDER BY m.safety DESC,CASE WHEN p.kind='问题投诉' THEN 0 ELSE 1 END,m.time,m.id LIMIT 12"""):
        v=evidence_record(c,{'message_id':r['id'],'source':r['source'],'time':r['time'],'text':r['text'],'quote_text':r['quote_text'],
            'kind':r['kind'],'intent':'待核实','reason':'原始反馈包含候选关键词或原始类型为问题投诉，尚未执行模型分析；不代表风险已成立。','confidence':None,
            'context_json':json.dumps({'limitations':'单条反馈记录；处理内容与用户原文分开保留，不把处理人员回复当成用户表述。','nearby_messages':[]},ensure_ascii=False)})
        events.append({'id':'suggestion-'+r['id'],'source':'suggestions','group_id':r['group_id'],'day':r['time'][:10],
            'topic':r['business_topic'] or '未分类','level':'','summary':'原始反馈待人工核实；未执行模型分析。',
            'message_count':1,'user_count':1,'review':'pending','issue':r['kind'] or '意见建议','vehicle':'待核实',
            'analysis_status':'unanalysed','evidence':[v],'taxonomy':[v['taxonomy']] if v['taxonomy'] else []})
    daily=[dict(r) for r in c.execute("""SELECT substr(m.time,1,10) day,m.source,count(*) imported,sum(m.candidate) candidates,
         sum(CASE WHEN a.status='ok' THEN 1 ELSE 0 END) analyzed FROM messages m LEFT JOIN analysis a ON a.message_id=m.id
         GROUP BY day,m.source ORDER BY day,m.source""")]
    return {'period':'2026年8月','generated_at':dt.datetime.now(replay.TZ).isoformat(),'sources':sources,'daily':daily,'events':events,
      'analysis':[dict(r) for r in c.execute('SELECT status,count(*) n FROM analysis GROUP BY status')],
      'r4':c.execute("SELECT count(*) FROM analysis WHERE status='ok' AND level='R4'").fetchone()[0],
      'taxonomy_count':c.execute('SELECT count(*) FROM business_taxonomy').fetchone()[0],
      'audit':{r[0]:json.loads(r[1]) for r in c.execute('SELECT * FROM import_audit')},
      'limits':['历史回放，非实时监控；各来源分析覆盖不同，以实际成功计数为准，不能外推未分析数据。','民间微信群归属尚未逐群确认；已排除已知官方重叠。','VOC负面预筛集与其他消息源不可直接比较负面率。','风险详情展示可追溯原始文字及真实渠道，模型预处理文字与原文分开保留。','公司标签仅通用和含电动范围；词面规则匹配待人工核实，未匹配保留未分类。','意见建议含原表的问题投诉；未分析候选仅作为原始线索。','周期自动化使用8月本地数据模拟接口获取；不连接实时采集或真实通知。']}
