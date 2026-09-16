import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from ninebot_listening import august,replay,contextual

class AugustTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=replay.connect(self.root/'r.db');august.setup(self.c)
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def test_voc_filter_no_keyword_gate_and_item_identity(self):
        cols=['ID','整体情感','研判状态','舆情状态','数据来源','发布时间','正文','标题','账号','帖子类型','入库时间']
        rows=[]
        for i,status in enumerate(['未删除','无须处理','无需处理','已删除','']):
            rows.append(dict(zip(cols,[str(i),'负面','已研判',status,'抖音','2026-08-02 12:00:00','体验不佳','--','user','评论','2026-08-03 00:00:00'])))
        rows.append({**rows[0],'ID':'5','研判状态':'未研判'})
        rows.append({**rows[0],'ID':'6','数据来源':'微博'})
        path=self.root/'voc.csv'
        with path.open('w',encoding='gb18030',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
        august.import_voc(self.c,path);august.import_voc(self.c,path)
        result=self.c.execute('SELECT * FROM messages').fetchall()
        self.assertEqual(len(result),2);self.assertTrue(all(r['candidate']==1 for r in result));self.assertNotEqual(result[0]['group_id'],result[1]['group_id'])
        self.assertEqual(contextual.context_for(self.c,result[0])['nearby_messages'],[])
    def test_unknown_authors_are_not_merged(self):
        w=august.Writer(self.c)
        for i in range(2):w.add('voc','g','',str(i),'2026-08-01T12:00:00+08:00','消息')
        self.assertEqual(self.c.execute('SELECT count(distinct user_id) FROM messages').fetchone()[0],2)
    def test_md_layouts(self):
        p=self.root/'a.md';p.write_text('# 群\n### 2026-08-01 12:00:00 / A\n充电异常\n### 2026-08-01 12:01:00 / B\n好的\n')
        self.assertEqual(len(list(august.md_messages(p))),2)
        p.write_text('# 聊天记录: 群\n- [2026-08-01 12:00] A: 充电异常\n- [2026-08-01 12:01] B: 好的\n')
        self.assertEqual(len(list(august.md_messages(p))),2)
    def test_snapshot_has_no_unanalyzed_raw_text(self):
        august.Writer(self.c).add('wecom','g','u','1','2026-08-01T00:00:00+08:00','不应出现在导出中的消息')
        d=august.export_snapshot(self.c)
        self.assertNotIn('不应出现在导出中的消息',json.dumps(d,ensure_ascii=False));self.assertEqual(d['events'],[])

class ReviewServerTests(unittest.TestCase):
    def test_review_persistence_csrf_and_simulation(self):
        spec=importlib.util.spec_from_file_location('review_server',Path(__file__).parents[1]/'scripts/august_server.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);snap=root/'snapshot.json';snap.write_text(json.dumps({'events':[{'id':'synthetic'}]}))
            server=ThreadingHTTPServer(('127.0.0.1',0),mod.application(snap,root/'state.db',root));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                d=json.load(urllib.request.urlopen(base+'/api/snapshot'))
                body=json.dumps({'event_id':'synthetic','decision':'confirmed','level':'R1','note':'合成测试'}).encode()
                req=urllib.request.Request(base+'/api/review',body,{'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                self.assertEqual(err.exception.code,403)
                req.add_header('X-CSRF-Token',d['csrf']);result=json.load(urllib.request.urlopen(req))
                self.assertTrue(result['simulated_notification']);self.assertFalse(result['real_notification_sent'])
                latest=json.load(urllib.request.urlopen(base+'/api/snapshot'));self.assertEqual(latest['reviews']['synthetic']['decision'],'confirmed')
                self.assertEqual(latest['simulated_outbox'][0]['status'],'simulated_only')
                rejected=json.dumps({'event_id':'synthetic','decision':'rejected','level':'R4','note':'合成驳回测试'}).encode()
                urllib.request.urlopen(urllib.request.Request(base+'/api/review',rejected,{'Content-Type':'application/json','X-CSRF-Token':d['csrf']})).close()
                self.assertEqual(json.load(urllib.request.urlopen(base+'/api/snapshot'))['simulated_outbox'],[])
                for path in ['/snapshot.json','/../snapshot.json','/.env']:
                    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(base+path)
                    self.assertEqual(err.exception.code,404)
            finally:server.shutdown();server.server_close();thread.join()
