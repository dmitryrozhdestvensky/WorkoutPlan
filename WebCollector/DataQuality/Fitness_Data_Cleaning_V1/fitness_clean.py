#!/usr/bin/env python3
"""Fitness catalogue / DaData quality audit. NO PostgreSQL writes."""
import argparse, collections, csv, datetime as dt, hashlib, json, os, re, sqlite3, sys, time, unicodedata
from pathlib import Path

API='https://cleaner.dadata.ru/api/v1/clean/name'
FIELDS=['trainer_id','display_name','normalized_name','city','profile_count','source_codes','source_names','issue_codes','dadata_result','dadata_qc','dadata_surname','dadata_name','dadata_patronymic','dadata_cached_at']

def tidy(s):return ' '.join(unicodedata.normalize('NFKC',str(s or '')).split())
def key(s):return tidy(s).casefold().replace('ё','е')
def dump(path, obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def write_csv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';',extrasaction='ignore');w.writeheader();w.writerows(rows)

def retrieve(args):
    import psycopg
    with psycopg.connect(host=args.host,port=args.port,user=args.user,dbname=args.dbname,connect_timeout=12,options='-c statement_timeout=120000') as con:
        with con.transaction():
            with con.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                cur.execute('SELECT current_database()'); db=cur.fetchone()[0]
                if db!='workoutplan':raise RuntimeError('Подключение не к workoutplan')
                cur.execute('''SELECT t.id,t.display_name,t.normalized_name,t.city,
                        COUNT(l.source_profile_id),COALESCE(string_agg(DISTINCT s.code,', ' ORDER BY s.code),'')
                  FROM fitness.trainers t
                  LEFT JOIN fitness.trainer_profile_links l ON l.trainer_id=t.id
                  LEFT JOIN fitness.source_profiles p ON p.id=l.source_profile_id
                  LEFT JOIN fitness.sources s ON s.id=p.source_id
                  GROUP BY t.id,t.display_name,t.normalized_name,t.city ORDER BY t.id''')
                trainers=cur.fetchall()
                cur.execute('''SELECT p.id,p.raw_name,p.normalized_name,p.city,t.id,s.code
                  FROM fitness.source_profiles p
                  LEFT JOIN fitness.trainer_profile_links l ON l.source_profile_id=p.id
                  LEFT JOIN fitness.trainers t ON t.id=l.trainer_id
                  JOIN fitness.sources s ON s.id=p.source_id ORDER BY p.id''')
                profiles=cur.fetchall()
    if len(trainers)!=3897 or len(profiles)!=5652:
        raise RuntimeError(f'Количество записей изменилось: trainers={len(trainers)}, profiles={len(profiles)}; ожидается 3897/5652. Остановлено.')
    if sum(int(r[4]) for r in trainers)!=5652 or any(r[4]==0 for r in trainers) or any(r[4] is None for r in profiles):
        raise RuntimeError('Нарушена полнота привязок исходных анкет к карточкам. Остановлено.')
    return trainers,profiles

def init_cache(path):
    c=sqlite3.connect(path)
    c.execute('''CREATE TABLE IF NOT EXISTS clean_names (
      name_hash TEXT PRIMARY KEY, submitted_name TEXT NOT NULL, result_json TEXT NOT NULL,
      checked_at TEXT NOT NULL)''')
    c.commit();return c

def make_rows(trainers, profiles, cache):
    pby=collections.defaultdict(list)
    for pid,raw,norm,city,tid,src in profiles:pby[tid].append((pid,raw or '',norm or '',city or '',src))
    cached={n:(source,json.loads(payload),when) for n,source,payload,when in cache.execute('SELECT name_hash,submitted_name,result_json,checked_at FROM clean_names')}
    rows=[]; names={}; original_key_groups=collections.defaultdict(list);clean_groups=collections.defaultdict(list)
    for tid,disp,norm,city,links,sources in trainers:
        ps=pby[tid]; display=tidy(disp); norm=tidy(norm)
        # Don't silently invent canonical names from other profiles: show missing card names for review.
        issues=[]
        if not display:issues.append('empty_display_name')
        if display and len(display.split())<2:issues.append('incomplete_display_name')
        if not tidy(city):issues.append('missing_city')
        original_candidates=sorted({key(p[1]) for p in ps if p[1]})
        if len(original_candidates)>1:issues.append('conflicting_source_names')
        if display and norm and key(display)!=key(norm):issues.append('display_normalized_mismatch')
        if len(ps)!=int(links):issues.append('link_count_mismatch')
        if display:original_key_groups[key(display)].append(tid)
        namehash=hashlib.sha256(display.encode('utf-8')).hexdigest() if display else ''
        d=None;checked=''
        if namehash in cached and cached[namehash][0]==display:
            d=cached[namehash][1];checked=cached[namehash][2]
            if str(d.get('qc')) not in ('0','None'):issues.append('dadata_review')
            if d.get('result') and key(d['result'])!=key(display):issues.append('dadata_name_changed')
            if d.get('result'):clean_groups[key(d['result'])].append(tid)
        if display:names[namehash]=display
        rows.append({'trainer_id':tid,'display_name':display,'normalized_name':norm,'city':city or '',
          'profile_count':links,'source_codes':sources,'source_names':' | '.join(sorted({tidy(p[1]) for p in ps if tidy(p[1])})),
          'issue_codes':' | '.join(issues),'dadata_result':(d or {}).get('result',''),'dadata_qc':(d or {}).get('qc',''),
          'dadata_surname':(d or {}).get('surname',''),'dadata_name':(d or {}).get('name',''),
          'dadata_patronymic':(d or {}).get('patronymic',''),'dadata_cached_at':checked})
    return rows,names,original_key_groups,clean_groups

def report(args,con,trainers,profiles):
    rows,names,original,clean=make_rows(trainers,profiles,con)
    issues=collections.Counter(k.strip() for r in rows for k in r['issue_codes'].split(' | ') if k.strip())
    original_pairs=sum(len(v)*(len(v)-1)//2 for v in original.values() if len(v)>1)
    clean_pairs=sum(len(v)*(len(v)-1)//2 for v in clean.values() if len(v)>1)
    suspects=[]
    byid={r['trainer_id']:r for r in rows}
    for group,kind in ((original,'raw_name_match'),(clean,'dadata_normalized_name_match')):
        for name,ids in group.items():
            if len(ids)>1:
                for i in range(len(ids)):
                    for j in range(i+1,len(ids)):
                        a,b=byid[ids[i]],byid[ids[j]]
                        suspects.append({'evidence':kind,'left_trainer_id':a['trainer_id'],'right_trainer_id':b['trainer_id'],
                           'name':name,'left_sources':a['source_codes'],'right_sources':b['source_codes'],
                           'left_city':a['city'],'right_city':b['city']})
    # Keep one row per pair with evidence string, never claim confirmed identity.
    uniq={}
    for s in suspects:
        k=(s['left_trainer_id'],s['right_trainer_id']);
        if k in uniq:uniq[k]['evidence']+=' | '+s['evidence']
        else:uniq[k]=s
    missing=[r for r in rows if r['issue_codes']]
    write_csv(args.output/'trainer_quality_audit.csv',rows,FIELDS)
    write_csv(args.output/'trainer_issues_review.csv',missing,FIELDS)
    write_csv(args.output/'name_duplicate_candidates.csv',list(uniq.values()),['evidence','left_trainer_id','right_trainer_id','name','left_sources','right_sources','left_city','right_city'])
    summary={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'mode':'read_only_postgresql',
      'source_profiles':len(profiles),'trainers':len(trainers),
      'unique_nonempty_display_names':len(names),'cached_names_in_scope':sum(bool(r['dadata_cached_at']) for r in rows),
      'issues':dict(issues),'rows_with_issues':len(missing),'raw_name_match_pairs':original_pairs,
      'dadata_normalized_match_pairs_in_cache':clean_pairs,'distinct_candidate_pairs':len(uniq),
      'warning':'DaData normalizes names but does not verify identities. Candidate pairs are NOT confirmed duplicates. No PostgreSQL writes.'}
    dump(args.output/'cleaning_summary.json',summary)
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    print('Отчеты:',args.output)
    return rows,names

def request_name(session,name,keyval,secret):
    r=session.post(API,headers={'Authorization':'Token '+keyval,'X-Secret':secret,'Content-Type':'application/json'},json=[name],timeout=30)
    if r.status_code!=200:raise RuntimeError(f'DaData HTTP {r.status_code}: запрос остановлен, проверьте доступ/лимит')
    data=r.json()
    if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):raise RuntimeError('Некорректный формат ответа DaData')
    return data[0]

def main():
    p=argparse.ArgumentParser(description='Безопасный аудит единого каталога с опциональной стандартизацией ФИО через DaData')
    p.add_argument('command',choices=['audit','probe','run','report'])
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=15432)
    p.add_argument('--user',default='workoutplan_test');p.add_argument('--dbname',default='workoutplan')
    p.add_argument('--output',type=Path,default=Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\PostgreSQL'))
    p.add_argument('--limit',type=int,default=20)
    p.add_argument('--max-spend-rub',type=float)
    p.add_argument('--confirm-requests',action='store_true')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    trainers,profiles=retrieve(args)
    con=init_cache(args.output/'dadata_pg_cache.sqlite3')
    try:
        rows,names=report(args,con,trainers,profiles)
        if args.command in ('audit','report'):return
        if args.limit<1:raise RuntimeError('--limit должен быть больше нуля')
        cached={row[0] for row in con.execute('SELECT name_hash FROM clean_names')}
        # Incomplete names first, then deterministic by trainer_id; one call per unique name.
        priority=sorted([r for r in rows if r['display_name']],key=lambda r:(len(r['display_name'].split())>=2,r['trainer_id']))
        pending=[];seen=set()
        for r in priority:
            name=r['display_name'];h=hashlib.sha256(name.encode('utf-8')).hexdigest()
            if h not in cached and h not in seen:
                pending.append((h,name));seen.add(h)
        count=min(len(pending),1 if args.command=='probe' else args.limit)
        if not count:
            print('Все подходящие уникальные ФИО уже находятся в локальном кэше DaData.');return
        if not args.confirm_requests:raise RuntimeError('Для обращения к DaData требуется --confirm-requests')
        estimate=round(count*0.20,2)
        if args.max_spend_rub is None or args.max_spend_rub+1e-9<estimate:
            raise RuntimeError(f'Бюджет: максимум {estimate:.2f} руб. Укажите --max-spend-rub {estimate:.2f} или больше после проверки тарифа.')
        token=os.environ.get('DADATA_API_KEY','').strip();secret=os.environ.get('DADATA_SECRET_KEY','').strip()
        if not token or not secret:raise RuntimeError('Отсутствуют DADATA_API_KEY или DADATA_SECRET_KEY в окружении. Используйте run_cleaning.ps1')
        import requests
        session=requests.Session();processed=0
        print(f'Запрашиваем {count} новых уникальных ФИО; верхняя оценка {estimate:.2f} руб. Существующий кэш не оплачивается повторно.')
        for h,name in pending[:count]:
            try:result=request_name(session,name,token,secret)
            except Exception as exc:
                print('ОСТАНОВКА, сохранены успешные предыдущие ответы:',str(exc));break
            con.execute('INSERT INTO clean_names(name_hash,submitted_name,result_json,checked_at) VALUES (?,?,?,?)',
               (h,name,json.dumps(result,ensure_ascii=False),dt.datetime.now(dt.timezone.utc).isoformat()))
            con.commit();processed+=1
            time.sleep(0.3)
        print(f'Получено ответов: {processed}; повторно запускайте report для обновления CSV.')
        report(args,con,trainers,profiles)
    finally:con.close()

if __name__=='__main__':
    try:main()
    except Exception as exc:print('ОШИБКА:',exc,file=sys.stderr);sys.exit(1)
