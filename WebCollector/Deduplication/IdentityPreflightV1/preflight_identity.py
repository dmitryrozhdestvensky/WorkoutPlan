#!/usr/bin/env python3
"""Read-only identity link preflight. Does not write to DB. PostgreSQL 17+."""
import argparse,csv,json,re,unicodedata
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,unquote

FIELDS=['legacy_id','source_id','source_code','name','source_profile_url','legacy_source_url','url_confirmed','name_confirmed','uniqueness_confirmed','existing_legacy_trainer_id','existing_source_trainer_id','decision','reason']

def normurl(v):
    try:
        p=urlsplit(str(v or '').strip())
        if p.scheme.lower() not in ('http','https') or not p.hostname:return ''
        return p.hostname.lower().removeprefix('www.')+unquote(p.path).rstrip('/').casefold()
    except Exception:return ''

def urls(v):
    return {normurl(s.rstrip('.,;)>"\'')) for s in re.findall(r'https?://[^\s|<>"\']+',str(v or ''),re.I)}-{''}

def name(v):
    v=unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е')
    return ' '.join(v.split())

def load_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f,delimiter=';')
        needed={'left_id','right_id','left_source','right_source','right_url','lineage_class','master_profile_url','master_source_url','left_name','right_name'}
        if not needed.issubset(r.fieldnames or []):raise RuntimeError('Missing CSV fields: '+repr(sorted(needed-set(r.fieldnames or []))))
        return list(r)

def connection(args):
    import psycopg
    return psycopg.connect(host=args.host,port=args.port,user=args.user,dbname=args.dbname,connect_timeout=10,options='-c default_transaction_read_only=on -c statement_timeout=120000')

def column_info(cur,tab):
    cur.execute('''SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns
       WHERE table_schema='fitness' AND table_name=%s ORDER BY ordinal_position''',(tab,))
    return [{'name':a,'type':b,'nullable':c,'default':d} for a,b,c,d in cur.fetchall()]

def get_db(cur, ids):
    cur.execute('''SELECT p.id,s.code,p.profile_url,p.raw_name,p.raw_data FROM fitness.source_profiles p JOIN fitness.sources s ON s.id=p.source_id
        WHERE p.id=ANY(%s)''',(list(ids),))
    d={}
    for pid,src,url,rawname,rawdata in cur.fetchall():
        d[int(pid)]={'source':src,'url':url or '', 'name':rawname or '', 'data':rawdata if isinstance(rawdata,dict) else {}}
    return d

def link_index(cur):
    cols={c['name'] for c in column_info(cur,'trainer_profile_links')}
    if not {'trainer_id','source_profile_id'}.issubset(cols):return {},'missing trainer_id/source_profile_id in trainer_profile_links'
    cur.execute('SELECT source_profile_id,trainer_id FROM fitness.trainer_profile_links')
    idx=defaultdict(set)
    for pid,tid in cur.fetchall():idx[int(pid)].add(str(tid))
    return idx,None

def writecsv(path,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=';',extrasaction='ignore');w.writeheader();w.writerows(rows)

def run(args):
    exact=load_csv(args.exact)
    amb=load_csv(args.ambiguous)
    ids=set()
    for r in exact:
        ids.update((int(r['left_id']),int(r['right_id'])))
    pair_keys=Counter();left=Counter();right=Counter()
    for r in exact:
        pair_keys[(r['left_id'],r['right_id'])]+=1
        left[r['left_id']]+=1;right[r['right_id']]+=1
    with connection(args) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database(),current_user')
            actual=cur.fetchone()
            if actual[0]!=args.dbname:raise RuntimeError('Wrong database')
            db=get_db(cur,ids)
            links,link_error=link_index(cur)
            schema={t:column_info(cur,t) for t in ['trainers','trainer_profile_links','source_profiles','merge_candidates']}
    results=[]
    for r in exact:
        lid,rid=int(r['left_id']),int(r['right_id'])
        a,b=db.get(lid),db.get(rid)
        reason=[]
        if not a or not b:reason.append('missing_profile_in_db')
        if a and a['source']!='legacy_master':reason.append('legacy_source_mismatch')
        if b and b['source']!=r['right_source']:reason.append('source_mismatch')
        if r['left_source']!='legacy_master' or r['right_source'] not in ('ddxfitness','regymsport'):reason.append('unexpected_pair_type')
        if r['lineage_class']!='exact_source_profile_url':reason.append('not_exact_lineage')
        same_url=False;same_name=False
        if a and b:
            fields=a['data'].get('fields') or {}
            if not isinstance(fields,dict):fields={}
            source_urls=urls(fields.get('Страница тренера в источнике')) | urls(fields.get('Дополнительные источники — URL')) | urls(fields.get('URL источника'))
            same_url=bool(normurl(b['url']) and normurl(b['url']) in source_urls and normurl(b['url'])==normurl(r['right_url']))
            same_name=bool(name(a['name']) and name(a['name'])==name(b['name']))
        if not same_url:reason.append('source_url_not_confirmed_in_live_db')
        if not same_name:reason.append('names_differ_in_live_db')
        unique=left[str(lid)]==1 and right[str(rid)]==1 and pair_keys[(str(lid),str(rid))]==1
        if not unique:reason.append('non_unique_mapping')
        if link_error:reason.append('cannot_inspect_existing_links')
        ta=links.get(lid,set());tb=links.get(rid,set())
        if len(ta)>1 or len(tb)>1 or (ta and tb and ta!=tb):reason.append('existing_trainer_link_conflict')
        status='review' if reason else ('already_linked' if ta and tb and ta==tb else 'candidate_ready')
        results.append({'legacy_id':lid,'source_id':rid,'source_code':r['right_source'],'name':r['right_name'],
           'source_profile_url':b['url'] if b else r['right_url'],'legacy_source_url':r['master_profile_url'],
           'url_confirmed':same_url,'name_confirmed':same_name,'uniqueness_confirmed':unique,
           'existing_legacy_trainer_id':','.join(sorted(ta)),'existing_source_trainer_id':','.join(sorted(tb)),
           'decision':status,'reason':','.join(reason)})
    args.output.mkdir(parents=True,exist_ok=True)
    writecsv(args.output/'identity_link_plan.csv',results)
    ambiguous_ids={(r['left_id'],r['right_id']) for r in amb if r['lineage_class']=='exact_source_profile_url'}
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'read_only','database':actual[0],
       'db_user':actual[1],'input_exact_pairs':len(exact),'input_ambiguous_rows':len(amb),
       'exact_pairs_also_in_ambiguous_report':len(ambiguous_ids),'decisions':dict(Counter(r['decision'] for r in results)),
       'reasons':dict(Counter(reason for r in results for reason in r['reason'].split(',') if reason)),
       'by_source':dict(Counter(r['source_code'] for r in results)),
       'note':'No insert/update/delete was executed. Preview only. No identity clusters created.'}
    (args.output/'identity_preflight_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'fitness_schema_inspection.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Reports:',args.output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Read-only preflight for fitness trainer canonical links')
    p.add_argument('--exact',type=Path,required=True);p.add_argument('--ambiguous',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',default=15432,type=int)
    p.add_argument('--user',default='workoutplan_test');p.add_argument('--dbname',default='workoutplan')
    run(p.parse_args())
