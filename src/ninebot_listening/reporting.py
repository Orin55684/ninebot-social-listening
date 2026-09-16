"""Local historical reports. Source databases are opened strictly read-only."""
from contextlib import contextmanager
import csv
import datetime as dt
import html
import io
import json
from pathlib import Path
import sqlite3
import uuid

SOURCES = {'wecom': '企微社群', 'wechat_export': '民间微信群（归属待核实）', 'voc': '公域VOC', 'suggestions': '意见建议（九号出行APP，含意见建议/问题投诉）'}
NOTICE = '2026年8月历史模拟，非实时接入；用户触发执行，无真实网络获取或自动调度。'
JOIN = ''' FROM messages m LEFT JOIN original_records o ON o.message_id=m.id
 LEFT JOIN message_catalog t ON t.message_id=m.id LEFT JOIN analysis a ON a.message_id=m.id '''
SELECT = '''m.id,m.time,m.source,m.text,m.quote_text,o.raw_text,o.raw_quote,o.source_name,o.channel,
 o.group_name,o.platform,o.author,o.native_id,o.source_file,o.source_row,o.raw_json,
 COALESCE(t.topic,'未分类') topic,t.tag_id,t.classification_method,a.status analysis_status,a.level analysis_level'''
CSV_HEADERS = dict(zip(
    ('id','time','source','text','quote_text','raw_text','raw_quote','source_name','channel','group_name','platform','author','native_id','source_file','source_row','raw_json','topic','tag_id','classification_method','analysis_status','analysis_level'),
    ('消息ID','消息时间','来源代码','脱敏文本','脱敏引用','完整原文','完整引用','原始来源名称','渠道','群名称','平台','作者','原始ID','源文件','源行号','完整源字段JSON','一级话题','主标签ID','分类方式（非人工最终标签）','分析状态','分析等级')))
METRICS = '''count(*) total,COALESCE(sum(a.status='ok'),0) analyzed_success,
 COALESCE(sum(a.status IS NULL),0) unanalyzed,
 COALESCE(sum(a.status IS NOT NULL AND a.status!='ok'),0) analysis_other,
 COALESCE(sum(a.status='ok' AND a.level IN ('R1','R2','R3')),0) analyzed_risk'''

class Unavailable(Exception):
    pass


def filters(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError('filters必须为对象')
    result = {k: value.get(k, '') for k in ('source','channel','topic','tag_id','q')}
    result.update(start=value.get('start') or '2026-08-01', end=value.get('end') or '2026-08-31')
    if any(not isinstance(v,str) for v in result.values()):
        raise ValueError('筛选条件必须为字符串')
    lo, hi = dt.date.fromisoformat(result['start']), dt.date.fromisoformat(result['end'])
    if lo.isoformat()!=result['start'] or hi.isoformat()!=result['end']:
        raise ValueError('日期格式须为YYYY-MM-DD')
    if not dt.date(2026,8,1) <= lo <= hi <= dt.date(2026,8,31):
        raise ValueError('日期须位于2026年8月且起始不晚于结束')
    if result['source'] and result['source'] not in SOURCES:
        raise ValueError('未知来源')
    return result


def where(f):
    clauses = ['m.time>=?', 'm.time<?']; args = [f['start'], (dt.date.fromisoformat(f['end'])+dt.timedelta(days=1)).isoformat()]
    for key, column in [('source','m.source'),('channel','o.channel'),('topic',"COALESCE(t.topic,'未分类')"),('tag_id','t.tag_id')]:
        if f[key]:
            clauses.append(column+'=?'); args.append(f[key])
    if f['q']:
        clauses.append("(instr(COALESCE(o.raw_text,m.text,''),?)>0 OR instr(COALESCE(o.raw_quote,m.quote_text,''),?)>0 OR instr(COALESCE(o.raw_json,''),?)>0)")
        args.extend([f['q']]*3)
    return ' WHERE '+' AND '.join(clauses),args


def query_from(f, analysis=False, topics=False):
    """Only join tables required by the filter or requested statistics."""
    sql = ' FROM messages m '
    if f['channel'] or f['q']:
        sql += ' LEFT JOIN original_records o ON o.message_id=m.id '
    if topics or f['topic'] or f['tag_id']:
        sql += ' LEFT JOIN message_catalog t ON t.message_id=m.id '
    if analysis:
        sql += ' LEFT JOIN analysis a ON a.message_id=m.id '
    return sql


def detail_rows(c, ids):
    """Load wide records only for an already selected page/export batch."""
    if not ids:
        return []
    rows = c.execute('SELECT '+SELECT+JOIN+' WHERE m.id IN ('+','.join('?' for _ in ids)+')', ids)
    by_id = {row['id']: row for row in rows}
    return [by_id[id] for id in ids if id in by_id]


def item(row):
    d = dict(row)
    if d['raw_json']:
        try: d['raw_json'] = json.loads(d['raw_json'])
        except (ValueError,TypeError): pass
    return d


def windows(f,period):
    if period not in ('daily','weekly','monthly','custom'):
        raise ValueError('未知报告周期')
    current = dt.date.fromisoformat(f['start']); end = dt.date.fromisoformat(f['end'])
    while current <= end:
        stop = current if period=='daily' else min(end,current+dt.timedelta(days=6-current.weekday())) if period=='weekly' else end
        yield current.isoformat(),stop.isoformat()
        current = stop+dt.timedelta(days=1)


class Reporting:
    def __init__(self,replay_path,state_path,clock=None):
        self.clock=clock
        self.path = Path(replay_path)
        p = Path(state_path); self.state = p.with_name(p.stem+'-reports.db')

    @contextmanager
    def source(self,cutoff=None):
        c = None
        try:
            c = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1.0)
            c.row_factory = sqlite3.Row
            cutoff=cutoff or (self.clock.now() if self.clock else None)
            if cutoff:
                # TEMP view applies the same time boundary to every query and export.
                safe=dt.datetime.fromisoformat(cutoff).isoformat().replace("'", "''")
                c.execute("CREATE TEMP VIEW messages AS SELECT * FROM main.messages WHERE time<='"+safe+"'")
            c.execute('PRAGMA query_only=ON')
            c.execute('SELECT '+SELECT+JOIN+' LIMIT 0')
            c.execute('SELECT id,level1,level2,level3,level4,description,department,domain,product_lines,path FROM business_taxonomy LIMIT 0')
            c.execute('BEGIN')
            yield c
        except sqlite3.Error as exc:
            raise Unavailable('历史数据尚未就绪或读取失败，请完成本地数据迁移后重试') from exc
        finally:
            if c is not None: c.close()

    @contextmanager
    def saved(self):
        c = sqlite3.connect(self.state)
        try:
            c.execute('CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            with c: yield c
        finally: c.close()

    def put(self,table,d):
        with self.saved() as c:
            c.execute('INSERT OR REPLACE INTO '+table+' VALUES (?,?)',(d['id'],json.dumps(d,ensure_ascii=False)))

    def get(self,table,id):
        with self.saved() as c: row = c.execute('SELECT payload FROM '+table+' WHERE id=?',(id,)).fetchone()
        if row is None: raise KeyError(id)
        d=json.loads(row[0])
        if table=='reports' and self.clock and (d.get('as_of') or d['filters']['end']+'T23:59:59+08:00')>self.clock.now():raise KeyError(id)
        return d

    def options(self):
        with self.source() as c:
            taxonomy = [dict(r) for r in c.execute("SELECT * FROM business_taxonomy ORDER BY path,id")]
            return {'range':{'start':'2026-08-01','end':self.clock.now()[:10] if self.clock else '2026-08-31'}, 'sources':[{'id':k,'label':v} for k,v in SOURCES.items()],
                'channels':[r[0] for r in c.execute("SELECT DISTINCT channel FROM original_records WHERE channel IS NOT NULL AND channel!='' ORDER BY channel")],
                'topics': sorted({r['level1'] for r in taxonomy if r['level1']}|{'未分类'}), 'taxonomy':[] if self.clock else taxonomy}

    def summary(self,c,f):
        sql,args=where(f)
        return dict(c.execute('SELECT '+METRICS+query_from(f,analysis=True)+sql,args).fetchone())

    def count(self,c,f):
        sql,args=where(f)
        return c.execute('SELECT count(*)'+query_from(f)+sql,args).fetchone()[0]

    def messages(self,params):
        f=filters(params); page=int(params.get('page',1)); size=int(params.get('page_size',30))
        if page<1 or not 1<=size<=200: raise ValueError('page须为正数，page_size须为1至200')
        sql,args=where(f)
        with self.source() as c:
            summary=self.summary(c,f)
            ids=[r[0] for r in c.execute('SELECT m.id'+query_from(f)+sql+' ORDER BY m.time DESC,m.id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size])]
            rows=detail_rows(c,ids)
            return {'total':summary['total'],'items':[item(r) for r in rows],'summary':summary,'page':page,'page_size':size}

    def message(self,id):
        with self.source() as c: row=c.execute('SELECT '+SELECT+JOIN+' WHERE m.id=?',(id,)).fetchone()
        if row is None: raise KeyError(id)
        return {'item':item(row)}

    def export(self,params,format):
        f=filters(params)
        if format not in ('csv','json'): raise ValueError('导出格式须为csv或json')
        # Open and validate before the HTTP headers are sent; close on disconnect too.
        context=self.source(); c=context.__enter__()
        try:
            sql,args=where(f); cursor=c.execute('SELECT m.id'+query_from(f)+sql+' ORDER BY m.time,m.id',args)
        except BaseException:
            context.__exit__(None,None,None); raise
        def chunks():
            try:
                if format=='json': yield b'['
                else:
                    yield b'\xef\xbb\xbf'
                    output=io.StringIO(); writer=csv.writer(output)
                    writer.writerow([CSV_HEADERS[r[0]] for r in c.execute('SELECT '+SELECT+JOIN+' LIMIT 0').description]); yield output.getvalue().encode('utf-8')
                first=True
                while True:
                    rows=cursor.fetchmany(500)
                    if not rows: break
                    for row in detail_rows(c,[r[0] for r in rows]):
                        d=item(row)
                        if format=='json':
                            yield (('' if first else ',')+json.dumps(d,ensure_ascii=False)).encode('utf-8'); first=False
                        else:
                            output.seek(0); output.truncate(0)
                            values=[]
                            for v in d.values():
                                s=json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else '' if v is None else str(v)
                                if s.lstrip().startswith(('=','+','-','@')) or s.startswith(('\t','\r','\n')): s="'"+s
                                values.append(s)
                            writer.writerow(values); yield output.getvalue().encode('utf-8')
                if format=='json': yield b']'
            finally: context.__exit__(None,None,None)
        return chunks()

    def generate(self,data):
        if not isinstance(data,dict): raise ValueError('请求须为对象')
        title=data.get('title','周期专项报告'); period=data.get('period','custom'); f=filters(data.get('filters'))
        if self.clock:f['end']=min(f['end'],self.clock.now()[:10])
        if f['start']>f['end']:raise ValueError('所选时间尚未到达')
        if not isinstance(title,str) or not title.strip() or len(title)>300: raise ValueError('标题须为1至300字符')
        spans=list(windows(f,period)); sql,args=where(f)
        with self.source() as c:
            grouped=[dict(r) for r in c.execute("SELECT substr(m.time,1,10) day,m.source,COALESCE(t.topic,'未分类') topic,"+METRICS+query_from(f,analysis=True,topics=True)+sql+" GROUP BY substr(m.time,1,10),m.source,COALESCE(t.topic,'未分类')",args)]
            def totals(rows):
                return {key:sum(row[key] for row in rows) for key in ('total','analyzed_success','unanalyzed','analysis_other','analyzed_risk')}
            selected_tag=c.execute('SELECT * FROM business_taxonomy WHERE id=?',(f['tag_id'],)).fetchone() if f['tag_id'] else None
            evidence_ids=[r[0] for r in c.execute('SELECT m.id'+query_from(f)+sql+' ORDER BY m.time,m.id LIMIT 5',args)]
            report={'id':uuid.uuid4().hex,'title':title,'period':period,'filters':f,'mode':'historical_simulation','notice':NOTICE,
                'selected_tag':dict(selected_tag) if selected_tag is not None else None,
                'topics':[dict(topic=topic,**totals([r for r in grouped if r['topic']==topic])) for topic in sorted({r['topic'] for r in grouped})],
                'summary':totals(grouped), 'buckets':[dict(start=lo,end=hi,**totals([r for r in grouped if lo<=r['day']<=hi])) for lo,hi in spans],
                'sources':[dict(source=s,**totals([r for r in grouped if r['source']==s])) for s in SOURCES if not f['source'] or f['source']==s],
                'evidence':[item(r) for r in detail_rows(c,evidence_ids)],
                'created_at':(self.clock.now() if self.clock else dt.datetime.now(dt.timezone.utc).isoformat()),'as_of':self.clock.now() if self.clock else None,
                'limits':['统计单位为消息，非事件；分析成功不等于人工核验。','unanalyzed仅无分析记录；analysis_other为失败或其他非成功状态。','已分析风险仅analysis.status=ok且R1/R2/R3；未分析原始候选不计入风险，不依赖events；不得外推全量风险率。','最多5条原文摘录；可通过消息CSV/JSON导出全部匹配原文及源字段。','每消息仅一个主标签；词面规则待核实，不是人工最终标签；未匹配保留未分类。']}
            for d in report['evidence']:
                for key in ('text','quote_text','raw_text','raw_quote'): d[key]=(d.get(key) or '')[:500]
                d.pop('raw_json',None)
        self.put('reports',report)
        return {'id':report['id'],'report':report}

    def schedule(self,data):
        if not isinstance(data,dict): raise ValueError('请求须为对象')
        f=filters(data.get('filters')); period=data.get('period'); list(windows(f,period))
        for k in ('name','title'):
            if not isinstance(data.get(k),str) or not data[k].strip() or len(data[k])>300: raise ValueError(k+'须为1至300字符')
        with self.source(): pass
        d={k:data[k] for k in ('name','title','period')}
        d.update(id=uuid.uuid4().hex,filters=f,created_at=(self.clock.now() if self.clock else dt.datetime.now(dt.timezone.utc).isoformat()),last_run=None)
        self.put('schedules',d); return {'schedule':d}

    def schedules(self):
        with self.source(): pass
        with self.saved() as c: items=[json.loads(r[0]) for r in c.execute('SELECT payload FROM schedules ORDER BY rowid DESC')]
        if self.clock:
            for d in items:
                if d.get('last_run') and (not d['last_run'].get('as_of') or d['last_run']['as_of']>self.clock.now()):d['last_run']=None
        return {'items':items}

    def run(self,id):
        schedule=self.get('schedules',id)
        effective=dict(schedule['filters'])
        if self.clock:effective['end']=min(effective['end'],self.clock.now()[:10])
        if effective['start']>effective['end']:raise ValueError('所选周期尚未到达')
        run={'as_of':self.clock.now() if self.clock else None,'id':uuid.uuid4().hex,'schedule_id':id,'mode':'historical_simulation','notice':NOTICE,'started_at':(self.clock.now() if self.clock else dt.datetime.now(dt.timezone.utc).isoformat()),'logs':[],'report_ids':[]}
        successful=[]
        for source in SOURCES:
            try:
                with self.source() as c: count=self.count(c,filters({'source':source}))
                run['logs'].append({'stage':'fetch','source':source,'status':'complete','count':count}); successful.append(source)
            except Unavailable as exc:
                run['logs'].append({'stage':'fetch','source':source,'status':'failed','count':None,'error':str(exc)})
        run['logs'].append({'stage':'integrate','status':'complete' if len(successful)==4 else 'partial' if successful else 'failed','count':sum(x['count'] or 0 for x in run['logs']) if successful else None})
        try:
            if len(successful)!=4:
                run['logs'].append({'stage':'filter','status':'failed','count':None,'error':'来源读取不完整，未执行过滤'})
                raise Unavailable('来源读取不完整，本次不生成可能不完整的报告')
            with self.source() as c: count=self.count(c,effective)
            run['logs'].append({'stage':'filter','status':'complete','count':count})
            for lo,hi in windows(effective,schedule['period']):
                result=self.generate(dict(title=schedule['title'],period=schedule['period'],filters=dict(effective,start=lo,end=hi)))
                run['report_ids'].append(result['id'])
            run['logs'].append({'stage':'report','status':'complete','count':len(run['report_ids'])})
            run['status']='complete'
        except (Unavailable,sqlite3.Error) as exc:
            run['logs'].append({'stage':'report','status':'failed','count':len(run['report_ids']),'error':str(exc)})
            run['status']='partial' if successful or run['report_ids'] else 'failed'
        run['finished_at']=(self.clock.now() if self.clock else dt.datetime.now(dt.timezone.utc).isoformat()); schedule['last_run']=run; self.put('schedules',schedule)
        return {'run':run}


def report_html(report):
    escape=lambda x:html.escape(str(x),quote=True)
    metrics=[('total','消息总量'),('analyzed_success','分析成功'),('unanalyzed','未分析'),('analysis_other','分析失败或其他状态'),('analyzed_risk','已分析风险 R1–R3')]
    def table(rows,leading):
        columns=leading+metrics
        return '<table><thead><tr>'+''.join('<th>'+escape(label)+'</th>' for _,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(row.get(key,''))+'</td>' for key,_ in columns)+'</tr>' for row in rows)+'</tbody></table>'
    f=report['filters']; selected=report.get('selected_tag') or {}
    selections=[('日期',f['start']+' 至 '+f['end']),('来源',SOURCES.get(f['source'],f['source']) or '全部'),
        ('渠道',f['channel'] or '全部'),('话题',f['topic'] or '全部'),('标签路径',selected.get('path') or f['tag_id'] or '全部'),('关键词',f['q'] or '无')]
    selection_html=''.join('<p>'+escape(label)+'：'+escape(value)+'</p>' for label,value in selections)
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>',escape(report['title']),'</title>',
        '<style>body{font:14px sans-serif;max-width:1100px;margin:32px auto;color:#182838}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #bbb;padding:8px;text-align:left}p,blockquote{white-space:pre-wrap;overflow-wrap:anywhere}h2{margin-top:28px}tr{break-inside:avoid}@media print{body{margin:0}thead{display:table-header-group}}</style>',
        '<h1>',escape(report['title']),'</h1><p>',escape(NOTICE),'</p><p>生成时间：',escape(report['created_at']),'</p><h2>筛选范围</h2>',selection_html,
        '<h2>消息统计</h2>',table([report['summary']],[]),'<h2>周期汇总</h2>',table(report['buckets'],[('start','开始日期'),('end','结束日期')]),
        '<h2>话题分布（词面规则待核实）</h2>',table(report.get('topics',[]),[('topic','一级话题')]),
        '<h2>来源汇总</h2>',table([dict(r,label=SOURCES.get(r['source'],r['source'])) for r in report['sources']],[('label','来源')]),'<h2>原文摘录（最多5条，可完整导出）</h2>']
    for row in report['evidence']:
        provenance=[('消息ID',row['id']),('渠道',row.get('channel')),('群名称',row.get('group_name')),('平台',row.get('platform')),
            ('源文件',row.get('source_file')),('源行号',row.get('source_row'))]
        parts.append('<p>'+escape('；'.join(label+'：'+str(value if value is not None and value!='' else '未提供') for label,value in provenance))+'</p>')
        parts.extend(['<p>',escape(row['time']),' · ',escape(SOURCES.get(row['source'],row['source'])),' · ',escape(row.get('topic','未分类')),'</p><p>原始正文摘录（最多500字）</p><blockquote>',escape(row.get('raw_text') or '原始正文未提供'),'</blockquote>',
            '<p>原始引用摘录（最多500字）</p><blockquote>',escape(row.get('raw_quote') or '原始引用未提供'),'</blockquote>'])
    parts.extend(['<h2>统计说明</h2><ul>',''.join('<li>'+escape(v)+'</li>' for v in report['limits']),'</ul></html>'])
    return ''.join(parts).encode('utf-8')
