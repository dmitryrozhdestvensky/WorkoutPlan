#!/usr/bin/env python3
"""Fitness canonical trainer builder, exact lineage only. PostgreSQL 17; fail-closed."""
import argparse, csv, json, hashlib, sys, unicodedata, re
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
from urllib.parse import urlsplit,unquote

EXPECTED_COLS={
 'trainers':{'id','display_name','normalized_name','city','bio','review_status','created_at','updated_at'},
 'trainer_profile_links':{'trainer_id','source_profile_id','link_method','reviewed_at','evidence'},
 'source_profiles':{'id','source_id','profile_url','raw_name','normalized_name','city','raw_data'},
}

def normurl(v):
    try:
        p=urlsplit(str(v or '').strip()); host=(p.hostname or '').lower().removeprefix('www.')
        if p.scheme.lower() not in ('http','https') or not host:return ''
        return host+unquote(p.path).rstrip('/').casefold()
    except Exception:return ''

def urls(v):
    return {normurl(s.rstrip('.,;)>"\'')) for s in re.findall(r'https?://[^\s|<>"\']+',str(v or ''),re.I)}-{''}

def normname(v):
    return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е').split())

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f,delimiter=';'); need={'left_id','right_id','left_source','right_source','right_url','lineage_class'}
        if not need.issubset(r.fieldnames or []):raise RuntimeError('Некорректные колонки CSV: '+repr(sorted(need-set(r.fieldnames or []))))
        return list(r)

def columns(cur,table):
    cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',('fitness',table))
    return {r[0] for r in cur.fetchall()}

def get_state(cur, expected_total):
    for table,need in EXPECTED_COLS.items():
        got=columns(cur,table)
        if not need.issubset(got):raise RuntimeError('Неподходящая схема fitness.'+table+': '+str(sorted(need-got)))
    cur.execute('''SELECT p.id,s.code,p.profile_url,p.raw_name,p.normalized_name,p.city,p.raw_data
        FROM fitness.source_profiles p JOIN fitness.sources s ON s.id=p.source_id ORDER BY p.id''')
    profiles={}
    for pid,src,url,rawname,nname,city,raw in cur.fetchall():
        profiles[int(pid)]={'source':src,'url':url or '', 'name':rawname or '', 'norm':nname or '', 'city':city or '', 'data':raw if isinstance(raw,dict) else {}}
    if len(profiles)!=expected_total:raise RuntimeError(f'В БД {len(profiles)} анкет, ожидалось {expected_total}; остановлено')
    cur.execute('SELECT id,display_name FROM fitness.trainers ORDER BY id')
    trainers={int(tid):nm for tid,nm in cur.fetchall()}
    cur.execute('SELECT trainer_id,source_profile_id FROM fitness.trainer_profile_links')
    links=defaultdict(set);bytrainer=defaultdict(set)
    for tid,pid in cur.fetchall():
        links[int(pid)].add(int(tid));bytrainer[int(tid)].add(int(pid))
    if any(len(tids)>1 for tids in links.values()):raise RuntimeError('Одна исходная анкета уже связана с несколькими тренерами. Нужен ручной разбор.')
    if any(pid not in profiles for pid in links):raise RuntimeError('Обнаружены связи с отсутствующими исходными анкетами')
    if any(tid not in trainers for tids in links.values() for tid in tids):raise RuntimeError('Обнаружены связи с отсутствующими тренерами')
    if set(trainers)-set(bytrainer):raise RuntimeError('Есть существующие карточки без исходных профилей; требуется ручная проверка до создания новых')
    return profiles,trainers,links,bytrainer

def build_plan(rows,profiles,trainers,links,bytrainer,expected_pairs):
    if len(rows)!=expected_pairs:raise RuntimeError(f'В CSV {len(rows)} пар, ожидалось {expected_pairs}')
    used_left=set();used_right=set();pairs=[]
    for i,r in enumerate(rows,2):
        try:a,b=int(r['left_id']),int(r['right_id'])
        except (ValueError,TypeError):raise RuntimeError(f'Строка {i}: неверный ID')
        if a in used_left or b in used_right or a==b:raise RuntimeError(f'Строка {i}: неуникальное соответствие')
        used_left.add(a);used_right.add(b)
        x,y=profiles.get(a),profiles.get(b)
        if not x or not y:raise RuntimeError(f'Строка {i}: профиль отсутствует в БД')
        if r['left_source']!='legacy_master' or x['source']!='legacy_master' or r['right_source'] not in ('ddxfitness','regymsport') or y['source']!=r['right_source']:
            raise RuntimeError(f'Строка {i}: неправильная пара источников')
        if r['lineage_class']!='exact_source_profile_url':raise RuntimeError(f'Строка {i}: нет подтверждения по URL')
        sx=normurl(y['url']); csvurl=normurl(r['right_url'])
        fields=x['data'].get('fields') or {}
        if not isinstance(fields,dict):fields={}
        master_urls=set().union(*(urls(fields.get(key)) for key in ('Страница тренера в источнике','Дополнительные источники — URL','URL источника')))
        if not sx or sx!=csvurl or sx not in master_urls:raise RuntimeError(f'Строка {i}: URL не подтверждён актуальной БД')
        if not normname(x['name']) or normname(x['name'])!=normname(y['name']):raise RuntimeError(f'Строка {i}: ФИО отличаются')
        pairs.append((a,b))
    # Every exact pair defines a 2-profile group. Remaining profiles are singletons.
    group_for={}; groups=[]
    for a,b in pairs:
        group=frozenset((a,b));groups.append(group);group_for[a]=group;group_for[b]=group
    for pid in profiles:
        if pid not in group_for:
            group=frozenset((pid,));groups.append(group);group_for[pid]=group
    group_existing={}
    for group in groups:
        tids={tid for pid in group for tid in links.get(pid,set())}
        if len(tids)>1:raise RuntimeError(f'Разные тренеры для одной пары: {sorted(group)}')
        if tids:
            tid=next(iter(tids))
            if bytrainer[tid]!=bytrainer[tid].intersection(group):raise RuntimeError(f'Имеющаяся карточка {tid} охватывает другие группы, требуется ручная проверка')
            if any(group_for[p]!=group for p in bytrainer[tid]):raise RuntimeError(f'Несовместимое существующее объединение у тренера {tid}')
            group_existing[group]=tid
    # Ensure each existing trainer does not appear in more than one group.
    used_existing=list(group_existing.values())
    if len(used_existing)!=len(set(used_existing)):raise RuntimeError('Одна существующая карточка пересекает несколько групп')
    new_count=len(groups)-len(group_existing)
    new_links=sum(len(g)-sum(bool(links.get(pid)) for pid in g) for g in groups)
    return pairs,groups,group_existing,new_count,new_links

def dump_json(path,d):path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')

def run(args):
    if args.apply and args.confirm!='LINK_1755_EXACT_URL_PAIRS':raise RuntimeError('Для записи требуется --confirm LINK_1755_EXACT_URL_PAIRS')
    if args.dbname!='workoutplan':raise RuntimeError('Разрешена только БД workoutplan; не меняйте её без ревизии скрипта')
    rows=read_csv(args.exact);digest=hashlib.sha256(args.exact.read_bytes()).hexdigest()
    import psycopg
    args.output.mkdir(parents=True,exist_ok=True)
    conn=psycopg.connect(host=args.host,port=args.port,user=args.user,dbname=args.dbname,connect_timeout=10,options='-c statement_timeout=180000')
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                if not args.apply:
                    cur.execute('SET TRANSACTION READ ONLY')
                cur.execute('SELECT current_database(),current_user')
                db,user=cur.fetchone()
                if db!='workoutplan':raise RuntimeError('Неправильная база данных')
                if args.apply:
                    # Lock before validating to avoid concurrent changes until commit.
                    cur.execute('LOCK TABLE fitness.source_profiles, fitness.trainers, fitness.trainer_profile_links IN SHARE ROW EXCLUSIVE MODE')
                profiles,trainers,links,bytrainer=get_state(cur,args.expected_profiles)
                pairs,groups,existing,new_count,new_links=build_plan(rows,profiles,trainers,links,bytrainer,args.expected_pairs)
                summary={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'apply' if args.apply else 'dry_run',
                  'database':db,'db_user':user,'input_sha256':digest,'input_pairs':len(pairs),'source_profiles':len(profiles),
                  'expected_groups_after_linking':len(groups),'current_trainers':len(trainers),'existing_group_cards':len(existing),
                  'new_trainers_to_create':new_count,'new_links_to_create':new_links,'existing_links_preserved':sum(map(len,links.values())),
                  'sources_in_pairs':dict(Counter(profiles[b]['source'] for _,b in pairs)),
                  'link_policy':'exact_source_profile_url only; all other profiles singleton; no fuzzy matches',
                  'note':'No source profile deletions or edits. public schema untouched.'}
                if args.apply:
                    # Sequence-free IDs: locks prevent conflicting concurrent insertions for this transaction.
                    next_id=max(trainers,default=0)+1
                    inserts=[]; link_inserts=[]
                    for group in groups:
                        tid=existing.get(group)
                        if tid is None:
                            tid=next_id;next_id+=1
                            # Prefer actual DDX/Regym source name for pairs; otherwise source profile name.
                            profiles_in_group=sorted(group,key=lambda p:(profiles[p]['source']=='legacy_master',p))
                            anchor=profiles[profiles_in_group[0]]
                            display=anchor['name'] or anchor['norm'] or None
                            normalized=normname(display) if display else None
                            city=anchor['city'] or next((profiles[p]['city'] for p in profiles_in_group if profiles[p]['city']),None)
                            inserts.append((tid,display,normalized,city))
                        for pid in sorted(group):
                            if not links.get(pid):
                                method='source_lineage_exact_url' if len(group)==2 else 'singleton_source_profile'
                                ev='exact_source_profile_url;'+digest[:16] if len(group)==2 else 'singleton;no_confirmed_cross_source_identity'
                                link_inserts.append((tid,pid,method,ev))
                    assert len(inserts)==new_count and len(link_inserts)==new_links
                    # Stop instead of creating an inconsistent result if ID sequence is unexpectedly managed elsewhere.
                    cur.execute("SELECT pg_get_serial_sequence('fitness.trainers','id')")
                    seq=cur.fetchone()[0]
                    for i in range(0,len(inserts),500):
                        batch=inserts[i:i+500]
                        cur.execute('''INSERT INTO fitness.trainers(id,display_name,normalized_name,city,review_status)
                          SELECT x.id,x.nm,x.nn,x.city,'provisional' FROM
                          UNNEST(%s::bigint[],%s::text[],%s::text[],%s::text[]) AS x(id,nm,nn,city)''',
                          ([x[0] for x in batch],[x[1] for x in batch],[x[2] for x in batch],[x[3] for x in batch]))
                    for i in range(0,len(link_inserts),500):
                        batch=link_inserts[i:i+500]
                        cur.execute('''INSERT INTO fitness.trainer_profile_links(trainer_id,source_profile_id,link_method,evidence)
                          SELECT * FROM UNNEST(%s::bigint[],%s::bigint[],%s::text[],%s::text[])''',
                          ([x[0] for x in batch],[x[1] for x in batch],[x[2] for x in batch],[x[3] for x in batch]))
                    if seq and inserts:
                        # Sequence is a quoted PostgreSQL identifier returned by built-in, passed as regclass parameter.
                        cur.execute('SELECT setval(%s::regclass,%s,true)',(seq,max(max(trainers,default=0),next_id-1)))
                    cur.execute('SELECT COUNT(*) FROM fitness.trainers');summary['trainers_after']=cur.fetchone()[0]
                    cur.execute('SELECT COUNT(*),COUNT(DISTINCT source_profile_id) FROM fitness.trainer_profile_links');total,unique=cur.fetchone()
                    summary['links_after']=total;summary['distinct_profiles_linked_after']=unique
                    if summary['trainers_after']!=len(groups):raise RuntimeError('Число карточек не равно ожидаемому; откат')
                    if unique!=len(profiles) or total!=len(profiles):raise RuntimeError('Проверка целостности не прошла; транзакция отменена')
                    cur.execute('''SELECT COUNT(*) FROM (SELECT trainer_id,COUNT(*) n FROM fitness.trainer_profile_links GROUP BY trainer_id HAVING COUNT(*)>2) x''')
                    if cur.fetchone()[0]:raise RuntimeError('Обнаружена карточка с более чем двумя исходными профилями; откат')
        # Transaction committed only if no exception.
        dump_json(args.output/('identity_apply_result.json' if args.apply else 'identity_dry_run.json'),summary)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        print('Reports:',args.output)
    finally:conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Safe exact URL identity linker for fitness schema. Default is read-only.')
    p.add_argument('--exact',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',default=15432,type=int)
    p.add_argument('--user',default='workoutplan_test');p.add_argument('--dbname',default='workoutplan')
    p.add_argument('--expected-profiles',default=5652,type=int);p.add_argument('--expected-pairs',default=1755,type=int)
    p.add_argument('--apply',action='store_true');p.add_argument('--confirm',default='')
    try:run(p.parse_args())
    except Exception as e:
        print('ОШИБКА: '+str(e),file=sys.stderr);sys.exit(1)
