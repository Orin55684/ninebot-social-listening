import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import importlib.util

from ninebot_listening import replay
from ninebot_listening.models import ModelResponse


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=replay.connect(self.root/'replay.db')
    def tearDown(self):self.c.close();self.tmp.cleanup()

    def test_full_analysis_requires_ids_and_includes_non_candidates_once(self):
        replay.add(self.c,'suggestions','g','u','plain','2026-08-21T01:00:00+08:00','合成普通建议')
        self.c.execute('UPDATE messages SET candidate=0')
        mid=self.c.execute('SELECT id FROM messages').fetchone()[0]
        class Gateway:
            def analyze_json(self,r):return ModelResponse({'topic':'安全','level':'R4','summary':'合成普通建议','confidence':0.8,'issue':'其他','vehicle':'未识别','intent':'建议','safety_claim':False,'reason':'未反馈故障'},'company_private','fixture')
        with self.assertRaises(ValueError):replay.analyze(self.c,Gateway(),include_noncandidates=True)
        self.assertEqual(replay.analyze(self.c,Gateway(),selected_ids=[mid]),0)
        self.assertEqual(replay.analyze(self.c,Gateway(),selected_ids=[mid],include_noncandidates=True),1)
        self.assertEqual(replay.analyze(self.c,Gateway(),selected_ids=[mid],include_noncandidates=True),0)

    def test_dedup_scoped_identity_and_redaction(self):
        for _ in range(2):replay.add(self.c,'wecom','g','u','1','2026-08-21T01:00:00+08:00','维修请联系13812345678')
        self.assertEqual(self.c.execute('SELECT count(*) FROM messages').fetchone()[0],1)
        text=self.c.execute('SELECT text FROM messages').fetchone()[0]
        self.assertNotIn('13812345678',text)
        replay.add(self.c,'wechat_export','g','u','1','2026-08-21T01:00:00+08:00','维修')
        self.assertEqual(self.c.execute('SELECT count(distinct group_id) FROM messages').fetchone()[0],2)

    def test_official_import_excludes_private_and_end_boundary(self):
        db=self.root/'source.db';s=sqlite3.connect(db)
        s.executescript('''CREATE TABLE wb_session(staff_id,id,target_id,session_type);
          CREATE TABLE wb_message(staff_id,session_id,from_id,original_id,time,text_content,type,id);
          INSERT INTO wb_session VALUES ('s','g','target','room'),('s','p','u','ext_user');
          INSERT INTO wb_message VALUES ('s','g','u','1',1787241600,'维修','text',1),
            ('s','p','u','2',1787241600,'私聊','text',2),
            ('s','g','u','3',1787846400,'结束边界','text',3);''');s.commit();s.close()
        replay.import_wecom(self.c,db,'2026-08-21','2026-08-28')
        self.assertEqual(self.c.execute('SELECT count(*) FROM messages').fetchone()[0],1)

    def test_jsonl_duplicate_and_nontext(self):
        d={'id':{'talker':'g','server_id_str':'1'},'sender':'A','create_time':1787241600,'kind':'text','text':'维修'}
        (self.root/'input.jsonl').write_text(json.dumps(d)+'\n'+json.dumps(d)+'\n'+json.dumps(dict(d,kind='image')))
        result=replay.import_wechat(self.c,self.root,'2026-08-21','2026-08-28')
        self.assertEqual(result['imported'],1)
        result=replay.import_wechat(self.c,self.root,'2026-08-21','2026-08-28')
        self.assertEqual(result['imported'],0)

    def test_analysis_review_notification_rejection(self):
        replay.add(self.c,'wecom','g','u','1','2026-08-21T01:00:00+08:00','合成：刹车失灵')
        class Gateway:
            def analyze_json(self,r):return ModelResponse({'topic':'安全','level':'R1','summary':'合成测试待核验','confidence':0.8,'issue':'制动异常','vehicle':'M3','intent':'亲历反馈','safety_claim':True,'reason':'明确反馈故障'},'company_private','fixture')
        replay.analyze(self.c,Gateway());replay.aggregate(self.c)
        r=self.c.execute('SELECT * FROM events').fetchone();self.assertEqual(r['level'],'R1')
        self.assertEqual(replay.stats(self.c)['simulated_notifications'],0)
        replay.review(self.c,r['id'],'confirmed','R1','合成测试确认')
        replay.review(self.c,r['id'],'confirmed','R1','重复确认')
        self.assertEqual(replay.stats(self.c)['simulated_notifications'],1)
        replay.review(self.c,r['id'],'confirmed','R2','调整等级')
        replay.aggregate(self.c)
        self.assertEqual(self.c.execute('SELECT level FROM events').fetchone()[0],'R2')
        replay.review(self.c,r['id'],'rejected','R4','无关话题')
        self.assertEqual(replay.stats(self.c)['simulated_notifications'],0)
        self.assertEqual(self.c.execute('SELECT count(*) FROM feedback').fetchone()[0],4)

    def test_page_escapes_model_text_and_does_not_auto_confirm(self):
        spec=importlib.util.spec_from_file_location('demo',Path(__file__).resolve().parents[1]/'scripts/community_demo.py')
        demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
        self.c.execute('''INSERT INTO events(id,source,group_id,day,topic,level,summary,message_count,user_count)
          VALUES ('e','wecom','g','2026-08-21','安全','R1','<script>alert(1)</script>',1,1)''')
        page=demo.render(self.c,'fixture-csrf',True)
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertIn('fixture-csrf',page)
        self.assertEqual(replay.stats(self.c)['simulated_notifications'],0)

    def test_invalid_model_output_is_retryable_not_successful(self):
        replay.add(self.c,'wecom','g','u','1','2026-08-21','维修')
        class Gateway:
            def analyze_json(self,r):return ModelResponse({'topic':'invented'},'company_private','fixture')
        replay.analyze(self.c,Gateway());replay.aggregate(self.c)
        self.assertEqual(self.c.execute('SELECT status FROM analysis').fetchone()[0],'failed')
        self.assertEqual(replay.stats(self.c)['events'],0)


if __name__=='__main__':unittest.main()
