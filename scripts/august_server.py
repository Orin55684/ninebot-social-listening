"""Loopback-only review backend; publish solely behind authenticated HTTPS."""
import argparse
from contextlib import contextmanager
import datetime as dt
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import urlsplit, parse_qs, unquote
# Support both repository scripts/ and a standalone deployment beside src/.
for source_root in (Path(__file__).resolve().parent/'src', Path(__file__).resolve().parents[1]/'src'):
    if (source_root/'ninebot_listening').is_dir():
        sys.path.insert(0,str(source_root))
        break
from ninebot_listening.reporting import Reporting, Unavailable, report_html
from ninebot_listening.topic_reports import TopicReports, render as topic_html, export_csv as topic_csv

def application(snapshot_path,state_path,assets,replay_path=None):
    reporting=Reporting(replay_path or Path(snapshot_path).parent/'replay.db',state_path)
    topic_reports=TopicReports(reporting)
    snapshot=json.loads(Path(snapshot_path).read_text())
    csrf=secrets.token_urlsafe(32)
    @contextmanager
    def db():
        c=sqlite3.connect(state_path);c.row_factory=sqlite3.Row
        c.executescript('''CREATE TABLE IF NOT EXISTS reviews(event_id TEXT PRIMARY KEY,decision TEXT,level TEXT,note TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,event_id TEXT,decision TEXT,level TEXT,note TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS simulated_outbox(event_id TEXT PRIMARY KEY,level TEXT,status TEXT,created_at TEXT);''')
        try:
            with c:yield c
        finally:c.close()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,data,kind='application/json; charset=utf-8'):
            body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(body)
        def report_error(self,exc):
            if isinstance(exc,KeyError):return self.send(404,{'error':'Not found'})
            if isinstance(exc,(Unavailable,sqlite3.Error,OSError)):return self.send(503,{'error':'历史报表数据暂不可用，请检查本地迁移及报表存储'})
            return self.send(400,{'error':str(exc) or 'Invalid request'})
        def download(self,chunks,kind,filename):
            self.send_response(200);self.send_header('Content-Type',kind)
            self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Connection','close');self.end_headers();self.close_connection=True
            try:
                for chunk in chunks:self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
            finally:
                if hasattr(chunks,'close'):chunks.close()
        def do_GET(self):
            path=urlsplit(self.path).path
            try:
                query=parse_qs(urlsplit(self.path).query,keep_blank_values=True)
                if any(len(v)!=1 for v in query.values()):raise ValueError('筛选仅支持单值')
                params={k:v[0] for k,v in query.items()}
                if path=='/api/topic-report-plans':return self.send(200,topic_reports.plans())
                if path=='/api/topic-reports':return self.send(200,topic_reports.list())
                if path.startswith('/api/topic-reports/'):
                    parts=path.split('/');jid=parts[3]
                    if len(parts)==4:return self.send(200,topic_reports.get(jid))
                    report=topic_reports.report(jid)
                    if parts[4]=='view':return self.send(200,topic_html(report),'text/html; charset=utf-8')
                    if parts[4]=='export':
                        fmt=params.get('format','html')
                        if fmt=='csv':return self.download([topic_csv(report,params)],'text/csv; charset=utf-8','topic-filtered.csv')
                        if fmt not in ('html','json'):raise ValueError('支持HTML、CSV和JSON导出')
                        body=topic_html(report) if fmt=='html' else json.dumps(report,ensure_ascii=False).encode()
                        return self.download([body],'text/html; charset=utf-8' if fmt=='html' else 'application/json; charset=utf-8','topic-report.'+fmt)
                    raise KeyError(path)
                if path=='/api/report-options':return self.send(200,reporting.options())
                if path=='/api/messages':return self.send(200,reporting.messages(params))
                if path.startswith('/api/messages/'):return self.send(200,reporting.message(unquote(path[len('/api/messages/'):])) )
                if path=='/api/report-schedules':return self.send(200,reporting.schedules())
                if path=='/api/export':
                    fmt=params.get('format','csv');chunks=reporting.export(params,fmt)
                    return self.download(chunks,'text/csv; charset=utf-8' if fmt=='csv' else 'application/json; charset=utf-8','messages.'+fmt)
                if path.startswith('/api/reports/') and path.endswith('/export'):
                    fmt=params.get('format','html')
                    if fmt not in ('html','json'):raise ValueError('报告导出格式须为html或json')
                    report=reporting.get('reports',path.split('/')[3])
                    body=report_html(report) if fmt=='html' else json.dumps(report,ensure_ascii=False).encode()
                    return self.download([body],'text/html; charset=utf-8' if fmt=='html' else 'application/json; charset=utf-8','report.'+fmt)
            except (ValueError,TypeError,KeyError,Unavailable,sqlite3.Error,OSError) as exc:return self.report_error(exc)
            if path=='/api/snapshot':
                data=json.loads(Path(snapshot_path).read_text())
                with db() as c:
                    data['reviews']={r['event_id']:dict(r) for r in c.execute('SELECT * FROM reviews')}
                    data['history']=[dict(r) for r in c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 30')]
                    data['simulated_outbox']=[dict(r) for r in c.execute('SELECT * FROM simulated_outbox ORDER BY created_at DESC')]
                data['csrf']=csrf
                return self.send(200,data)
            files={'/assets/topic-studio.js':'topic-studio.js','/':'august.html','/assets/august.js':'august.js','/assets/august.css':'august.css','/assets/blue-v2.css':'blue-v2.css'}
            if path not in files:return self.send(404,{'error':'Not found'})
            name=files[path];content=(Path(assets)/name).read_bytes()
            kind='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
            return self.send(200,content,kind+'; charset=utf-8')
        def do_POST(self):
            path=urlsplit(self.path).path
            is_report=(path.startswith('/api/topic-report-plans/') and path.endswith('/run')) or path in ('/api/topic-report-plans','/api/topic-reports','/api/reports/generate','/api/report-schedules') or (path.startswith('/api/report-schedules/') and path.endswith('/run'))
            if path!='/api/review' and not is_report:return self.send(404,{'error':'Not found'})
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token','').encode('utf-8'),csrf.encode('utf-8')):return self.send(403,{'error':'Invalid CSRF token'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'JSON required'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=12000:raise ValueError()
                d=json.loads(self.rfile.read(n))
                if not isinstance(d,dict):raise ValueError('请求须为JSON对象')
                if is_report:
                    if path=='/api/topic-report-plans':result=topic_reports.save_plan(d)
                    elif path.startswith('/api/topic-report-plans/'):result=topic_reports.run_plan(path.split('/')[3])
                    elif path=='/api/topic-reports':result=topic_reports.start(d)
                    elif path=='/api/reports/generate':result=reporting.generate(d)
                    elif path=='/api/report-schedules':result=reporting.schedule(d)
                    else:result=reporting.run(path.split('/')[3])
                    return self.send(200,result)
                eid=d['event_id'];decision=d['decision'];level=d['level'];note=d['note']
                if eid not in {r['id'] for r in json.loads(Path(snapshot_path).read_text())['events']} or decision not in ('confirmed','rejected') or level not in ('R1','R2','R3','R4'):raise ValueError()
                if not isinstance(note,str) or not 1<=len(note.strip())<=1000:raise ValueError()
                now=dt.datetime.now(dt.timezone.utc).isoformat()
                with db() as c:
                    c.execute('INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?)',(eid,decision,level,note.strip(),now))
                    c.execute('INSERT INTO history(event_id,decision,level,note,updated_at) VALUES (?,?,?,?,?)',(eid,decision,level,note.strip(),now))
                    c.execute('DELETE FROM simulated_outbox WHERE event_id=?',(eid,))
                    if decision=='confirmed' and level in ('R1','R2'):
                        c.execute('INSERT INTO simulated_outbox VALUES (?,?,?,?)',(eid,level,'simulated_only',now))
                return self.send(200,{'saved':True,'simulated_notification':decision=='confirmed' and level in ('R1','R2'),'real_notification_sent':False})
            except (KeyError,ValueError,TypeError,UnicodeError,Unavailable,sqlite3.Error,OSError) as exc:
                if is_report:return self.report_error(exc)
                return self.send(400,{'error':'Invalid review'})
    return Handler

if __name__=='__main__':
    import os
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--state',required=True);p.add_argument('--replay-db');p.add_argument('--assets',required=True);p.add_argument('--port',type=int,default=8881);a=p.parse_args()
    ThreadingHTTPServer(('127.0.0.1',a.port),application(a.snapshot,a.state,a.assets,a.replay_db)).serve_forever()
