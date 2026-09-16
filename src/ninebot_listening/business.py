"""Read-only XLSX ingestion and source-derived business taxonomy.

No workbook formulas or document text are executed. Word matches are review
hints, never company-confirmed classifications or inferred risk levels.
"""
from __future__ import annotations
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def xlsx_rows(path):
    """Yield (sheet name, 1-based worksheet row, values); standard-library only."""
    with ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,el in ET.iterparse(f,events=('end',)):
                    if el.tag.endswith('}si'):
                        strings.append(''.join(t.text or '' for t in el.findall('.//s:t',NS)));el.clear()
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets={r.attrib['Id']:r.attrib['Target'] for r in rels}
        book=ET.fromstring(z.read('xl/workbook.xml'))
        for sheet in book.find('s:sheets',NS):
            key=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=targets[key]
            name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            with z.open(name) as f:
                for _,el in ET.iterparse(f,events=('end',)):
                    if el.tag!='{'+NS['s']+'}row':continue
                    cells={}
                    for cell in el.findall('s:c',NS):
                        col=re.match(r'[A-Z]+',cell.attrib.get('r','A')).group()
                        index=0
                        for letter in col:index=index*26+ord(letter)-64
                        kind=cell.attrib.get('t');v=cell.find('s:v',NS)
                        value=v.text if v is not None else ''
                        if kind=='s':value=strings[int(value)] if value else ''
                        elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.findall('.//s:t',NS))
                        # Keep numeric source identifiers lexical and dates handled by caller.
                        cells[index-1]=value or ''
                    yield sheet.attrib['name'],int(el.attrib.get('r',0)),[cells.get(i,'') for i in range(max(cells,default=-1)+1)]
                    el.clear()

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS original_records(
      message_id TEXT PRIMARY KEY,raw_text TEXT,raw_quote TEXT,source_name TEXT,
      channel TEXT,group_name TEXT,platform TEXT,author TEXT,native_id TEXT,
      source_file TEXT,source_row TEXT,raw_json TEXT);
    CREATE TABLE IF NOT EXISTS business_taxonomy(
      id TEXT PRIMARY KEY,level1 TEXT,level2 TEXT,level3 TEXT,level4 TEXT,
      description TEXT,department TEXT,domain TEXT,product_lines TEXT,path TEXT);
    CREATE TABLE IF NOT EXISTS message_catalog(
      message_id TEXT PRIMARY KEY,topic TEXT,tag_id TEXT,classification_method TEXT);
    CREATE INDEX IF NOT EXISTS messages_source_time ON messages(source,time);
    CREATE INDEX IF NOT EXISTS messages_time ON messages(time,id);
    CREATE INDEX IF NOT EXISTS original_channel ON original_records(channel,message_id);
    CREATE INDEX IF NOT EXISTS catalog_topic ON message_catalog(topic,message_id);
    CREATE INDEX IF NOT EXISTS catalog_tag ON message_catalog(tag_id,message_id);
    ''')
    c.commit()

def import_taxonomy(c,path):
    headers={};tags=[]
    for sheet,row,values in xlsx_rows(path):
        if row==1:headers[sheet]=values;continue
        if not any(values):continue
        r=dict(zip(headers[sheet],values))
        required=['一级标签','二级标签','三级标签','四级标签','产品线']
        if not all(k in r for k in required):raise ValueError('业务标签缺少必要列')
        lines=[v.strip() for v in re.split('[,，、]',r['产品线']) if v.strip()]
        if not {'通用','电动'}.intersection(lines):continue
        levels=[r[k].strip() for k in required[:4]]
        if not all(levels):raise ValueError('业务标签层级为空，请核对来源表')
        identity=' > '.join(levels)
        tid=hashlib.sha256(identity.encode()).hexdigest()[:20]
        tags.append((tid,*levels,r.get('四级描述',''),r.get('主责部门',''),r.get('领域标签',''),r['产品线'],identity))
    if not tags:raise ValueError('没有通用或电动标签')
    # Replace the imported dictionary atomically, retaining deterministic IDs.
    with c:
        c.execute('DELETE FROM business_taxonomy')
        c.executemany('INSERT OR REPLACE INTO business_taxonomy VALUES (?,?,?,?,?,?,?,?,?,?)',tags)
    return {'applicable_rows':len(tags),'unique_tags':c.execute('SELECT count(*) FROM business_taxonomy').fetchone()[0]}

class Classifier:
    def __init__(self,c):
        self.tags=[dict(r) for r in c.execute('SELECT * FROM business_taxonomy')]
        leaf=collections.defaultdict(list)
        for t in self.tags:leaf[t['level4']].append(t)
        # Exact, unique leaf phrases avoid inventing a choice between ambiguous branches.
        self.phrases={k:v[0] for k,v in leaf.items() if len(v)==1 and 4<=len(k)<=18 and not any(x in k for x in ('其他','总体','（','/', '类'))}
        self.pattern=re.compile('|'.join(re.escape(k) for k in sorted(self.phrases,key=len,reverse=True))) if self.phrases else None
        # These plain expressions point to broad experience labels in the supplied dictionary.
        mappings=[('续航里程体验',r'续航'),('充电体验',r'充电'),('智能服务',r'智能服务'),('维修进度',r'维修进度|送修.{0,12}(?:多久|几天|进度)'),('蓝牙连接状态',r'蓝牙.{0,6}(?:连接|连不上|断连)'),('锁定/解锁设备',r'解锁'),('刹车体验',r'刹车|制动')]
        self.rules=[]
        for name,pattern in mappings:
            choices=leaf.get(name,[])
            if len(choices)==1:self.rules.append((re.compile(pattern),choices[0]))
    def classify(self,text):
        if self.pattern:
            match=self.pattern.search(text)
            if match:
                t=self.phrases[match.group()];return (t['level1'],t['id'],'词面规则待核实')
        for pattern,t in self.rules:
            if pattern.search(text):return (t['level1'],t['id'],'词面规则待核实')
        return ('未分类','','未分类')

def import_suggestions(c,root,writer_factory,audit_func):
    from . import replay
    writer=writer_factory(c);stats=collections.Counter();types=collections.Counter();files=[]
    paths=[Path(root)] if Path(root).is_file() else sorted(Path(root).glob('*.xlsx'))
    if not paths:raise ValueError('意见建议文件夹没有xlsx文件')
    for path in paths:
        headers={};files.append(path.name)
        for sheet,row,values in xlsx_rows(path):
            if row==1:
                headers[sheet]=values
                if not {'来源','反馈类型','反馈时间','反馈内容'}.issubset(values):raise ValueError('意见建议缺少必要列')
                continue
            if not any(values):continue
            fields=dict(zip(headers[sheet],values));stats['source_rows']+=1
            raw=fields.get('反馈内容','')
            if not raw.strip():stats['empty_text']+=1;continue
            try:
                value=fields['反馈时间']
                stamp=(dt.datetime(1899,12,30)+dt.timedelta(days=float(value))) if re.fullmatch(r'\d+(\.\d+)?',value) else dt.datetime.fromisoformat(value)
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=replay.TZ)
                stamp=stamp.astimezone(replay.TZ).isoformat()
            except (ValueError,OverflowError):stats['invalid_dates']+=1;continue
            if not '2026-08-01'<=stamp[:10]<'2026-09-01':stats['outside_window']+=1;continue
            # No feedback ID is supplied: preserve distinct worksheet rows, including duplicates.
            native=f'{path.name}|{sheet}|{row}'
            channel=fields.get('来源') or '来源未提供'
            stats['added']+=writer.add('suggestions',channel,fields.get('反馈人ID',''),native,stamp,raw,
                platform=channel,kind=fields.get('反馈类型',''),ingested=fields.get('受理时间',''),
                source_name='意见建议',channel=channel,author=fields.get('反馈人昵称',''),
                source_file=path.name,source_row=f'{sheet}!{row}',raw_fields=fields,
                force_candidate=fields.get('反馈类型')=='问题投诉')
            types[fields.get('反馈类型') or '未提供']+=1
    c.commit()
    audit_func(c,'suggestions',{**stats,'files':files,'feedback_types':dict(types),'coverage':'按反馈时间筛选2026年8月；保留意见建议和问题投诉；原渠道与处理记录按原表保存。源表无反馈唯一ID，使用文件/工作表/行号定位并幂等导入，不合并相同文字的不同反馈。'})
    return dict(stats)
