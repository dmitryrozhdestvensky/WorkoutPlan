#!/usr/bin/env python3
"""Safe staged importer for the existing workoutplan.fitness schema (PostgreSQL 17)."""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PLATFORMS = {'vk':'vk','ok':'ok','д Zen':'dzen','дзен':'dzen','dzen':'dzen','telegram':'telegram','instagram':'instagram','tiktok':'tiktok','tenchat':'tenchat'}
MASTER_SOCIAL = {'VK':'vk','OK':'ok','Дзен':'dzen','Telegram':'telegram','Instagram':'instagram','TikTok':'tiktok','TenChat':'tenchat'}
SPIRIT_SOCIAL = {'vk':'vk','ok':'ok','dzen':'dzen','telegram':'telegram','instagram':'instagram','tiktok':'tiktok','tenchat':'tenchat'}
MASTER_HEADERS = ['Тренер / имя','Город','Специализация','VK','OK','Дзен','Telegram','Instagram','TikTok','TenChat','Сайт / мультиссылка','URL источника','Статус проверки','Примечание','Дата сбора','Источник — название','Страница тренера в источнике','Дополнительные источники — URL','Клубы RegymSport','Компетенции RegymSport','Образование RegymSport']

def clean(x):
    if x is None: return None
    s = str(x).strip()
    return s or None

def make_jsonable(x):
    if isinstance(x, (date, datetime)): return x.isoformat()
    return str(x) if x is not None and not isinstance(x,(int,float,bool,str,list,dict)) else x

def timestamp(x):
    s = clean(x)
    if not s: return None
    if isinstance(x,datetime): return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    if isinstance(x,date): return datetime(x.year,x.month,x.day,tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(s.replace('Z','+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError: return None

def url(x):
    s = clean(x)
    if not s: return None
    if s.startswith(('https://','http://')) and urlparse(s).netloc: return s.rstrip('/')
    return None

def normalize_name(x):
    return ' '.join(re.findall(r'[^\W_]+', (x or '').casefold(), re.UNICODE)) or None

def social_links(row, cols):
    for col, platform in cols.items():
        raw = clean(row.get(col))
        if not raw: continue
        for candidate in re.split(r'\s*[|;\n]\s*',raw):
            link = url(candidate)
            if link: yield platform, link

def master_rows(path):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError('Install openpyxl: python -m pip install openpyxl') from exc
    wb = load_workbook(path,read_only=True,data_only=True)
    try:
        if 'Тренеры' not in wb.sheetnames: raise RuntimeError('Sheet "Тренеры" not found')
        it = wb['Тренеры'].iter_rows(values_only=True)
        headers = [clean(x) for x in next(it)]
        if not {'Тренер / имя','Город'}.issubset(set(headers)):
            raise RuntimeError('Unexpected workbook headers; inspect first row of "Тренеры"')
        for nr, cells in enumerate(it,start=2):
            row = {key:make_jsonable(cells[i]) for i,key in enumerate(headers) if key and i<len(cells)}
            name = clean(row.get('Тренер / имя'))
            if not name: continue
            # A workbook row is LEGACY CONSOLIDATED evidence, not an independent source page.
            # DO NOT use category URL as individual's source profile URL.
            yield {'source_code':'legacy_master','source_name':'Legacy Excel master (consolidated)',
                   'source_profile_id':f'master:row:{nr}','profile_url':None,
                   'raw_name':name,'normalized_name':normalize_name(name),
                   'city':clean(row.get('Город')),'clubs':clean(row.get('Клубы RegymSport')),
                   'specialty':clean(row.get('Специализация')),
                   'biography':None,'collected_at':timestamp(row.get('Дата сбора')),
                   'raw_data':{'origin':'legacy_master','master_sheet':'Тренеры','master_row':nr,'fields':row},
                   'socials':list(social_links(row,MASTER_SOCIAL))}
    finally: wb.close()

def spirit_csv_rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        sample=f.read(2048); f.seek(0)
        dialect = csv.excel
        dialect.delimiter = ';' if sample.count(';')>sample.count(',') else ','
        reader=csv.DictReader(f,dialect=dialect)
        if not {'name','source_profile_url'}.issubset(set(reader.fieldnames or [])):
            raise RuntimeError('Unexpected SpiritFitness CSV headers')
        for n,row in enumerate(reader,start=2):
            if clean(row.get('status')) not in (None,'collected'): continue
            name = clean(row.get('name')); link=url(row.get('source_profile_url'))
            if not name or not link or 'Страница не найдена' in name: continue
            yield {'source_code':'spiritfitness','source_name':'Spirit Fitness',
                   'profile_url':link,'source_profile_id':None,
                   'raw_name':clean(row.get('raw_name')) or name,
                   'normalized_name':clean(row.get('normalized_name')) or normalize_name(name),
                   'city':clean(row.get('city')),'clubs':clean(row.get('clubs')),
                   'specialty':clean(row.get('specialty')) or clean(row.get('role')),
                   'biography':None,'collected_at':timestamp(row.get('collected_at')),
                   'raw_data':{'origin':'spiritfitness_csv','csv_row':n,'fields':row},
                   'socials':list(social_links(row,SPIRIT_SOCIAL))}

DDX_REQUIRED = {'name', 'source_profile_url', 'source'}
DDX_SOCIAL = {'vk':'vk','ok':'ok','dzen':'dzen','telegram':'telegram',
              'instagram':'instagram','tiktok':'tiktok','tenchat':'tenchat'}

def ddx_csv_rows(path):
    # The DDX collector exports a UTF-8-BOM semicolon-separated file.
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        headers = set(reader.fieldnames or [])
        if not DDX_REQUIRED.issubset(headers):
            raise RuntimeError('Unexpected DDX CSV headers. Missing: ' + ', '.join(sorted(DDX_REQUIRED - headers)))
        for csv_line, row in enumerate(reader, start=2):
            name = clean(row.get('name'))
            profile_link = url(row.get('source_profile_url'))
            status = (clean(row.get('status')) or '').casefold()
            # Avoid promoting error pages or rows without a personal source URL.
            if not name or not profile_link or 'страница не найдена' in name.casefold():
                continue
            if status in ('error', 'failed', 'invalid', 'invalid_page', 'not_found', 'queued'):
                continue
            if not (urlparse(profile_link).hostname or '').lower().endswith('ddxfitness.ru'):
                # An unknown source profile URL must be inspected instead of silently importing.
                raise RuntimeError(f'DDX CSV line {csv_line}: unexpected source profile domain: {profile_link}')
            yield {
                'source_code': 'ddxfitness', 'source_name': 'DDX Fitness',
                'profile_url': profile_link, 'source_profile_id': None,
                'raw_name': name, 'normalized_name': normalize_name(name),
                'city': clean(row.get('city')), 'clubs': clean(row.get('clubs')),
                'specialty': clean(row.get('specialty')) or clean(row.get('role')),
                'biography': None,
                'collected_at': timestamp(row.get('date_collected')),
                'raw_data': {
                    'origin': 'ddxfitness_csv', 'csv_row': csv_line,
                    'fields': row,
                },
                'socials': list(social_links(row, DDX_SOCIAL)),
            }

REGYM_REQUIRED = {'name', 'source_profile_url', 'source'}
REGYM_SOCIAL = {'vk':'vk','ok':'ok','dzen':'dzen','telegram':'telegram',
                'instagram':'instagram','tiktok':'tiktok','tenchat':'tenchat'}

def regym_csv_rows(path):
    # RegymSport collector exports semicolon-delimited UTF-8 CSV.
    # Keep every original field in JSONB, including education and skills.
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        headers = set(reader.fieldnames or [])
        missing = REGYM_REQUIRED - headers
        if missing:
            raise RuntimeError('Unexpected RegymSport CSV headers. Missing: ' + ', '.join(sorted(missing)))
        for csv_line, row in enumerate(reader, start=2):
            name = clean(row.get('name'))
            profile_link = url(row.get('source_profile_url'))
            status = (clean(row.get('status')) or '').casefold()
            if not name or not profile_link or 'страница не найдена' in name.casefold():
                continue
            if status in ('error','failed','invalid','invalid_page','not_found','queued'):
                continue
            host = (urlparse(profile_link).hostname or '').lower()
            if host != 'regymsport.ru' and not host.endswith('.regymsport.ru'):
                raise RuntimeError(f'RegymSport CSV line {csv_line}: unexpected profile URL domain: {profile_link}')
            yield {
                'source_code':'regymsport', 'source_name':'RegymSport',
                'profile_url':profile_link, 'source_profile_id':None,
                'raw_name':name, 'normalized_name':normalize_name(name),
                'city':clean(row.get('city')), 'clubs':clean(row.get('clubs')),
                'specialty':clean(row.get('specialty')),
                'biography':None,
                'collected_at':timestamp(row.get('date_collected')),
                'raw_data':{'origin':'regymsport_csv','csv_row':csv_line,'fields':row},
                'socials':list(social_links(row, REGYM_SOCIAL)),
            }

def spirit_sqlite_rows(path):
    db=sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        for r in db.execute("SELECT * FROM source_profiles WHERE status='collected'"):
            row=dict(r); name=clean(row.get('name')); link=url(row.get('url'))
            if not name or not link or 'Страница не найдена' in name: continue
            try: socials=json.loads(row.get('socials_json') or '{}')
            except (ValueError,TypeError): socials={}
            if not isinstance(socials,dict): socials={}
            items=[]
            for k,v in socials.items():
                platform=SPIRIT_SOCIAL.get(str(k).lower())
                if not platform: continue
                vals=v if isinstance(v,list) else [v]
                for entry in vals:
                    link_social=url(entry)
                    if link_social: items.append((platform,link_social))
            yield {'source_code':'spiritfitness','source_name':'Spirit Fitness',
                   'profile_url':link,'source_profile_id':None,
                   'raw_name':clean(row.get('raw_name')) or name,
                   'normalized_name':clean(row.get('normalized_name')) or normalize_name(name),
                   'city':clean(row.get('city')),'clubs':clean(row.get('clubs')),
                   'specialty':clean(row.get('specialty')) or clean(row.get('role')),
                   'biography':None,'collected_at':timestamp(row.get('collected_at')),
                   'raw_data':{'origin':'spiritfitness_sqlite','fields':row},'socials':items}
    finally: db.close()


WORLDCLASS_REQUIRED = {'name', 'surname', 'clubs', 'club_address', 'source_profile_url'}
WORLDCLASS_SOCIAL = {'vk':'vk','ok':'ok','dzen':'dzen','telegram':'telegram',
                     'instagram':'instagram','tiktok':'tiktok','tenchat':'tenchat'}

def worldclass_csv_rows(path, raw_sqlite=None):
    """Import API-enriched V1.7 CSV, optionally join original API JSON from SQLite."""
    api_db = None
    if raw_sqlite:
        db_path=Path(raw_sqlite)
        if not db_path.is_file():
            raise RuntimeError('WorldClass raw SQLite not found: '+str(db_path))
        api_db=sqlite3.connect('file:'+db_path.resolve().as_posix()+'?mode=ro',uri=True)
        exists=api_db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_records'").fetchone()
        if not exists:
            api_db.close()
            raise RuntimeError('The SQLite does not contain api_records; use V1.7.1 output or omit --raw-sqlite')
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            reader=csv.DictReader(f, delimiter=';')
            missing=WORLDCLASS_REQUIRED-set(reader.fieldnames or ())
            if missing:
                raise RuntimeError('WorldClass CSV missing: '+', '.join(sorted(missing)))
            seen=set()
            for lineno,row in enumerate(reader,start=2):
                link=url(row.get('source_profile_url'))
                name=clean(row.get('name'))
                if not link or not name:
                    raise RuntimeError(f'WorldClass CSV line {lineno}: missing name or URL')
                parsed=urlparse(link)
                if parsed.hostname not in ('www.worldclass.ru','worldclass.ru') or not re.fullmatch(r'/trainers/\d+',parsed.path):
                    raise RuntimeError(f'WorldClass CSV line {lineno}: invalid trainer URL: {link}')
                if link in seen:
                    raise RuntimeError(f'WorldClass CSV duplicate trainer URL on line {lineno}: {link}')
                seen.add(link)
                api_json=None
                if api_db:
                    raw=api_db.execute('SELECT raw_json FROM api_records WHERE url=?',(link+'/',)).fetchone()
                    if raw:
                        try: api_json=json.loads(raw[0])
                        except (TypeError,ValueError):raise RuntimeError(f'WorldClass invalid API JSON for {link}')
                    else:
                        raise RuntimeError(f'WorldClass API JSON not found for {link}; verify V1.7.1 API run completed')
                # Keep CSV as structured evidence and original JSON when requested.
                raw_data={'origin':'worldclass_api_v1_7_csv','csv_row':lineno,'fields':row}
                if api_json is not None:raw_data['api_record']=api_json
                yield {
                    'source_code':'worldclass','source_name':'World Class',
                    'profile_url':link,'source_profile_id':clean(row.get('source_external_id')) or parsed.path.split('/')[-1],
                    'raw_name':name,'normalized_name':normalize_name(name),
                    'city':None if (clean(row.get('city')) or '').casefold().startswith('не уточн') else clean(row.get('city')),
                    'clubs':clean(row.get('clubs')),
                    'specialty':clean(row.get('skills')) or clean(row.get('specialty')),
                    'biography':None,
                    'collected_at':timestamp(row.get('date_collected')),
                    'raw_data':raw_data,
                    'socials':list(social_links(row,WORLDCLASS_SOCIAL)),
                }
    finally:
        if api_db:api_db.close()

def pick_reader(kind,path,raw_sqlite=None):
    if kind=='master': return master_rows(path)
    if kind=='spirit_csv': return spirit_csv_rows(path)
    if kind=='spirit_sqlite': return spirit_sqlite_rows(path)
    if kind=='ddx_csv': return ddx_csv_rows(path)
    if kind=='regym_csv': return regym_csv_rows(path)
    if kind=='worldclass_csv': return worldclass_csv_rows(path,raw_sqlite)
    raise ValueError(kind)

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def db_connect(args):
    try: import psycopg
    except ImportError as exc:raise RuntimeError('Install psycopg: python -m pip install "psycopg[binary]"') from exc
    if args.password_env and os.getenv(args.password_env):
        passwd=os.getenv(args.password_env)
    else: passwd=None # libpq may use PGPASSFILE / pgpass.conf / PGPASSWORD
    return psycopg.connect(host=args.host,port=args.port,dbname=args.dbname,user=args.user,password=passwd,connect_timeout=8,options='-c statement_timeout=120000')

def inspect_schema(conn):
    must={'sources','source_profiles','profile_socials','import_runs'}
    with conn.cursor() as c:
        c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='fitness'")
        found={r[0] for r in c.fetchall()}
        missing=must-found
        if missing:raise RuntimeError('Missing fitness tables: '+', '.join(sorted(missing)))
        c.execute('SELECT current_database(), current_user')
        print('Connected:',c.fetchone())

def import_file(conn,kind,path,limit=None,raw_sqlite=None):
    from psycopg.types.json import Jsonb
    count={'read':0,'inserted':0,'updated':0,'skipped':0,'socials':0}
    hashv=sha256_file(path)
    with conn.transaction():
        with conn.cursor() as c:
            c.execute("INSERT INTO fitness.import_runs(input_path,input_sha256,status,notes) VALUES (%s,%s,'started',%s) RETURNING id",(str(Path(path).resolve()),hashv,'WebCollector PostgreSQL Importer V1.3; source snapshots remain external'))
            run_id=c.fetchone()[0]
            source_ids={}
            for row in pick_reader(kind,path,raw_sqlite):
                count['read']+=1
                if limit and count['read']>limit:
                    count['read']-=1;break
                code=row['source_code']
                if code not in source_ids:
                    c.execute('INSERT INTO fitness.sources(code,name) VALUES (%s,%s) ON CONFLICT(code) DO UPDATE SET name=excluded.name RETURNING id',(code,row['source_name']))
                    source_ids[code]=c.fetchone()[0]
                sid=source_ids[code]
                if row['profile_url']:
                    c.execute('SELECT id FROM fitness.source_profiles WHERE source_id=%s AND profile_url=%s',(sid,row['profile_url']))
                else:
                    c.execute('SELECT id FROM fitness.source_profiles WHERE source_id=%s AND source_profile_id=%s',(sid,row['source_profile_id']))
                prev=c.fetchone()
                values=(sid,row['profile_url'],row['source_profile_id'],row['raw_name'],row['normalized_name'],row['city'],row['clubs'],row['specialty'],row['biography'],Jsonb(row['raw_data']),row['collected_at'],run_id)
                if prev:
                    pid=prev[0]
                    c.execute('''UPDATE fitness.source_profiles SET raw_name=%s, normalized_name=%s,city=%s,clubs=%s,specialty=%s,biography=%s,raw_data=%s,collected_at=COALESCE(%s,collected_at),last_seen_at=now(),import_run_id=%s WHERE id=%s''',
                              (row['raw_name'],row['normalized_name'],row['city'],row['clubs'],row['specialty'],row['biography'],Jsonb(row['raw_data']),row['collected_at'],run_id,pid))
                    count['updated']+=1
                else:
                    c.execute('''INSERT INTO fitness.source_profiles(source_id,profile_url,source_profile_id,raw_name,normalized_name,city,clubs,specialty,biography,raw_data,collected_at,last_seen_at,import_run_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s) RETURNING id''',values)
                    pid=c.fetchone()[0];count['inserted']+=1
                for platform,link in sorted(set(row['socials'])):
                    c.execute('''INSERT INTO fitness.profile_socials(source_profile_id,platform,account_url,verification_status,evidence,collected_at) VALUES (%s,%s,%s,'unverified',%s,%s) ON CONFLICT (source_profile_id,platform,account_url) DO NOTHING RETURNING id''',
                              (pid,platform,link,'Imported from '+row['raw_data']['origin']+'; ownership NOT verified',row['collected_at']))
                    if c.fetchone():count['socials']+=1
            c.execute("UPDATE fitness.import_runs SET status='completed',rows_read=%s,rows_inserted=%s,rows_updated=%s,rows_skipped=%s,notes=%s,finished_at=now() WHERE id=%s",
                      (count['read'],count['inserted'],count['updated'],count['skipped'],f'Imported {kind}; {count["socials"]} new unverified social URLs',run_id))
    return count

def main():
    p=argparse.ArgumentParser(description='Import WebCollector into existing PostgreSQL workoutplan.fitness schema; never modifies public.users')
    p.add_argument('--kind',choices=['master','spirit_csv','spirit_sqlite','ddx_csv','regym_csv','worldclass_csv'],required=True)
    p.add_argument('--file',required=True)
    p.add_argument('--raw-sqlite',help='Optional WorldClass SQLite with api_records for full raw JSON evidence')
    p.add_argument('--dry-run',action='store_true',help='Inspect and count input without a DB connection')
    p.add_argument('--limit',type=int,default=None,help='First N valid rows only; for test runs')
    p.add_argument('--expected-rows',type=int,default=None,help='Require this many valid rows on full file import')
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=15432)
    p.add_argument('--dbname',default='workoutplan');p.add_argument('--user',default='workoutplan_test')
    p.add_argument('--password-env',default='PGPASSWORD')
    args=p.parse_args()
    path=Path(args.file)
    if not path.is_file():p.error('File not found: '+str(path))
    if args.kind=='master' and path.suffix.lower()!='.xlsx':p.error('master expects .xlsx')
    if args.kind in ('ddx_csv','regym_csv','worldclass_csv') and path.suffix.lower()!='.csv':p.error(args.kind + ' expects .csv')
    try:
        if args.expected_rows is not None and args.limit is None:
            n=sum(1 for _ in pick_reader(args.kind,path,args.raw_sqlite))
            if n!=args.expected_rows:raise RuntimeError(f'Expected {args.expected_rows} rows; got {n}. Import not started.')
        if args.dry_run:
            rows=0; social=0; sample=[]
            for row in pick_reader(args.kind,path,args.raw_sqlite):
                rows+=1;social+=len(row['socials'])
                if len(sample)<3:sample.append({'name':row['raw_name'],'profile_url':row['profile_url'],'source':row['source_code']})
                if args.limit and rows>=args.limit:break
            print(json.dumps({'kind':args.kind,'rows':rows,'social_links':social,'sha256':sha256_file(path),'sample':sample},ensure_ascii=False,indent=2))
        else:
            with db_connect(args) as conn:
                if conn.info.dbname != args.dbname:raise RuntimeError('Unexpected connected dbname')
                inspect_schema(conn)
                print('Importing into',args.dbname,'fitness.*, NOT public.*')
                print(json.dumps(import_file(conn,args.kind,path,args.limit,args.raw_sqlite),ensure_ascii=False,indent=2))
    except Exception as exc:
        print('ERROR:',exc,file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
