"""WebCollector Fitness Dedup V1: evidence-based cross-source candidates, no merges.
Python 3.10+, psycopg 3. Uses libpq pgpass on Windows.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, unquote

SOCIAL_PLATFORMS = {'vk', 'ok', 'dzen', 'telegram', 'instagram', 'tiktok', 'tenchat'}
PAIR_LIMIT = 10000


def norm_words(value):
    txt = unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё', 'е')
    txt = re.sub(r'[^\w\s-]', ' ', txt, flags=re.UNICODE).replace('_', ' ')
    return tuple(re.findall(r'[^\W\d_][\w-]*', txt, flags=re.UNICODE))


def norm_name(value):
    return ' '.join(norm_words(value))


def norm_social(platform, url):
    if not url:
        return ''
    try:
        u = urlsplit(str(url).strip())
        host = (u.hostname or '').lower().removeprefix('www.')
        path = unquote(u.path).strip('/').casefold()
        # Avoid platform homepages, sharing links, invite links and searches.
        if not host or not path or path in ('feed', 'home', 'search', 'share', 'login'):
            return ''
        if platform == 'vk' and host not in ('vk.com', 'm.vk.com', 'vkontakte.ru'):
            return ''
        if platform == 'telegram' and host not in ('t.me', 'telegram.me'):
            return ''
        if platform == 'ok' and host != 'ok.ru':
            return ''
        if platform == 'dzen' and host not in ('dzen.ru', 'zen.yandex.ru'):
            return ''
        if platform == 'instagram' and host != 'instagram.com':
            return ''
        if platform == 'tiktok' and host != 'tiktok.com':
            return ''
        if platform == 'tenchat' and host != 'tenchat.ru':
            return ''
        return platform + ':' + path.rstrip('/')
    except Exception:
        return ''


def norm_club(value):
    words = norm_words(value)
    # Generic company names alone are not useful proof of same club.
    return ' '.join(words) if len(words) > 0 else ''


def useful_city(value):
    x = norm_name(value)
    return x if x and 'не уточн' not in x and x not in ('нет', 'unknown', 'не указан') else ''


def get_raw_fields(data):
    if not isinstance(data, dict):
        return {}
    fields = data.get('fields')
    return fields if isinstance(fields, dict) else {}


def group_blocks(groups, index, indices, cap=120):
    for key, ids in groups.items():
        if not key or len(ids) < 2:
            continue
        if len(ids) > cap:
            continue
        for ii in range(len(ids)):
            for jj in range(ii + 1, len(ids)):
                a, b = ids[ii], ids[jj]
                if index[a]['source'] == index[b]['source']:
                    continue
                indices.add((min(a, b), max(a, b)))


def shortlist(records, socials):
    index = {x['id']: x for x in records}
    by_full_name, by_sorted_name, by_social, by_name_club = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for x in records:
        name = norm_name(x['name'])
        tokens = norm_words(x['name'])
        if len(tokens) >= 2:
            by_full_name[name].append(x['id'])
            by_sorted_name[' '.join(sorted(tokens))].append(x['id'])
            club = norm_club(x['clubs'])
            if club:
                by_name_club[(name, club)].append(x['id'])
        for social in socials.get(x['id'], set()):
            by_social[social].append(x['id'])
    pairs = set()
    for block in (by_full_name, by_sorted_name, by_name_club, by_social):
        group_blocks(block, index, pairs)
    return pairs


def compare(a, b, socials):
    n1, n2 = norm_name(a['name']), norm_name(b['name'])
    w1, w2 = norm_words(a['name']), norm_words(b['name'])
    name_exact = len(w1) >= 2 and w1 == w2
    name_permuted = len(w1) >= 2 and len(w2) >= 2 and sorted(w1) == sorted(w2) and not name_exact
    shared_socials = sorted(socials.get(a['id'], set()) & socials.get(b['id'], set()))
    c1, c2 = norm_club(a['clubs']), norm_club(b['clubs'])
    club_exact = bool(c1 and c2 and c1 == c2)
    city1, city2 = useful_city(a['city']), useful_city(b['city'])
    city_match = bool(city1 and city2 and city1 == city2)
    city_conflict = bool(city1 and city2 and city1 != city2)
    # Fuzzy spelling is only supporting evidence; this version does not introduce
    # fuzzy-only candidates to avoid large quantities of false positives.
    name_ratio = round(SequenceMatcher(None, n1, n2).ratio(), 3) if n1 and n2 else 0
    score = 0
    reasons = []
    if shared_socials:
        score += 75
        reasons.append('same_social_account')
    if name_exact:
        score += 48
        reasons.append('same_full_name')
    elif name_permuted:
        score += 42
        reasons.append('name_tokens_permuted')
    elif shared_socials and name_ratio >= 0.86 and len(w1) >= 2 and len(w2) >= 2:
        score += 20
        reasons.append('similar_name')
    if club_exact:
        score += 18
        reasons.append('same_club_text')
    if city_match:
        score += 6
        reasons.append('same_city')
    if city_conflict:
        reasons.append('different_cities_not_disqualifying')
    if not reasons or (not shared_socials and not name_exact and not name_permuted):
        return None
    # Capped score is a review priority heuristic, NOT a statistical probability.
    score = min(score, 100)
    level = 'high' if score >= 85 else 'medium' if score >= 60 else 'low'
    return {
        'left_id': a['id'], 'right_id': b['id'],
        'left_source': a['source'], 'right_source': b['source'],
        'left_name': a['name'], 'right_name': b['name'],
        'left_url': a['url'], 'right_url': b['url'],
        'left_city': a['city'], 'right_city': b['city'],
        'left_clubs': a['clubs'], 'right_clubs': b['clubs'],
        'score': score, 'priority': level,
        'evidence': ','.join(reasons), 'name_similarity': name_ratio,
        'shared_socials': ' | '.join(shared_socials),
        'review_status': 'needs_manual_review'
    }


def fetch_data(conn):
    with conn.cursor() as cur:
        cur.execute('''
            SELECT p.id, s.code, p.raw_name, p.profile_url, p.city, p.clubs, p.raw_data
              FROM fitness.source_profiles p
              JOIN fitness.sources s ON s.id = p.source_id
             ORDER BY p.id
        ''')
        records = []
        for pid, src, name, url, city, clubs, raw in cur.fetchall():
            data = raw if isinstance(raw, dict) else {}
            fields = get_raw_fields(data)
            if not name:
                name = fields.get('name') or ''
            records.append({'id': int(pid), 'source': str(src), 'name': str(name or ''),
                            'url': str(url or ''), 'city': str(city or ''), 'clubs': str(clubs or ''),
                            'fields': fields})
        cur.execute('SELECT source_profile_id, platform, account_url FROM fitness.profile_socials')
        socials = defaultdict(set)
        for pid, platform, url in cur.fetchall():
            platform = str(platform or '').lower()
            if platform not in SOCIAL_PLATFORMS:
                continue
            normalized = norm_social(platform, url)
            if normalized:
                socials[int(pid)].add(normalized)
        # Extra source URLs are not regarded as verified social accounts.
    return records, socials


def export_csv(path, candidates):
    cols = ('left_id', 'right_id', 'left_source', 'right_source', 'left_name', 'right_name',
            'left_url', 'right_url', 'left_city', 'right_city', 'left_clubs', 'right_clubs',
            'score', 'priority', 'evidence', 'name_similarity', 'shared_socials', 'review_status')
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';')
        w.writeheader()
        w.writerows(candidates)


def export_summary(path, records, candidates, matched_pairs):
    by_priority = Counter(x['priority'] for x in candidates)
    by_source = Counter(x['source'] for x in records)
    no_full_name = sum(len(norm_words(x['name'])) < 2 for x in records)
    summary = {
        'generated_at': datetime.now().isoformat(),
        'source_profiles': len(records),
        'sources': dict(sorted(by_source.items())),
        'profiles_with_incomplete_names': no_full_name,
        'cross_source_candidate_pairs': len(candidates),
        'by_review_priority': dict(by_priority),
        'distinct_profile_ids_in_candidate_pairs': len(matched_pairs),
        'note': 'Scores are a heuristic for human review, NOT probabilities. No source profiles were merged, linked, or deleted.'
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def get_merge_table_shape(conn):
    with conn.cursor() as cur:
        cur.execute('''
            SELECT column_name, is_nullable, column_default, is_identity, data_type
            FROM information_schema.columns
            WHERE table_schema='fitness' AND table_name='merge_candidates'
            ORDER BY ordinal_position
        ''')
        return {r[0]: {'nullable': r[1] == 'YES', 'default': r[2], 'identity': r[3] == 'YES', 'type': r[4]} for r in cur.fetchall()}


def write_candidates(conn, candidates):
    """Write review candidates only when the existing schema is safely compatible."""
    from psycopg import sql
    shape = get_merge_table_shape(conn)
    if not shape:
        raise RuntimeError('fitness.merge_candidates not found; no writes performed')
    left_col = next((x for x in ('left_source_profile_id', 'source_profile_id_1', 'profile_a_id', 'profile1_id', 'left_profile_id') if x in shape), None)
    right_col = next((x for x in ('right_source_profile_id', 'source_profile_id_2', 'profile_b_id', 'profile2_id', 'right_profile_id') if x in shape), None)
    if not left_col or not right_col:
        raise RuntimeError('Unknown merge_candidates pair columns; no writes. Existing columns: ' + ', '.join(shape))
    optional = {}
    for field, choices in {
        'score': ('score', 'confidence_score', 'match_score'),
        'status': ('status', 'review_status'),
        'evidence': ('evidence', 'reasons', 'details'),
    }.items():
        col = next((x for x in choices if x in shape), None)
        if col:
            optional[field] = col
    # Protect against accidental writes to tables with required, unknown columns.
    provided = {left_col, right_col, *optional.values()}
    required_extra = [c for c, d in shape.items() if c not in provided and
                      not d['nullable'] and d['default'] is None and not d['identity']]
    if required_extra:
        raise RuntimeError('merge_candidates requires unsupported columns: ' + ', '.join(required_extra))
    if optional.get('status') and shape[optional['status']]['type'] != 'text' and shape[optional['status']]['type'] != 'character varying':
        raise RuntimeError('Review status column is not text; no writes performed')
    if optional.get('evidence') and shape[optional['evidence']]['type'] not in ('jsonb', 'json', 'text', 'character varying'):
        raise RuntimeError('Evidence column unsupported; no writes performed')
    columns = [left_col, right_col] + list(optional.values())
    # No DELETE/UPDATE: do not overwrite human review decisions. Idempotency via NOT EXISTS.
    stmt = sql.SQL('''INSERT INTO fitness.merge_candidates ({cols})
        SELECT {values} WHERE NOT EXISTS
        (SELECT 1 FROM fitness.merge_candidates WHERE {l}=%s AND {r}=%s)''').format(
        cols=sql.SQL(', ').join(map(sql.Identifier, columns)),
        values=sql.SQL(', ').join(sql.Placeholder() for _ in columns),
        l=sql.Identifier(left_col), r=sql.Identifier(right_col))
    inserted = 0
    with conn.transaction():
        with conn.cursor() as cur:
            for row in candidates:
                a, b = row['left_id'], row['right_id']
                values = [a, b]
                for key in optional:
                    col = optional[key]
                    if key == 'score':
                        values.append(row['score'])
                    elif key == 'status':
                        values.append('pending')
                    else:
                        evidence = {'reasons': row['evidence'].split(','), 'source': 'fitness_dedup_v1',
                                    'shared_socials': row['shared_socials'], 'score': row['score']}
                        values.append(json.dumps(evidence, ensure_ascii=False) if shape[col]['type'] in ('jsonb', 'json') else json.dumps(evidence, ensure_ascii=False))
                cur.execute(stmt, values + [a, b])
                inserted += cur.rowcount
    return inserted


def main():
    ap = argparse.ArgumentParser(description='Review-only cross-source deduplication (no merges)')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=15432)
    ap.add_argument('--dbname', default='workoutplan')
    ap.add_argument('--user', default='workoutplan_test')
    ap.add_argument('--output', default='.', help='Report directory')
    ap.add_argument('--min-score', type=int, default=48, choices=range(0, 101), metavar='0..100')
    ap.add_argument('--write-candidates', action='store_true', help='Optional DB insert after explicit approval; never merges trainer records')
    args = ap.parse_args()
    import psycopg
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    # libpq uses Windows pgpass.conf automatically; never print credentials.
    with psycopg.connect(host=args.host, port=args.port, dbname=args.dbname,
                         user=args.user, connect_timeout=10, options='-c statement_timeout=120000') as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database(), current_user')
            print('Подключение:', cur.fetchone(), flush=True)
        records, socials = fetch_data(conn)
        index = {x['id']: x for x in records}
        pairs = shortlist(records, socials)
        matches = []
        for a, b in pairs:
            candidate = compare(index[a], index[b], socials)
            if candidate and candidate['score'] >= args.min_score:
                matches.append(candidate)
        matches.sort(key=lambda x: (-x['score'], x['left_id'], x['right_id']))
        if len(matches) > PAIR_LIMIT:
            print(f'Внимание: ограничение отчёта: {PAIR_LIMIT} из {len(matches)} кандидатов')
            matches = matches[:PAIR_LIMIT]
        csv_path = out / 'fitness_merge_candidates_review.csv'
        summary_path = out / 'fitness_dedup_summary.json'
        export_csv(csv_path, matches)
        summary = export_summary(summary_path, records, matches, {r[k] for r in matches for k in ('left_id','right_id')})
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print('CSV:', csv_path)
        print('JSON:', summary_path)
        if args.write_candidates:
            inserted = write_candidates(conn, matches)
            print(f'Записано в fitness.merge_candidates (новых кандидатов): {inserted}. Объединений не выполнялось.')
        else:
            print('РЕЖИМ ПРОСМОТРА: PostgreSQL не изменялась. Для записи кандидатов нужен --write-candidates.')

if __name__ == '__main__':
    main()
