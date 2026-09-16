import json
from pathlib import Path
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile
from ninebot_listening import august,business,replay,contextual


def fixture_xlsx(path,rows):
    def letter(i):
        result=''
        while i:i,r=divmod(i-1,26);result=chr(65+r)+result
        return result
    with ZipFile(path,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="反馈" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        body=''.join('<row r="'+str(i)+'">'+''.join(f'<c r="{letter(j)}{i}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' for j,v in enumerate(row,1))+'</row>' for i,row in enumerate(rows,1))
        z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+body+'</sheetData></worksheet>')

class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=replay.connect(self.root/'test.db');august.setup(self.c)
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def test_taxonomy_selects_common_and_electric_mixed_only(self):
        p=self.root/'tags.xlsx'
        fixture_xlsx(p,[['一级标签','二级标签','三级标签','四级标签','四级描述','标签合并','主责部门','领域标签','产品线'],
            ['产品','综合体验','骑行体验','续航里程体验','源描述','','部门A','体验','通用'],
            ['APP','连接','蓝牙','蓝牙连接状态','','','部门B','智能','电动 ,短交通'],
            ['其他','X','X','非适用','','','','','SPS'],
            ['其他','Y','Y','非适用2','','','','','短交通']])
        result=august.import_taxonomy(self.c,p)
        self.assertEqual(result['unique_tags'],2)
        tag=business.Classifier(self.c).classify('续航最近变短')
        self.assertEqual(tag[0],'产品');self.assertEqual(tag[2],'词面规则待核实')
        self.assertEqual(business.Classifier(self.c).classify('今天天气不错'),('未分类','','未分类'))
    def test_suggestions_preserve_originals_dates_types_and_idempotence(self):
        p=self.root/'suggestions.xlsx'
        raw='  <真实文字>电话13800138000 '+('长文字'*700)+'  '
        headers=['来源','反馈类型','反馈时间','反馈内容','反馈人ID','反馈人昵称','状态','处理内容']
        duplicate=['九号出行APP','问题投诉','2026-08-31 23:59:59',raw,'user','昵称','已处理','服务答复']
        fixture_xlsx(p,[headers,duplicate,duplicate,['九号出行APP','意见建议','2026-09-01 00:00:00','不纳入','u','n','',''],['九号出行APP','意见建议','2026-08-01 00:00:00','解锁建议','u','n','','']])
        august.import_suggestions(self.c,p);august.import_suggestions(self.c,p)
        self.assertEqual(self.c.execute('SELECT count(*) FROM messages').fetchone()[0],3)
        r=self.c.execute('SELECT * FROM original_records WHERE raw_text=?',(raw,)).fetchone()
        self.assertIsNotNone(r);self.assertEqual(r['channel'],'九号出行APP');self.assertEqual(r['native_id'],'')
        self.assertEqual(json.loads(r['raw_json'])['处理内容'],'服务答复')
        self.assertLessEqual(len(self.c.execute('SELECT text FROM messages WHERE id=?',(r['message_id'],)).fetchone()[0]),1500)
        self.assertNotEqual(self.c.execute('SELECT text FROM messages WHERE id=?',(r['message_id'],)).fetchone()[0],raw)
        snapshot=august.export_snapshot(self.c)
        self.assertEqual(len(snapshot['events']),3)
        self.assertTrue(all(e['level']=='' and e['analysis_status']=='unanalysed' for e in snapshot['events']))
        self.assertTrue(any(e['evidence'][0]['raw_text']==raw for e in snapshot['events']))
        self.assertEqual(contextual.context_for(self.c,self.c.execute('SELECT * FROM messages LIMIT 1').fetchone())['nearby_messages'],[])
    def test_reimport_backfills_same_message_identity(self):
        w=august.Writer(self.c)
        w.add('wecom','group','user','native','2026-08-01T12:00:00+08:00','初始原文')
        mid=self.c.execute('SELECT id FROM messages').fetchone()[0]
        self.c.execute('DELETE FROM original_records');self.c.commit()
        self.assertEqual(w.add('wecom','group','user','native','2026-08-01T12:00:00+08:00','初始原文',group_name='真实群名',channel='企业微信'),0)
        self.assertEqual(self.c.execute('SELECT id FROM messages').fetchone()[0],mid)
        self.assertEqual(self.c.execute('SELECT group_name FROM original_records').fetchone()[0],'真实群名')
