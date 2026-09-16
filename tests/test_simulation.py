import datetime as dt
import tempfile
import unittest
from pathlib import Path
from ninebot_listening.simulation import SimulationClock,START,END
from ninebot_listening.reporting import Reporting
import test_reporting

class ClockTests(unittest.TestCase):
    def test_clock_persistence_pause_advance_reset(self):
        with tempfile.TemporaryDirectory() as root:
            wall=[1000.0];p=Path(root)/'clock.db';c=SimulationClock(p,lambda:wall[0])
            self.assertEqual(c.now(),START.isoformat())
            wall[0]+=60;self.assertEqual(dt.datetime.fromisoformat(c.now()),START+dt.timedelta(seconds=60))
            c.update({'action':'pause'});wall[0]+=500;self.assertEqual(c.state()['speed'],0)
            paused=c.now();self.assertEqual(SimulationClock(p,lambda:wall[0]).now(),paused)
            c.update({'action':'advance','seconds':86400});self.assertEqual(dt.datetime.fromisoformat(c.now()),dt.datetime.fromisoformat(paused)+dt.timedelta(days=1))
            c.update({'action':'reset'});self.assertEqual(c.now(),START.isoformat())
            c.update({'action':'speed','speed':3600});wall[0]+=999999;self.assertEqual(c.now(),END.isoformat());self.assertEqual(c.state()['speed'],0)

class ReplayBoundaryTests(unittest.TestCase):
    setUp=test_reporting.ReportingTests.setUp
    tearDown=test_reporting.ReportingTests.tearDown
    def test_clock_boundary_applies_to_message_and_export(self):
        # Reuse realistic source fixtures, then choose a boundary between their records.
        class Clock:
            def now(self):return '2026-08-01T00:00:00+08:00'
        self.r.clock=Clock()
        result=self.r.messages({})
        self.assertEqual(result['total'],0)
        self.assertEqual(b''.join(self.r.export({},'json')),b'[]')

class RiskReplayTests(unittest.TestCase):
    def test_windows_paging_future_and_level(self):
        from ninebot_listening import replay,august
        from ninebot_listening.simulation import Simulation
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);c=replay.connect(root/'replay.db');august.setup(c);w=august.Writer(c)
            for i in range(45):
                stamp=(START-dt.timedelta(minutes=i+1)).isoformat()
                w.add('suggestions','APP','u',str(i),stamp,'测试原声',source_name='意见建议',channel='APP')
            w.add('voc','g','u','future',(START+dt.timedelta(hours=1)).isoformat(),'未来消息',source_name='VOC',channel='抖音')
            c.execute("INSERT INTO analysis(message_id,status,level) SELECT id,'ok',CASE WHEN source='voc' THEN 'R1' ELSE 'R2' END FROM messages")
            c.commit();c.close();clock=SimulationClock(root/'clock.db',lambda:1000);r=Reporting(root/'replay.db',root/'state.db',clock);sim=Simulation(r,clock)
            dashboard=sim.dashboard();self.assertEqual(dashboard['metrics'],dict(voices24=45,risks24=45,alerts24=45,alerts7=45));self.assertEqual(len(dashboard['daily']),7)
            first=sim.risks({},{});second=sim.risks({'page':'2'},{});self.assertEqual(len(first['items']),20);self.assertEqual(len(second['items']),20)
            self.assertFalse({x['id'] for x in first['items']}&{x['id'] for x in second['items']});self.assertGreater(first['items'][0]['time'],second['items'][0]['time'])
            self.assertEqual(sim.risks({'level':'R1'}, {})['total'],0)
            clock.update({'action':'advance','seconds':3600});self.assertEqual(sim.risks({'level':'R1'}, {})['total'],1)
            self.assertEqual(sim.risks({'level':'R1','as_of':START.isoformat()}, {})['total'],0)
            self.assertEqual(sim.risks({'as_of':START.isoformat()}, {})['total'],45)
            clock.update({'action':'advance','seconds':86400});self.assertEqual(sim.dashboard()['metrics']['voices24'],0)

class OfficialReportPolicyTests(unittest.TestCase):
    def test_report_scope_accepts_authorized_data_only(self):
        from ninebot_listening.models.report_gateway import OfficialReportGateway
        from ninebot_listening.models.deepseek import DeepSeekConfig
        from ninebot_listening.models import ModelRequest,DataClassification,ModelSecurityError
        transport=lambda *args:b'{"model":"deepseek-flash","choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'
        g=OfficialReportGateway(DeepSeekConfig(api_key='synthetic-key'),transport=transport)
        self.assertTrue(g.analyze_json(ModelRequest('JSON','Synthetic test',DataClassification.COMPANY_APPROVED)).payload['ok'])
        with self.assertRaises(ModelSecurityError):g.analyze_json(ModelRequest('JSON','Synthetic test',DataClassification.PRODUCTION_CHAT))

class TopicCutoffTests(unittest.TestCase):
    def test_future_originals_never_reach_model(self):
        import test_topic_reports
        from ninebot_listening.models import ModelResponse
        from ninebot_listening.topic_reports import config
        fixture=test_topic_reports.TopicTests();fixture.setUp()
        try:
            service=fixture.service
            class Clock:
                def now(self):return '2026-08-12T13:00:00+08:00'
            service.reporting.clock=Clock();service.gateway_factory=lambda:object();seen=[]
            def call(g,s,p,tokens=0):
                if '规划助手' in s:return ModelResponse({'entity_terms':['M3'],'keywords':['挡泥板'],'topics':['甩泥','其他']},'fake','fake')
                seen.extend(x['text'] for x in p['items'])
                return ModelResponse({'results':[dict(id=x['id'],relevance='unrelated',topic='其他',sentiment='中性',concern='normal',title='不相关',reason='合成测试',quote='') for x in p['items']]},'fake','fake')
            service.call=call
            cfg=config(dict(title='截止测试',request='M3挡泥板',filters={}));cfg['as_of']=Clock().now()
            job=dict(id='cutoff-test',status='queued',config=cfg);service.put(job);service.build(job)
            self.assertEqual(seen,['M3挡泥板甩泥'])
            self.assertEqual(service.report(job['id'])['retrieved'],1)
        finally:fixture.tearDown()
