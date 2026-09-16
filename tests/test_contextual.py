import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from ninebot_listening import contextual,replay
from ninebot_listening.models import ModelResponse


def result(**updates):
    d=dict(topic='安全',issue='电池冒烟起火',vehicle='M3',intent='咨询',
           safety_claim=False,level='R1',summary='咨询防范措施',reason='没有实际事故反馈',confidence=0.8)
    d.update(updates);return d


class ContextualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=replay.connect(self.root/'test.db')
    def tearDown(self):self.c.close();self.tmp.cleanup()

    def test_safety_word_does_not_force_inquiry_to_r1(self):
        replay.add(self.c,'wecom','g','u','1','2026-08-21T12:00:00+08:00','怎么避免起火？')
        class Gateway:
            def analyze_json(self,request):return ModelResponse(result(),'company_private','fixture')
        replay.analyze(self.c,Gateway());replay.aggregate(self.c)
        row=self.c.execute('SELECT level,model_level,intent FROM analysis').fetchone()
        self.assertEqual(tuple(row),('R4','R1','咨询'))
        self.assertEqual(replay.stats(self.c)['simulated_notifications'],0)

    def test_safety_claim_requires_assertion(self):
        self.assertEqual(contextual.validate(result(intent='亲历反馈',safety_claim=True),replay.TOPICS),'R1')
        self.assertEqual(contextual.validate(result(intent='无法判断'),replay.TOPICS),'R3')
        for intent in ('咨询','建议','否认','玩笑'):
            self.assertEqual(contextual.validate(result(intent=intent,safety_claim=True),replay.TOPICS),'R4')

    def test_context_bounded_and_source_group_scoped(self):
        base=dt.datetime.fromisoformat('2026-08-21T12:00:00+08:00')
        for i in range(12):
            replay.add(self.c,'wecom','g','u',str(i),(base+dt.timedelta(seconds=i)).isoformat(),'测试'+str(i))
        replay.add(self.c,'wecom','other','u','a',base.isoformat(),'异群')
        replay.add(self.c,'wechat_export','g','u','a',base.isoformat(),'异来源')
        replay.add(self.c,'wecom','g','u','b',(base+dt.timedelta(minutes=6)).isoformat(),'窗口外')
        target=self.c.execute('SELECT * FROM messages WHERE text=?',('测试0',)).fetchone()
        context=contextual.context_for(self.c,target)
        self.assertEqual(len(context['nearby_messages']),8)
        self.assertTrue(all(x['text'].startswith('测试') for x in context['nearby_messages']))
        self.assertNotIn(target['id'],[x['id'] for x in context['nearby_messages']])

    def test_quote_import_separates_author_and_reference(self):
        d={'id':{'talker':'g','server_id_str':'1'},'sender':'A','create_time':1787241600,
           'kind':'quote','text':'这是别人的事吗？','quote':{'text':'我的电池冒烟了，电话13812345678'}}
        (self.root/'source.jsonl').write_text(json.dumps(d))
        replay.import_wechat(self.c,self.root,'2026-08-21','2026-08-28')
        row=self.c.execute('SELECT * FROM messages').fetchone()
        self.assertEqual(row['text'],'这是别人的事吗？')
        self.assertIn('冒烟',row['quote_text']);self.assertNotIn('13812345678',row['quote_text'])
        self.assertEqual(row['candidate'],1)

    def test_links_require_known_vehicle_and_feedback(self):
        for group,vehicle,intent in [('a','M3','亲历反馈'),('b','M3','转述'),('c','未识别','亲历反馈'),('d','M3','咨询')]:
            replay.add(self.c,'wecom',group,'u',group,'2026-08-21T12:00:00+08:00','冒烟')
            mid=replay.token(self.c,f'wecom|{group}|{group}')
            self.c.execute('''INSERT INTO analysis(message_id,topic,level,summary,status,issue,vehicle,intent,version)
                VALUES (?,?,?,?,?,?,?,?,?)''',(mid,'安全','R1' if intent!='咨询' else 'R4','合成样本','ok','电池冒烟起火',vehicle,intent,contextual.VERSION))
        data=contextual.signals(self.c)
        self.assertEqual(len(data['links']),1);self.assertEqual(data['links'][0]['groups'],2)
        self.assertIn('不足',data['growth_status'])

    def test_different_issue_and_vehicle_not_merged(self):
        for i,(issue,vehicle) in enumerate([('制动异常','M3'),('电池鼓包','M3'),('制动异常','M5')]):
            replay.add(self.c,'wecom','g','u',str(i),'2026-08-21T12:00:00+08:00','异常')
            mid=replay.token(self.c,f'wecom|g|{i}')
            self.c.execute('''INSERT INTO analysis(message_id,topic,level,summary,status,issue,vehicle,version)
              VALUES (?,?,?,?,?,?,?,?)''',(mid,'安全','R1','合成样本','ok',issue,vehicle,contextual.VERSION))
        replay.aggregate(self.c)
        self.assertEqual(replay.stats(self.c)['events'],3)


if __name__=='__main__':unittest.main()
