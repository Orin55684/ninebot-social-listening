import json
from pathlib import Path
import tempfile
import unittest
from ninebot_listening import august,replay
from ninebot_listening.reporting import Reporting
from ninebot_listening.topic_reports import TopicReports,config,valid_labels,valid_narrative,summarize_stats,render,export_csv
from ninebot_listening.models import ModelResponse

class TopicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);c=replay.connect(self.root/'replay.db');august.setup(c)
        w=august.Writer(c)
        w.add('suggestions','APP','u','1','2026-08-12T12:00:00+08:00','M3挡泥板甩泥',source_name='意见建议',channel='APP',source_file='fixture.xlsx',source_row='Sheet1!2')
        w.add('voc','g','u','2','2026-08-13T12:00:00+08:00','M1挡泥板甩泥',source_name='VOC',channel='抖音')
        c.commit();c.close();self.service=TopicReports(Reporting(self.root/'replay.db',self.root/'state.db'))
    def tearDown(self):self.tmp.cleanup()
    def label(self,id,quote='M3挡泥板甩泥'):
        return dict(id=id,relevance='related',topic='甩泥',sentiment='失望',concern='focus',title='甩泥反馈',reason='用户反馈甩泥',quote=quote)
    def test_validation_does_not_invent_entity_or_quote(self):
        rows=[dict(id='a',raw_text='M1挡泥板甩泥',group_name='')];plan={'entity_terms':['M3'],'topics':['甩泥']}
        d=self.label('a','M1挡泥板甩泥');valid_labels({'results':[d]},rows,plan);self.assertEqual(d['relevance'],'uncertain')
        with self.assertRaises(ValueError):valid_labels({'results':[self.label('a','发生起火')]},rows,plan)
        with self.assertRaises(ValueError):valid_labels({'results':[self.label('b')]},rows,plan)
    def test_unknown_citations_rejected(self):
        n={'headline':'概览','summary':'描述','findings':[dict(title='标题',text='文字',evidence_ids=['unknown'])],'actions':[],'limitations':[]}
        with self.assertRaises(ValueError):valid_narrative(n,{'known'})
    def test_end_to_end_actual_counts_export_and_cache(self):
        calls=[]
        def call(gateway,system,payload,tokens=0):
            calls.append(system)
            if '规划助手' in system:d={'entity_terms':['M3'],'keywords':['挡泥板'],'topics':['甩泥','其他']}
            elif 'section' in payload:d={'title':'建议核实','text':'建议核实用户反馈甩泥的场景。' if payload['section']=='actions' else '用户反馈甩泥，建议核实场景。'}
            elif 'verified_findings' in payload:d={'headline':'甩泥反馈值得核实','summary':'用户有甩泥反馈，仍需核实具体场景。'}
            elif 'items' in payload:
                d={'results':[self.label(r['id'],r['text']) for r in payload['items']]}
            else:
                ids=[payload['evidence'][0]['id']];d=dict(headline='甩泥值得核实',summary='用户有甩泥反馈',findings=[dict(title='甩泥',text='用户表达使用困扰',evidence_ids=ids)],actions=[dict(title='建议核实',text='建议确认场景',evidence_ids=ids)],limitations=['仅合成测试'])
            return ModelResponse(d,'company_private','fixture')
        self.service.gateway_factory=lambda:None;self.service.call=call
        cfg=config(dict(title='测试报告',request='M3挡泥板反馈',entity_terms='M3',keywords='挡泥板',filters={}))
        job=dict(id='first',config=cfg,status='queued');self.service.put(job);self.service.build(job);r=self.service.report('first')
        self.assertEqual(r['retrieved'],2);self.assertEqual(r['stats']['total'],1);self.assertEqual(r['stats']['uncertain'],1);self.assertEqual(r['stats']['negative_rate'],100)
        self.assertEqual(sum(d['total'] for d in r['stats']['days']),1);self.assertEqual(len(r['stats']['sources']),4)
        import csv,io
        exported=list(csv.DictReader(io.StringIO(export_csv(r,{'view':'review','source':'suggestions'}).decode('utf-8-sig'))))
        self.assertEqual(len(exported),1);self.assertEqual(exported[0]['完整原文'],'M3挡泥板甩泥')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(export_csv(r,{'view':'review','q':'不存在'}).decode('utf-8-sig'))))),0)
        r['title']='</script><script>alert(1)</script>';html=render(r).decode();self.assertNotIn('</script><script>alert(1)',html);self.assertIn('\\u003c/script',html)
        n=len(calls);job=dict(id='second',config=cfg,status='queued');self.service.put(job);self.service.build(job);self.assertFalse(any('你是专项舆情分析助手' in x for x in calls[n:]))
    def test_period_config_clips_august(self):
        p=self.service.save_plan(dict(title='周报',request='M3挡泥板',entity_terms='M3',keywords='挡泥板',period='weekly',filters={}))
        self.assertEqual(p['period'],'weekly');self.assertEqual(self.service.plans()['items'][0]['id'],p['id'])

    def test_period_runner_creates_six_clipped_weeks(self):
        import time
        plan=self.service.save_plan(dict(title='专项周报',request='M3挡泥板',entity_terms='M3',keywords='挡泥板',period='weekly',filters={}))
        def build(job):job.update(status='complete');self.service.put(job)
        self.service.build=build
        result=self.service.run_plan(plan['id']);ids=result['last_run']['job_ids'];self.assertEqual(len(ids),6)
        until=time.monotonic()+3
        while self.service.running and time.monotonic()<until:time.sleep(.01)
        self.assertFalse(self.service.running)
        self.assertEqual(self.service.get(ids[0])['config']['filters']['end'],'2026-08-02')
        self.assertEqual(self.service.get(ids[-1])['config']['filters']['start'],'2026-08-31')
        self.assertEqual(self.service.plans()['items'][0]['last_run']['status'],'complete')

    def test_plan_endpoint_requires_csrf_and_persists(self):
        import importlib.util,threading,urllib.request,urllib.error
        from http.server import ThreadingHTTPServer
        spec=importlib.util.spec_from_file_location('topic_server',Path(__file__).parents[1]/'scripts/august_server.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        snap=self.root/'snapshot.json';snap.write_text('{"events":[]}')
        server=ThreadingHTTPServer(('127.0.0.1',0),mod.application(snap,self.root/'state.db',self.root))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(server.server_port)
        try:
            body=json.dumps(dict(title='周期测试',request='M3挡泥板',period='weekly',filters={})).encode()
            req=urllib.request.Request(base+'/api/topic-report-plans',body,{'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,403)
            csrf=json.load(urllib.request.urlopen(base+'/api/snapshot'))['csrf'];req.add_header('X-CSRF-Token',csrf)
            result=json.load(urllib.request.urlopen(req));self.assertEqual(result['period'],'weekly')
            self.assertEqual(len(json.load(urllib.request.urlopen(base+'/api/topic-report-plans'))['items']),1)
        finally:server.shutdown();server.server_close();thread.join()

class DeploymentAvailabilityTests(unittest.TestCase):
    def test_disabled_model_creates_no_jobs(self):
        from unittest.mock import patch
        from ninebot_listening.topic_reports import TopicReports
        instance = object.__new__(TopicReports)
        with patch.dict('os.environ', {'COMPANY_MODEL_DISABLED_REASON': '公司模型网络未连接'}):
            with self.assertRaisesRegex(ValueError, '公司模型网络未连接'):
                instance.start({})
            with self.assertRaisesRegex(ValueError, '公司模型网络未连接'):
                instance.run_plan('unused')
