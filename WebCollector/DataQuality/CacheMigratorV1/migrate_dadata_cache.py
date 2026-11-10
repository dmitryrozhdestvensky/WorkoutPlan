#!/usr/bin/env python3
"""Transfer saved name cleaning results from legacy to PG cache, no DaData calls and no PostgreSQL writes."""
import argparse, csv, datetime as dt, hashlib, json, shutil, sqlite3, sys, unicodedata
from pathlib import Path

def tidy(s): return ' '.join(unicodedata.normalize('NFKC', str(s or '')).split())
def hname(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()

def table_columns(con, table):
    return {r[1] for r in con.execute('PRAGMA table_info("' + table + '")')}

def main():
    ap=argparse.ArgumentParser(description='Copy legacy DaData name results to new PG cache (no network or PG changes).')
    ap.add_argument('--old',type=Path,default=Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\dadata_quality_progress.sqlite3'))
    ap.add_argument('--new',type=Path,default=Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\PostgreSQL\dadata_pg_cache.sqlite3'))
    ap.add_argument('--audit-csv',type=Path,default=Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\PostgreSQL\trainer_quality_audit.csv'))
    ap.add_argument('--output',type=Path,default=Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\PostgreSQL\cache_migration_summary.json'))
    ap.add_argument('--apply',action='store_true',help='Apply reviewed insertions, backup new cache first.')
    args=ap.parse_args()
    for p in (args.old,args.new,args.audit_csv):
        if not p.is_file(): raise RuntimeError(f'Missing required input: {p}')
    with args.audit_csv.open('r',encoding='utf-8-sig',newline='') as fh:
        rdr=csv.DictReader(fh,delimiter=';')
        if not {'display_name','trainer_id'}.issubset(rdr.fieldnames or []):raise RuntimeError('Unexpected audit CSV header')
        names={tidy(row['display_name']) for row in rdr if tidy(row['display_name'])}
    with sqlite3.connect(f'file:{args.old.as_posix()}?mode=ro',uri=True) as old:
        expected={'master_row','original_name','normalized_name','surname','name','patronymic','qc','city','clubs','source_profile','checked_at'}
        if not expected.issubset(table_columns(old,'names')):raise RuntimeError('Legacy schema mismatch; refusing migration')
        old_rows=old.execute('SELECT master_row,original_name,normalized_name,surname,name,patronymic,qc,checked_at FROM names').fetchall()
    with sqlite3.connect(f'file:{args.new.as_posix()}?mode=ro',uri=True) as new_ro:
        expected={'name_hash','submitted_name','result_json','checked_at'}
        if not expected.issubset(table_columns(new_ro,'clean_names')):raise RuntimeError('New cache schema mismatch; refusing migration')
        current={r[0]:r[1] for r in new_ro.execute('SELECT name_hash,submitted_name FROM clean_names')}
    counts={'old_rows':len(old_rows),'new_cache_before':len(current),'audit_unique_display_names':len(names),'not_in_current_catalog':0,'existing_cache':0,'empty_name_or_result':0,'duplicate_old_name':0,'hash_collision':0,'to_import':0}
    proposed={}
    for master_row,original,normalized,surname,firstname,patronymic,qc,checked_at in old_rows:
        original=tidy(original); normalized=tidy(normalized)
        if not original or not normalized:
            counts['empty_name_or_result']+=1;continue
        if original not in names:
            counts['not_in_current_catalog']+=1;continue
        h=hname(original)
        if h in current:
            if current[h]!=original:counts['hash_collision']+=1
            else:counts['existing_cache']+=1
            continue
        if h in proposed:
            counts['duplicate_old_name']+=1
            if proposed[h][1]!=normalized:raise RuntimeError('Conflicting old normalizations for name: '+original)
            continue
        result={'source':original,'result':normalized,'surname':tidy(surname) or None,'name':tidy(firstname) or None,
                'patronymic':tidy(patronymic) or None,'qc':qc if qc is not None else None,
                '_cache_origin':'legacy_dadata_quality_progress','_legacy_master_row':master_row,
                '_legacy_import_note':'Reconstructed from saved legacy fields; not a fresh DaData API response.'}
        proposed[h]=(original,normalized,json.dumps(result,ensure_ascii=False),str(checked_at or dt.datetime.now(dt.timezone.utc).isoformat()))
    if counts['hash_collision']:raise RuntimeError('Hash conflict, stopping')
    counts['to_import']=len(proposed)
    report={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'mode':'apply' if args.apply else 'preview',
            'old_cache':str(args.old),'new_cache':str(args.new),'audit_csv':str(args.audit_csv),**counts,
            'new_cache_after_expected':len(current)+len(proposed),
            'note':'Existing cache rows never overwritten. Legacy results matched by exact normalized whitespace name, no API calls, no PostgreSQL writes.'}
    if args.apply and proposed:
        stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup=args.new.with_name(args.new.stem+'_before_legacy_merge_'+stamp+args.new.suffix)
        # SQLite live backup API is consistent even if WAL is enabled.
        with sqlite3.connect(f'file:{args.new.as_posix()}?mode=ro',uri=True) as src,sqlite3.connect(backup) as dest:
            src.backup(dest)
        report['backup']=str(backup)
        with sqlite3.connect(args.new) as db:
            db.execute('BEGIN IMMEDIATE')
            for h,(name,normalized,payload,when) in proposed.items():
                db.execute('INSERT INTO clean_names (name_hash,submitted_name,result_json,checked_at) VALUES (?,?,?,?)',(h,name,payload,when))
            db.commit()
            report['new_cache_after_actual']=db.execute('SELECT COUNT(*) FROM clean_names').fetchone()[0]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print('Report:',args.output)

if __name__=='__main__':
    try:main()
    except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
