"""Small local replay and review application; no real notification transport."""
from __future__ import annotations
import argparse
from dataclasses import replace
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs

from ninebot_listening import replay
from ninebot_listening import contextual
from ninebot_listening.models import CompanyPrivateConfig, CompanyPrivateGateway


def load_env(path):
    # Parse literal values without executing shell substitutions or commands.
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        key,sep,value=line.partition('=')
        if sep and key.strip().startswith('COMPANY_MODEL_'):
            os.environ[key.strip()]=value.strip().strip('\"\'')


def render(c, csrf='', active=False):
    esc=lambda v:html.escape(str(v),quote=True)
    counts=replay.stats(c)
    signals=contextual.signals(c)
    cards=[]
    for row in c.execute('SELECT * FROM events ORDER BY level,day,id'):
        r=dict(row)
        evidence=c.execute('''SELECT m.time,m.text,m.quote_text,a.intent,a.reason,a.confidence,a.context_json
            FROM evidence e JOIN messages m ON e.message_id=m.id JOIN analysis a ON a.message_id=m.id
            WHERE e.event_id=? ORDER BY m.time LIMIT 5''',(r['id'],)).fetchall()
        quotes=''
        for x in evidence:
            ctx=json.loads(x['context_json']).get('nearby_messages',[])
            context_lines=''.join('<li>'+esc(y['time'])+' · 用户 '+esc(y['user_id'][:6])+'：'+esc(y['text'])+'</li>' for y in ctx)
            quote='<blockquote>引用原话：'+esc(x['quote_text'])+'</blockquote>' if x['quote_text'] else ''
            quotes+='<li>'+esc(x['time'])+' · '+esc(x['text'])+quote+'<p>表达类型：'+esc(x['intent'])+' · 模型自评置信度：'+esc(x['confidence'])+'</p><p>依据：'+esc(x['reason'])+'</p><details><summary>本次分析所用上下文（'+str(len(ctx))+' 条）</summary><ul>'+context_lines+'</ul></details></li>'
        options=''.join(f'<option {"selected" if level==r["level"] else ""}>{level}</option>' for level in replay.LEVELS)
        form=(f'''<form method="post" action="/review"><input type="hidden" name="csrf" value="{csrf}">
          <input type="hidden" name="event" value="{r['id']}"><select name="level">{options}</select>
          <input name="note" maxlength="1000" placeholder="核验结论或驳回原因" required>
          <button name="decision" value="confirmed">确认事件</button>
          <button class="secondary" name="decision" value="rejected">驳回</button></form>''' if active else '')
        cards.append(f'''<article><small>{esc(r['source'])} · 群 {esc(r['group_id'][:8])} · {esc(r['day'])}</small>
          <h2>{esc(r['level'])} · {esc(r['topic'])}</h2><p>{esc(r['issue'])} · 车型 {esc(r['vehicle'])}</p><p>{esc(r['summary'])}</p>
          <p>{r['message_count']} 条依据 · {r['user_count']} 位群内匿名用户 · 状态 {esc(r['review'])}</p>
          <details><summary>查看脱敏证据（最多 5 条）</summary><ul>{quotes}</ul></details>{form}</article>''')
    daily=''.join(f'<tr><td>{esc(r[0])}</td><td>{r[1]}</td><td>{r[2]}</td></tr>' for r in
        c.execute("SELECT day,count(*),sum(review='confirmed') FROM events GROUP BY day ORDER BY day"))
    ok=sum(r['n'] for r in counts['analysis'] if r['status']=='ok')
    failed=sum(r['n'] for r in counts['analysis'] if r['status']=='failed')
    sources=' · '.join(f"{esc(r['source'])}：{r['messages']} 条 / {r['groups']} 群 / {r['candidates']} 条规则候选" for r in counts['sources'])
    links=''.join('<li>'+esc(x['vehicle'])+' · '+esc(x['issue'])+'：'+str(x['groups'])+' 个来源内群标识 / '+str(x['messages'])+' 条反馈</li>' for x in signals['links'])
    coverage=''.join('<tr>'+''.join('<td>'+esc(x[k])+'</td>' for k in ('day','source','imported','candidates','analyzed','feedback'))+'</tr>' for x in signals['daily'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>九号社群观察 · 历史回放</title><style>
    body{{font:16px/1.65 system-ui,sans-serif;background:#f2f4f7;color:#182532;max-width:1040px;margin:40px auto;padding:0 24px}}
    header{{background:#142f39;color:white;padding:32px;border-radius:20px}}h1{{margin:8px 0;font-size:32px}}
    article,section{{background:white;border:1px solid #dbe1e8;padding:24px;border-radius:16px;margin:18px 0}}
    small{{color:#5a6977}}header small{{color:#99e3d0}}h2{{font-size:21px}}form{{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}}
    input,select,button{{font:inherit;padding:10px;border:1px solid #bbc7cc;border-radius:8px}}input[name=note]{{flex:1;min-width:160px}}
    button{{background:#176453;color:white;cursor:pointer}}.secondary{{background:white;color:#334}}li{{margin:12px 0;overflow-wrap:anywhere}}
    td,th{{padding:8px 26px 8px 0;text-align:left}}.metrics{{font-size:20px;font-weight:600}}
    </style><header><small>NINEBOT / COMMUNITY LISTENING</small><h1>社群观察 · 历史回放</h1>
    <p>比赛演示 V2 · 上下文核验 · 引用区分 · 通知仅模拟</p></header>
    <section><p class="metrics">{ok} 条已分析 · {counts['events']} 个候选 · {counts['simulated_notifications']} 条模拟通知</p>
    <p>{sources}</p><p>分析失败：{failed} 条。抽样优先覆盖风险关键词，不能据此推算整体投诉率或模型召回率。</p>
    <p>脱敏为规则初筛，证据仍可能包含间接身份信息，仅供本机内部评审。微信来源尚未逐群核实民间/官方归属。
    候选按同来源、同群、同日、主题、具体问题和车型归并，仍需核实是否同一事件。安全关键词只提高处理优先级，不直接定为 R1。
    上下文为已导入样本内前后各 5 分钟、最多 8 条；这是历史回看，不是实时发现时效测试。</p></section>
    <section><h2>疑似跨群同类问题</h2><ul>{links or '<li>当前已分析样本中暂无满足条件的关联。</li>'}</ul>
    <p>仅关联明确车型、同一具体问题、亲历或转述反馈。来源内群标识尚未跨来源映射，数量不等于真实独立群数；相似反馈不代表同一事件或传播。</p></section>
    <section><h2>样本时间分布与分析覆盖</h2><table><tr><th>日期</th><th>来源</th><th>导入</th><th>关键词候选</th><th>已分析</th><th>R1–R3</th></tr>{coverage}</table>
    <p>{esc(signals['growth_status'])}</p></section>
    <section><h2>历史每日候选概览</h2><table><tr><th>日期</th><th>候选数</th><th>已确认</th></tr>{daily}</table>
    <p>确认 R1/R2 后生成本地模拟通知，驳回会撤销该候选的模拟通知。页面刷新可查看最新计数。</p></section>
    {''.join(cards) or '<section>尚无候选；请先执行历史导入和模型分析。</section>'}</html>'''


def serve(db, port):
    csrf=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,body):
            self.send_response(code);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('X-Frame-Options','DENY')
            self.end_headers();self.wfile.write(body.encode())
        def do_GET(self):
            if self.path!='/':return self.reply(404,'Not found')
            c=replay.connect(db)
            try:self.reply(200,render(c,csrf,True))
            finally:c.close()
        def do_POST(self):
            if self.path!='/review':return self.reply(404,'Not found')
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16000:raise ValueError('size')
                params=parse_qs(self.rfile.read(size).decode())
                if not secrets.compare_digest(params.get('csrf',[''])[0],csrf):return self.reply(403,'Forbidden')
                c=replay.connect(db)
                try:replay.review(c,params['event'][0],params['decision'][0],params['level'][0],params['note'][0])
                finally:c.close()
            except (ValueError,KeyError,UnicodeError):return self.reply(400,'Invalid request')
            self.send_response(303);self.send_header('Location','/');self.end_headers()
    server=HTTPServer(('127.0.0.1',port),Handler)
    print(f'Local demo: http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['import','analyze','report','serve','status'])
    p.add_argument('--db',type=Path,default=Path('data/demo-v2/replay.db'))
    p.add_argument('--wecom',type=Path);p.add_argument('--wechat',type=Path)
    p.add_argument('--start',default='2026-08-21');p.add_argument('--end',default='2026-08-28')
    p.add_argument('--env',default='.env.local');p.add_argument('--limit',type=int,default=40)
    p.add_argument('--approve-historical-demo',action='store_true')
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--request-interval',type=float,default=12)
    a=p.parse_args()
    if a.action=='serve':return serve(a.db,a.port)
    c=replay.connect(a.db)
    try:
        if a.action=='import':
            window=json.dumps([a.start,a.end])
            prior=c.execute("SELECT value FROM settings WHERE key='window'").fetchone()
            if prior and prior[0]!=window:raise ValueError('Use a separate demo database for another window')
            # Re-running a completed import is idempotent rather than filling a new sample.
            if not prior:
                if not a.wecom or not a.wechat:raise ValueError('Both source paths are required')
                replay.import_wecom(c,a.wecom,a.start,a.end)
                replay.import_wechat(c,a.wechat,a.start,a.end)
                c.execute('INSERT INTO settings VALUES (?,?)',('window',window));c.commit()
        elif a.action=='analyze':
            if not a.approve_historical_demo:raise ValueError('Historical demo approval flag is required')
            load_env(a.env)
            # Invocation-scoped permission for the explicitly authorized historical demo.
            # The persisted production environment flag remains false.
            config=replace(CompanyPrivateConfig.from_env(),allow_production_data=True,timeout_seconds=30)
            if a.limit<1 or not 0<=a.request_interval<=60:raise ValueError('Invalid request budget')
            replay.analyze(c,CompanyPrivateGateway(config),limit=a.limit,request_interval=a.request_interval)
            replay.aggregate(c)
        elif a.action=='report':
            a.db.with_suffix('.html').write_text(render(c),encoding='utf-8')
        print(json.dumps(replay.stats(c),ensure_ascii=False))
    finally:c.close()


if __name__=='__main__':main()
