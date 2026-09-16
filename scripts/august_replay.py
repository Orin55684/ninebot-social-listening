"""Run the separately stored four-source August demonstration."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
from ninebot_listening import august,replay
from ninebot_listening.models import CompanyPrivateConfig,CompanyPrivateGateway
from community_demo import load_env

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('action',choices=['import','analyze','export','status'])
    p.add_argument('--db',type=Path,default=Path('data/august-demo/replay.db'))
    p.add_argument('--wecom',type=Path);p.add_argument('--wechat',type=Path);p.add_argument('--voc',type=Path)
    p.add_argument('--suggestions',type=Path);p.add_argument('--taxonomy',type=Path)
    p.add_argument('--refresh-originals',action='store_true',help='Re-read provided sources without changing existing analysis or review IDs')
    p.add_argument('--per-source',type=int,default=12);p.add_argument('--env',default='.env.local')
    p.add_argument('--approve-historical-demo',action='store_true');a=p.parse_args()
    c=replay.connect(a.db);august.setup(c)
    try:
        if a.action=='import':
            if not any((a.wecom,a.wechat,a.voc,a.suggestions,a.taxonomy)):raise ValueError('source or taxonomy path required')
            if a.taxonomy:print(json.dumps(august.import_taxonomy(c,a.taxonomy),ensure_ascii=False),flush=True)
            completed={r[0] for r in c.execute('SELECT source FROM import_audit')}
            official=None
            if a.wecom:
                if a.refresh_originals or 'wecom' not in completed:
                    official=august.import_wecom(c,a.wecom);print('wecom import finished',flush=True)
                else:
                    src=sqlite3.connect(a.wecom.resolve().as_uri()+'?mode=ro',uri=True)
                    official={august.normalize(r[0]) for r in src.execute("SELECT name FROM wb_session WHERE session_type='room'") if r[0]};src.close()
            if a.wechat:
                if official is None:raise ValueError('--wechat requires --wecom to retain official-group exclusion')
                if a.refresh_originals or 'wechat_export' not in completed:
                    august.import_wechat(c,a.wechat,official);print('wechat import finished',flush=True)
            if a.voc and (a.refresh_originals or 'voc' not in completed):
                august.import_voc(c,a.voc);print('voc import finished',flush=True)
            if a.suggestions:
                print(json.dumps(august.import_suggestions(c,a.suggestions),ensure_ascii=False),flush=True)
        if a.action=='analyze':
            if not a.approve_historical_demo:raise ValueError('explicit historical demo flag required')
            if not 1<=a.per_source<=100:raise ValueError('invalid budget')
            load_env(a.env);config=replace(CompanyPrivateConfig.from_env(),allow_production_data=True,timeout_seconds=120)
            prior=c.execute("SELECT value FROM settings WHERE key='august_sample'").fetchone()
            ids=json.loads(prior[0]) if prior else august.sample(c,a.per_source)
            if prior:
                represented={r[0] for r in c.execute('SELECT DISTINCT source FROM messages WHERE id IN ('+','.join('?' for _ in ids)+')',ids)} if ids else set()
                available={r[0] for r in c.execute('SELECT DISTINCT source FROM messages')}
                missing=available-represented
                if missing:
                    for mid in august.sample(c,a.per_source):
                        if c.execute('SELECT source FROM messages WHERE id=?',(mid,)).fetchone()[0] in missing:ids.append(mid)
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('august_sample',json.dumps(ids)));c.commit()
            replay.analyze(c,CompanyPrivateGateway(config),limit=len(ids),request_interval=15,selected_ids=ids)
            replay.aggregate(c)
        if a.action=='export':
            replay.aggregate(c)
            c.execute('BEGIN')
            out=a.db.parent/'snapshot.json';temp=out.with_suffix('.json.tmp');temp.write_text(json.dumps(august.export_snapshot(c),ensure_ascii=False),encoding='utf-8');os.chmod(temp,0o600);temp.replace(out)
            c.commit()
            print('snapshot exported locally',flush=True)
        print(json.dumps(replay.stats(c),ensure_ascii=False),flush=True)
    finally:c.close()
if __name__=='__main__':main()
