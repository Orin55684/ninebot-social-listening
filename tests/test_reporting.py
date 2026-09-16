import csv
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import os
from unittest.mock import patch
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from ninebot_listening.reporting import Reporting, Unavailable, report_html, filters, where, query_from


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.db=self.root/'replay.db'; c=sqlite3.connect(self.db)
        c.executescript('''CREATE TABLE messages(id TEXT PRIMARY KEY,time TEXT,source TEXT,text TEXT,quote_text TEXT);
        CREATE TABLE analysis(message_id TEXT PRIMARY KEY,status TEXT,level TEXT);
        CREATE TABLE original_records(message_id TEXT PRIMARY KEY,raw_text TEXT,raw_quote TEXT,source_name TEXT,channel TEXT,group_name TEXT,platform TEXT,author TEXT,native_id TEXT,source_file TEXT,source_row TEXT,raw_json TEXT);
        CREATE TABLE message_catalog(message_id TEXT PRIMARY KEY,topic TEXT,tag_id TEXT,classification_method TEXT);
        CREATE TABLE business_taxonomy(id TEXT PRIMARY KEY,level1 TEXT,level2 TEXT,level3 TEXT,level4 TEXT,description TEXT,department TEXT,domain TEXT,product_lines TEXT,path TEXT);''')
        for i,source in enumerate(('wecom','wechat_export','voc','suggestions')):
            id=str(i); day='01' if i<2 else '31'
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(id,f'2026-08-{day}T23:59:59+08:00',source,'redacted',''))
            c.execute('INSERT INTO original_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(id,'=SUM(1,2)' if i==0 else '<script>原文</script>'+'长'*2000,'完整引用','真实来源','真实渠道','群','平台','作者',id,'fixture','1',json.dumps({'完整字段':'原值','number':i},ensure_ascii=False)))
            if i<3:c.execute('INSERT INTO message_catalog VALUES (?,?,?,?)',(id,'服务','leaf','词面规则待核实'))
        c.execute("INSERT INTO analysis VALUES ('0','ok','R1'),('1','ok','R4'),('2','failed',NULL)")
        c.execute("INSERT INTO business_taxonomy VALUES ('leaf','服务','','','维修','描述','部门','产品设计','电动 ,短交通','服务/维修'),('other','隐藏','','','','','','其他','','隐藏')")
        c.commit();c.close();self.original=self.db.read_bytes()
        self.r=Reporting(self.db,self.root/'state.db')
    def tearDown(self):
        self.assertEqual(self.original,self.db.read_bytes())
        self.assertFalse((self.root/'state.db').exists())
        self.tmp.cleanup()
    def test_filters_full_text_and_summary(self):
        result=self.r.messages({'page_size':'1'})
        self.assertEqual(result['summary'],dict(total=4,analyzed_success=2,unanalyzed=1,analysis_other=1,analyzed_risk=1))
        self.assertEqual(len(result['items']),1)
        self.assertEqual(self.r.messages({'start':'2026-08-31','end':'2026-08-31'})['total'],2)
        self.assertEqual(self.r.messages({'source':'suggestions','topic':'未分类','channel':'真实渠道','q':'原值'})['total'],1)
        self.assertEqual(self.r.messages({'tag_id':'leaf'})['total'],3)
        self.assertEqual(self.r.messages({'source':'suggestions'})['summary']['analyzed_risk'],0)
        self.assertGreater(len(self.r.message('3')['item']['raw_text']),2000)
        self.assertEqual(self.r.messages({'q':"' OR 1=1 --"})['total'],0)
        for bad in ({'start':'2026-09-01'},{'page_size':'0'},{'source':'invented'},{'page':'0'}):
            with self.assertRaises(ValueError):self.r.messages(bad)
        options=self.r.options();self.assertEqual(len(options['sources']),4)
        self.assertEqual(options['channels'],['真实渠道']);self.assertEqual(len(options['taxonomy']),2)
        self.assertTrue(any(r['id']=='leaf' and r['domain']=='产品设计' and r['product_lines']=='电动 ,短交通' for r in options['taxonomy']))
    def test_exports_are_full_and_safe(self):
        result=json.loads(b''.join(self.r.export({'page_size':'1'},'json')))
        self.assertEqual(len(result),4);self.assertEqual(result[3]['raw_json']['完整字段'],'原值')
        raw=b''.join(self.r.export({},'csv'));self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        self.assertEqual(rows[0]['完整原文'],"'=SUM(1,2)")
        self.assertEqual(json.loads(rows[3]['完整源字段JSON'])['number'],3)
        self.assertEqual(json.loads(b''.join(self.r.export({'q':'不存在'},'json'))),[])
    def test_reports_persist_week_boundaries_and_html(self):
        d=self.r.generate({'title':'<script>标题</script>','period':'weekly'})['report']
        self.assertEqual([(b['start'],b['end']) for b in d['buckets']], [('2026-08-01','2026-08-02'),('2026-08-03','2026-08-09'),('2026-08-10','2026-08-16'),('2026-08-17','2026-08-23'),('2026-08-24','2026-08-30'),('2026-08-31','2026-08-31')])
        self.assertEqual(sum(b['total'] for b in d['buckets']),4)
        self.assertEqual(self.r.get('reports',d['id']),d)
        output=report_html(d).decode();self.assertNotIn('<script>',output);self.assertIn('&lt;script&gt;',output)
        self.assertTrue(all(len(x['raw_text'])<=500 for x in d['evidence']))
        for period,count in [('daily',31),('monthly',1),('custom',1)]:
            self.assertEqual(len(self.r.generate({'period':period})['report']['buckets']),count)
    def test_schedule_run_counts_zero_and_failure(self):
        schedule=self.r.schedule({'name':'测试','title':'周报','period':'weekly','filters':{'q':'不存在'}})['schedule']
        run=self.r.run(schedule['id'])['run']
        self.assertEqual(run['status'],'complete');self.assertEqual(len(run['report_ids']),6)
        self.assertEqual([x['count'] for x in run['logs'][:4]],[1,1,1,1])
        self.assertEqual(run['logs'][5]['count'],0)
        self.assertEqual(self.r.schedules()['items'][0]['last_run'],run)
        self.r.path=self.root/'absent.db'
        run=self.r.run(schedule['id'])['run'];self.assertEqual(run['status'],'failed')
        self.assertTrue(all(x['count'] is None for x in run['logs'][:4]))
        self.assertFalse(self.r.path.exists())
    def test_report_topics_filter_labels_and_evidence_provenance(self):
        report=self.r.generate({'filters':{'tag_id':'leaf','source':'wecom','channel':'真实渠道','topic':'服务','q':'SUM'},'period':'monthly'})['report']
        self.assertEqual(report['selected_tag']['path'],'服务/维修')
        self.assertEqual(report['topics'],[dict(topic='服务',total=1,analyzed_success=1,unanalyzed=0,analysis_other=0,analyzed_risk=1)])
        page=report_html(report).decode()
        for text in ('来源：企微社群','渠道：真实渠道','话题：服务','标签路径：服务/维修','关键词：SUM','日期：2026-08-01 至 2026-08-31',
                     '群名称：群','平台：平台','源文件：fixture','源行号：1','消息ID：0','不是人工最终标签'):
            self.assertIn(text,page)
        self.assertNotIn('&quot;start&quot;',page)
        whole=self.r.generate({})['report']
        self.assertEqual(sum(r['total'] for r in whole['topics']),whole['summary']['total'])
        self.assertIsNone(whole['selected_tag'])
        report['evidence'][0]['source_file']='<script>file</script>'
        self.assertNotIn('<script>',report_html(report).decode())

    def test_html_missing_original_never_falls_back_to_processed_text(self):
        report=self.r.generate({})['report']
        report['evidence']=report['evidence'][:1]
        row=report['evidence'][0]
        row.update(text='预处理正文不可冒充原文',quote_text='预处理引用不可冒充原文',raw_text=None,raw_quote='<script>原始引用</script>')
        page=report_html(report).decode()
        self.assertIn('原始正文未提供',page)
        self.assertIn('原始引用摘录（最多500字）',page)
        self.assertIn('&lt;script&gt;原始引用&lt;/script&gt;',page)
        self.assertNotIn('预处理正文不可冒充原文',page)
        self.assertNotIn('预处理引用不可冒充原文',page)
        self.assertNotIn('<script>',page)
        row.update(raw_text='',raw_quote=None)
        self.assertIn('原始引用未提供',report_html(report).decode())

    def test_count_avoids_wide_tables_and_uses_range_index(self):
        c=sqlite3.connect(self.db)
        c.executescript('CREATE INDEX messages_source_time ON messages(source,time); CREATE INDEX messages_time ON messages(time);')
        c.close();self.original=self.db.read_bytes()
        with self.r.source() as c:
            def authorize(action,table,column,database,trigger):
                if action==sqlite3.SQLITE_READ and table in ('original_records','message_catalog','events'):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize)
            self.assertEqual(self.r.count(c,filters()),4)
            self.assertEqual(self.r.summary(c,filters())['analyzed_risk'],1)
            for params,index in [({'source':'wecom'},'messages_source_time'),({},'messages_time')]:
                f=filters(params);clause,args=where(f)
                plan=' '.join(r[3] for r in c.execute('EXPLAIN QUERY PLAN SELECT count(*)'+query_from(f)+clause,args))
                self.assertIn(index,plan);self.assertIn('time>? AND time<?',plan)

    def test_page_hydrates_only_page_and_export_batches(self):
        import ninebot_listening.reporting as module
        original=module.detail_rows; sizes=[]
        def record(c,ids):
            sizes.append(len(ids));return original(c,ids)
        with patch.object(module,'detail_rows',record):
            self.assertEqual(len(self.r.messages({'page':'2','page_size':'1'})['items']),1)
            self.assertEqual(sizes,[1])
            sizes.clear()
            c=sqlite3.connect(self.db)
            c.executemany('INSERT INTO messages VALUES (?,?,?,?,?)',((f'batch{i}','2026-08-10','wecom','fixture','') for i in range(1001)))
            c.commit();c.close();self.original=self.db.read_bytes()
            self.assertEqual(len(json.loads(b''.join(self.r.export({},'json')))),1005)
            self.assertEqual(sizes,[500,500,5])

    def test_locked_fixture_is_unavailable(self):
        c=sqlite3.connect(self.db)
        c.execute('BEGIN EXCLUSIVE')
        try:
            with self.assertRaises(Unavailable):self.r.messages({})
        finally:c.rollback();c.close()

    def test_standalone_help_without_pythonpath(self):
        env=dict(os.environ);env.pop('PYTHONPATH',None)
        result=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'scripts/august_server.py'),'--help'],env=env,cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--replay-db',result.stdout)

    def test_partial_run_and_isolated_persistence(self):
        schedule=self.r.schedule({'name':'部分失败','title':'报告','period':'monthly'})['schedule']
        original=self.r.count
        def summary(c,f):
            if f['source']=='voc':raise Unavailable('合成来源失败')
            return original(c,f)
        self.r.count=summary
        result=self.r.run(schedule['id'])['run']
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['report_ids'],[])
        self.assertEqual(result['logs'][2]['count'],None)
        self.assertEqual(result['logs'][4]['count'],3)
        self.assertEqual(result['logs'][5]['stage'],'filter')
        self.assertEqual(Reporting(self.db,self.root/'state.db').schedules()['items'][0]['last_run'],result)

    def test_stream_batches_over_page_limit(self):
        c=sqlite3.connect(self.db)
        c.executemany('INSERT INTO messages VALUES (?,?,?,?,?)',((f'extra{i}','2026-08-10','wecom','synthetic','') for i in range(1001)))
        c.commit();c.close();self.original=self.db.read_bytes()
        self.assertEqual(len(json.loads(b''.join(self.r.export({},'json')))),1005)
        self.assertEqual(len(self.r.generate({})['report']['evidence']),5)
    def test_http_csrf_missing_database_and_download(self):
        spec=importlib.util.spec_from_file_location('report_server',Path(__file__).parents[1]/'scripts/august_server.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        snap=self.root/'snapshot.json';snap.write_text(json.dumps({'events':[{'id':'suggestion-3','level':'','analysis_status':'unanalysed'}]}))
        # This is a separate synthetic review store, never a real review database.
        server=ThreadingHTTPServer(('127.0.0.1',0),mod.application(snap,self.root/'synthetic-review.db',self.root))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def get(path):return urllib.request.urlopen(base+path)
        def post(path,data,token=''):
            return urllib.request.urlopen(urllib.request.Request(base+path,json.dumps(data).encode(),{'Content-Type':'application/json','X-CSRF-Token':token}))
        try:
            self.assertFalse((self.root/'synthetic-review.db').exists())
            token=json.load(get('/api/snapshot'))['csrf']
            with self.assertRaises(urllib.error.HTTPError) as error:post('/api/reports/generate',{})
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as error:
                post('/api/review',{'event_id':'suggestion-3','decision':'confirmed','level':'','note':'人工候选核验'},token)
            self.assertEqual(error.exception.code,400)
            reviewed=json.load(post('/api/review',{'event_id':'suggestion-3','decision':'confirmed','level':'R2','note':'人工明确选级'},token))
            self.assertTrue(reviewed['saved'])
            self.assertEqual(json.load(get('/api/messages?source=suggestions'))['summary']['analyzed_risk'],0)
            result=json.load(post('/api/reports/generate',{'period':'monthly'},token))
            response=get('/api/reports/'+result['id']+'/export?format=html')
            self.assertIn('attachment',response.headers['Content-Disposition']);self.assertIn(b'<!doctype html>',response.read())
            self.assertEqual(len(json.load(get('/api/export?format=json&page_size=1'))),4)
            with self.assertRaises(urllib.error.HTTPError) as error:get('/api/messages?source=voc&source=wecom')
            self.assertEqual(error.exception.code,400)
            self.db.rename(self.root/'backup.db')
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:get('/api/messages')
                self.assertEqual(error.exception.code,503)
                self.assertEqual(json.load(get('/api/snapshot'))['events'][0]['analysis_status'],'unanalysed')
            finally:(self.root/'backup.db').rename(self.db)
        finally:server.shutdown();server.server_close();thread.join()
