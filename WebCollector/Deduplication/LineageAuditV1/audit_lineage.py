#!/usr/bin/env python3
"""Read-only source lineage & identity evidence audit for Fitness Trainer database.

No writes to PostgreSQL. Never merges source records.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote

COLUMNS = [
    'left_id', 'right_id', 'left_source', 'right_source', 'left_name', 'right_name',
    'left_url', 'right_url', 'priority', 'score', 'original_evidence', 'shared_socials',
    'lineage_class', 'lineage_evidence', 'master_source_name', 'master_profile_url',
    'master_other_urls', 'master_source_url', 'master_row', 'ddx_same_name_count',
    'master_same_name_count', 'same_club', 'same_city', 'action'
]


def normalize_url(value):
    """Only exact same-person URLs count. Preserve path identity; ignore trailing slash/query/fragments."""
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').casefold().removeprefix('www.')
        if parsed.scheme not in ('https', 'http') or not host:
            return ''
        path = unquote(parsed.path).rstrip('/').casefold()
        return f'{host}{path}' if path else ''
    except Exception:
        return ''


def extract_urls(value):
    return set(normalize_url(x.rstrip('.,;)>"')) for x in re.findall(r'https?://[^\s|<>"\']+', str(value or ''), re.I)) - {''}


def norm_name(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё','е')
    return ' '.join(re.findall(r'[^\W\d_][\w-]*', text, flags=re.UNICODE))


def norm_words(value):
    return norm_name(value).split()


def norm_club(value):
    return norm_name(value)


def read_candidates(filename):
    with filename.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        mandatory = {'left_id', 'right_id', 'left_source', 'right_source', 'left_name', 'right_name', 'priority'}
        if not mandatory.issubset(reader.fieldnames or []):
            raise RuntimeError('Incorrect input candidate CSV columns: ' + ', '.join(sorted(mandatory-set(reader.fieldnames or []))))
        rows = list(reader)
    return rows


def fetch_master_raw(host, port, user, dbname):
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError('Install: py -3.13 -m pip install "psycopg[binary]"') from e
    conn = psycopg.connect(host=host, port=port, user=user, dbname=dbname,
                           connect_timeout=10, options='-c default_transaction_read_only=on -c statement_timeout=120000')
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database(), current_user')
            print('Read-only connected:', cur.fetchone(), flush=True)
            cur.execute('''SELECT p.id, p.raw_name, p.raw_data
                           FROM fitness.source_profiles p
                           JOIN fitness.sources s ON p.source_id=s.id
                           WHERE s.code='legacy_master' ''')
            info = {}
            for pid, raw_name, raw_json in cur.fetchall():
                raw_json = raw_json if isinstance(raw_json, dict) else {}
                fields = raw_json.get('fields') or {}
                if not isinstance(fields, dict):
                    fields = {}
                info[str(pid)] = {'name': raw_name or '', 'fields': fields,
                                  'master_row': raw_json.get('master_row')}
            return info
    finally:
        conn.close()


def master_from_pair(row, masters):
    if row['left_source'] == 'legacy_master':
        return masters.get(str(row['left_id'])), row['right_url'], row['right_source']
    if row['right_source'] == 'legacy_master':
        return masters.get(str(row['right_id'])), row['left_url'], row['left_source']
    return None, '', ''


def classify(row, masters, same_name_ddx, same_name_master):
    master, other_url, other_source = master_from_pair(row, masters)
    fields = (master or {}).get('fields') or {}
    source_name = str(fields.get('Источник — название') or '').strip()
    master_profile_url = str(fields.get('Страница тренера в источнике') or '').strip()
    other_urls = str(fields.get('Дополнительные источники — URL') or '').strip()
    source_url = str(fields.get('URL источника') or '').strip()
    evidence = str(row.get('evidence') or '')
    social = str(row.get('shared_socials') or '').strip()
    norm_profile = normalize_url(other_url)
    explicit_urls = extract_urls(master_profile_url) | extract_urls(other_urls)
    # Generic source URL can be a category page, so it is only proof if it
    # exactly equals an individual profile URL.
    source_url_match = norm_profile and norm_profile in extract_urls(source_url)
    exact_url = bool(norm_profile and (norm_profile in explicit_urls or source_url_match))

    if exact_url:
        label = 'exact_source_profile_url'
        reasons = 'master references exact individual source URL'
        action = 'verify_exact_url_then_link'
    elif social:
        label = 'shared_social_review'
        reasons = 'same social account in candidate report; identity still needs confirmation'
        action = 'review_social_account_ownership'
    elif 'same_full_name' in evidence and 'same_club_text' in evidence and 'same_city' in evidence:
        label = 'name_club_city_review'
        reasons = 'same full name, club and city; no exact profile URL or shared social'
        action = 'manual_review'
    elif other_source == 'ddxfitness' and source_name and 'ddx' in source_name.casefold():
        label = 'master_source_tag_only'
        reasons = 'master source label mentions DDX; no exact individual source URL'
        action = 'review_provenance'
    elif other_source == 'ddxfitness':
        label = 'same_name_only_ddx'
        reasons = 'identical name not sufficient; legacy master is a consolidated workbook'
        action = 'do_not_link_without_more_evidence'
    elif not master:
        label = 'independent_sources_name_only'
        reasons = 'not a legacy master pair; name alone insufficient'
        action = 'manual_review'
    else:
        label = 'same_name_only'
        reasons = 'same name alone insufficient'
        action = 'do_not_link_without_more_evidence'

    if 'legacy_master' in (row['left_source'], row['right_source']):
        name = norm_name(row['left_name'] if row['left_source'] == 'legacy_master' else row['right_name'])
    else:
        name = norm_name(row['left_name'])
    same_club = 'same_club_text' in evidence
    same_city = 'same_city' in evidence

    return {
        'left_id': row['left_id'], 'right_id': row['right_id'],
        'left_source': row['left_source'], 'right_source': row['right_source'],
        'left_name': row['left_name'], 'right_name': row['right_name'],
        'left_url': row.get('left_url', ''), 'right_url': row.get('right_url', ''),
        'priority': row.get('priority',''), 'score': row.get('score',''),
        'original_evidence': evidence, 'shared_socials': social,
        'lineage_class': label, 'lineage_evidence': reasons,
        'master_source_name': source_name, 'master_profile_url': master_profile_url,
        'master_other_urls': other_urls, 'master_source_url': source_url,
        'master_row': str((master or {}).get('master_row') or ''),
        'ddx_same_name_count': same_name_ddx.get(name,0),
        'master_same_name_count': same_name_master.get(name,0),
        'same_club': same_club, 'same_city': same_city, 'action': action,
    }


def save_csv(file, rows):
    with file.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description='Fitness Lineage Audit V1 — read-only audit of candidate pairs')
    ap.add_argument('--candidates', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=15432)
    ap.add_argument('--user', default='workoutplan_test')
    ap.add_argument('--dbname', default='workoutplan')
    args = ap.parse_args()
    rows = read_candidates(args.candidates)
    print(f'Candidate rows: {len(rows)}', flush=True)
    masters = fetch_master_raw(args.host, args.port, args.user, args.dbname)
    print(f'Legacy source records read: {len(masters)}', flush=True)
    same_name_ddx = Counter()
    same_name_master = Counter()
    ddx_id_by_name = defaultdict(set)
    master_id_by_name = defaultdict(set)
    for r in rows:
        for side in ('left','right'):
            name = norm_name(r[side+'_name'])
            if r[side+'_source'] == 'ddxfitness':
                ddx_id_by_name[name].add(str(r[side+'_id']))
            elif r[side+'_source'] == 'legacy_master':
                master_id_by_name[name].add(str(r[side+'_id']))
    same_name_ddx.update({n:len(ids) for n,ids in ddx_id_by_name.items()})
    same_name_master.update({n:len(ids) for n,ids in master_id_by_name.items()})

    detailed = [classify(r, masters, same_name_ddx, same_name_master) for r in rows]
    ambiguous = [r for r in detailed if r['ddx_same_name_count'] > 1 or r['master_same_name_count'] > 1]
    exact = [r for r in detailed if r['lineage_class'] == 'exact_source_profile_url']
    strong_social = [r for r in detailed if r['lineage_class'] == 'shared_social_review']

    args.output.mkdir(parents=True, exist_ok=True)
    save_csv(args.output/'lineage_candidates_detailed.csv', detailed)
    save_csv(args.output/'lineage_ambiguous_names.csv', ambiguous)
    save_csv(args.output/'lineage_exact_urls.csv', exact)
    save_csv(args.output/'lineage_social_review.csv', strong_social)

    pair_counts = Counter(' + '.join(sorted((r['left_source'],r['right_source']))) for r in detailed)
    categories = Counter(r['lineage_class'] for r in detailed)
    distinct_master = len({r['left_id'] if r['left_source']=='legacy_master' else r['right_id'] for r in detailed if 'legacy_master' in (r['left_source'],r['right_source'])})
    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'read_only',
        'candidate_rows': len(detailed),
        'legacy_records_examined': len(masters),
        'unique_legacy_candidate_ids': distinct_master,
        'pair_source_distribution': dict(sorted(pair_counts.items())),
        'lineage_categories': dict(sorted(categories.items())),
        'exact_source_profile_url_pairs': len(exact),
        'shared_social_pairs_needing_review': len(strong_social),
        'ambiguous_candidate_rows': len(ambiguous),
        'distinct_ambiguous_ddx_names': len({norm_name(r['left_name']) for r in ambiguous if r['ddx_same_name_count']>1}),
        'note': 'Reports are evidence for manual review only. No trainer identity asserted and NO database writes.'
    }
    (args.output/'lineage_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2),flush=True)
    print('Reports:',args.output,flush=True)

if __name__=='__main__':
    main()
