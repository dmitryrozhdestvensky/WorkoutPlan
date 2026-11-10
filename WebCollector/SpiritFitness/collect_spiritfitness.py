#!/usr/bin/env python3
"""Spirit Fitness public trainer profiles -> local SQLite + CSV.

Safe by default: no writes to existing Excel, no DaData API calls, no auto-merge.
"""
import argparse
import csv
import datetime as dt
import shutil
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'spiritfitness.sqlite3'
CSV = ROOT / 'spiritfitness_trainers.csv'
ERRORS = ROOT / 'spiritfitness_errors.csv'
CITY_PAGES = {
    'Москва': 'https://spiritfit.ru/coaches/',
    'Санкт-Петербург': 'https://spiritfit.ru/spb/coaches/',
    'Екатеринбург': 'https://spiritfit.ru/ekb/coaches/',
}
REGION = {'Москва': '', 'Санкт-Петербург': 'spb', 'Екатеринбург': 'ekb'}
BAD_TITLES = ('страница не найдена', '404', 'not found', 'page not found', 'доступ запрещён')
FIELDS = ['name','city','role','clubs','specialty','vk','ok','dzen','telegram','instagram','tiktok','tenchat',
          'source','source_profile_url','source_catalog_url','collected_at','status','raw_name','normalized_name',
          'source_profile_id']
SNETWORKS = {'vk':('vk.com','m.vk.com'), 'ok':('ok.ru',), 'dzen':('dzen.ru',),
             'telegram':('t.me','telegram.me'), 'instagram':('instagram.com','www.instagram.com'),
             'tiktok':('tiktok.com','www.tiktok.com'), 'tenchat':('tenchat.ru',)}


def clean_url(url):
    try:
        p=urlsplit(url)
        if p.scheme.lower() not in ('https','http') or not p.hostname:
            return ''
        host=p.hostname.lower()
        if host.startswith('www.spiritfit.ru'): host='spiritfit.ru'
        path=re.sub(r'/+', '/', p.path)
        if path != '/': path=path.rstrip('/') + '/'
        return urlunsplit(('https',host,path,'',''))
    except Exception: return ''


def trainer_url(url, city=None):
    """Canonicalize a trainer URL using the source catalog's region.

    Some regional listings use absolute /coaches/ links missing /spb/ or
    /ekb/. They must be resolved within the listing's region.
    """
    u = clean_url(url)
    if not u:
        return ''
    p = urlsplit(u)
    if p.hostname != 'spiritfit.ru':
        return ''
    m = re.fullmatch(r'/(?:([a-z]{2,4})/)?coaches/([^/]+)/', p.path)
    if not m:
        return ''
    prefix, slug = m.groups()
    if slug.lower() in {'specialization', 'club', 'training', 'search', 'filter'}:
        return ''
    target_region = REGION.get(city) if city else None
    if city and target_region is None:
        return ''
    # A regional listing owns its individual trainer URLs. Replace a missing
    # or inconsistent region prefix with the region of that listing.
    region = target_region if city else (prefix or '')
    path = f'/{region + "/" if region else ""}coaches/{slug}/'
    return f'https://spiritfit.ru{path}'


def valid_profile_name(value):
    name = ' '.join((value or '').split())
    if not name or len(name) > 110:
        return False
    low = name.casefold()
    if any(bad in low for bad in BAD_TITLES):
        return False
    if low.startswith(('тренеры', 'тренировки', 'ошибка', 'страница', 'error')):
        return False
    # Name should be 2-4 words rather than a generic navigation title.
    words = name.split()
    return 2 <= len(words) <= 4 and all(re.search(r'[а-яёa-z]', w, re.I) for w in words)


def normalized_name(name):
    # Local comparison key only. Never overwrite the public name.
    words=re.findall(r'[а-яёa-z-]+', (name or '').lower())
    return ' '.join(sorted(w.replace('ё','е') for w in words))


def connect():
    db=sqlite3.connect(DB)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS source_profiles (
      url TEXT PRIMARY KEY, source TEXT NOT NULL, name TEXT, city TEXT, role TEXT, clubs TEXT,
      specialty TEXT, socials_json TEXT, catalog_url TEXT, raw_name TEXT, normalized_name TEXT,
      raw_text TEXT, discovered_at TEXT NOT NULL, collected_at TEXT, status TEXT NOT NULL DEFAULT 'queued'
    );
    CREATE TABLE IF NOT EXISTS source_occurrences (
      url TEXT NOT NULL, catalog_url TEXT NOT NULL, city TEXT NOT NULL, discovered_at TEXT NOT NULL,
      PRIMARY KEY(url,catalog_url)
    );
    CREATE TABLE IF NOT EXISTS crawl_errors (
      id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, stage TEXT, message TEXT, happened_at TEXT
    );
    ''')
    db.commit()
    return db


def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def error(db,url,stage,message):
    db.execute('INSERT INTO crawl_errors(url,stage,message,happened_at) VALUES(?,?,?,?)',
               (url,stage,str(message)[:600],now()))
    db.commit()
    print('  ERROR',stage,url,str(message)[:140],flush=True)


def discover(db,url,city,catalog):
    db.execute('INSERT OR IGNORE INTO source_profiles(url,source,city,catalog_url,discovered_at) VALUES(?,?,?,?,?)',
               (url,'Spirit Fitness',city,catalog,now()))
    db.execute('INSERT OR IGNORE INTO source_occurrences(url,catalog_url,city,discovered_at) VALUES(?,?,?,?)',
               (url,catalog,city,now()))


def get_listing_links(page, city):
    # Prefer genuine profile cards rather than every navigation hyperlink.
    hrefs = page.locator('a[href]').evaluate_all("""els => els.filter(a =>
        (a.innerText || '').includes('Подробнее') ||
        (a.querySelector('img') && a.closest('article'))
    ).map(a => a.href)""")
    if not hrefs:
        hrefs = page.locator('a[href]').evaluate_all('(els) => els.map(a => a.href)')
    out = []
    seen = set()
    for href in hrefs:
        u = trainer_url(href, city)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def dismiss_blocking_banner(page):
    """Attempt normal dismissal of a known popup, never force-click through."""
    modal = page.locator('#banner.popup-modal__container')
    try:
        if not modal.count() or not modal.first.is_visible():
            return True
        for selector in (
            'button[aria-label*="закры"]', 'button[aria-label*="Закры"]',
            'button[aria-label*="close"]', '.popup-modal__close',
            '[data-fancybox-close]', 'button.close', '.modal-close',
        ):
            button = modal.locator(selector).first
            if button.count() and button.is_visible():
                button.click(timeout=2500)
                page.wait_for_timeout(200)
                if not modal.first.is_visible():
                    return True
        page.keyboard.press('Escape')
        page.wait_for_timeout(250)
        return not modal.first.is_visible()
    except Exception:
        return False


def check_robots(base, user_agent='FitnessTrainerResearchBot'):
    # Fail closed on technical errors; do not treat inaccessible robots as permission.
    from urllib.parse import urlsplit
    domain=urlsplit(base).netloc
    robots=f'https://{domain}/robots.txt'
    try:
        req=Request(robots, headers={'User-Agent': user_agent})
        with urlopen(req,timeout=15) as res:
            if res.status != 200:
                return False, f'robots HTTP {res.status}'
            body=res.read(200000).decode('utf-8','replace')
        rp=RobotFileParser();rp.parse(body.splitlines())
        return rp.can_fetch(user_agent,base), 'robots allowed' if rp.can_fetch(user_agent,base) else 'robots disallow'
    except Exception as exc:
        return False, f'robots check unavailable: {type(exc).__name__}: {exc}'


def body_text(page):
    try: return page.locator('main').first.inner_text(timeout=4000)
    except Exception:
        try:return page.locator('h1').first.inner_text(timeout=2000)
        except Exception:return ''


def parse_profile(page, url, city, catalog, response=None):
    if response is not None and response.status >= 400:
        raise ValueError(f'HTTP {response.status}: {url}')
    if urlsplit(page.url).hostname not in ('spiritfit.ru', 'www.spiritfit.ru'):
        raise ValueError('Unexpected redirect domain: ' + page.url)
    h1 = ' '.join(page.locator('h1').first.inner_text(timeout=9000).split())
    if not valid_profile_name(h1):
        raise ValueError('Invalid trainer heading: ' + h1[:100])
    headings = page.locator('h2').all_inner_texts()
    role = ''
    for heading in headings:
        heading = ' '.join(heading.split())
        if heading and heading.lower() != 'клубы' and not heading.lower().startswith(('наши ', 'фитнес специализации')):
            role = heading
            break
    clubs = []
    try:
        clubs = page.evaluate('''() => {
          const h=[...document.querySelectorAll('h1,h2,h3')].find(e=>e.textContent.trim().toLowerCase()==='клубы');
          if(!h) return [];
          let out=[], p=h.nextElementSibling, n=0;
          while(p && n++<5 && !/^H[123]$/.test(p.tagName)) {
            const t=(p.innerText||'').trim();
            if(t && t.length<180) out.push(t);
            p=p.nextElementSibling;
          }
          return out;
        }''')
    except Exception:
        pass
    clubs = [c for c in clubs if c and 'Записаться' not in c]
    clubs = '; '.join(dict.fromkeys(' '.join(c.split()) for c in clubs))[:400]
    # A legitimate profile needs more than a plausible name. On Spirit's
    # individual trainer pages a role appears below H1.
    if not role or not re.search(r'тренер|инструктор|coach', role, re.I):
        raise ValueError('Missing trainer role, possible error page: ' + h1)
    socials = {k: '' for k in SNETWORKS}
    raw = body_text(page)
    if not raw:
        raw = h1 + '\n' + role + '\n' + clubs
    return {'name': h1, 'city': city, 'role': role, 'clubs': clubs, 'specialty': '',
            'socials': socials, 'source': 'Spirit Fitness', 'source_profile_url': url,
            'source_catalog_url': catalog, 'raw_name': h1, 'normalized_name': normalized_name(h1),
            'raw_text': raw[:15000], 'collected_at': now(), 'status': 'collected'}


def backup_db(db):
    folder = ROOT / 'Backups'
    folder.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    path = folder / f'spiritfitness_before_repair_{stamp}.sqlite3'
    dst = sqlite3.connect(path)
    try:
        db.backup(dst)
    finally:
        dst.close()
    return path


def repair_db(db):
    """Migrate old misregionalized URLs; quarantine bogus saved page titles.

    No rows are deleted. Superseded URLs and past occurrences remain for audit.
    Idempotent; the first run creates a full SQLite backup.
    """
    backup = backup_db(db)
    counts = {'quarantined': 0, 'requeued_regional': 0, 'added_urls': 0}
    db.execute('BEGIN IMMEDIATE')
    try:
        for url, name in db.execute("SELECT url,name FROM source_profiles WHERE status='collected'").fetchall():
            if not valid_profile_name(name):
                db.execute("UPDATE source_profiles SET status='invalid_page' WHERE url=?", (url,))
                counts['quarantined'] += 1
        rows = db.execute("""SELECT p.url,p.city,p.catalog_url,p.status
                             FROM source_profiles p WHERE p.status != 'superseded'""").fetchall()
        for url, city, catalog, status in rows:
            if city not in ('Санкт-Петербург', 'Екатеринбург'):
                continue
            target = trainer_url(url, city)
            if not target or target == url:
                continue
            cur = db.execute("""INSERT OR IGNORE INTO source_profiles
                (url,source,city,catalog_url,discovered_at,status)
                VALUES (?, 'Spirit Fitness', ?, ?, ?, 'queued')""",
                (target, city, catalog, now()))
            counts['added_urls'] += max(cur.rowcount, 0)
            occurrences = db.execute('SELECT catalog_url,city,discovered_at FROM source_occurrences WHERE url=?', (url,)).fetchall()
            for cat, occurrence_city, seen in occurrences:
                db.execute('INSERT OR IGNORE INTO source_occurrences(url,catalog_url,city,discovered_at) VALUES(?,?,?,?)',
                           (target, cat, occurrence_city, seen))
            db.execute("UPDATE source_profiles SET status='superseded' WHERE url=?", (url,))
            counts['requeued_regional'] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    print('BACKUP:', backup)
    print('REPAIR:', counts)
    print('Nothing deleted; old URLs retained as superseded/invalid_page.')
    return counts


def write_csv(db):
    rows=db.execute("SELECT url,name,city,role,clubs,specialty,socials_json,catalog_url,collected_at,status,raw_name,normalized_name FROM source_profiles WHERE status='collected' AND name IS NOT NULL AND TRIM(name)<>'' ORDER BY url").fetchall()
    temp=CSV.with_suffix('.csv.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=';');w.writeheader()
        for url,name,city,role,clubs,specialty,js,catalog,collected,status,raw,normalized in rows:
            socials=json.loads(js or '{}')
            row=dict(name=name,city=city,role=role,clubs=clubs,specialty=specialty,
                     source='Spirit Fitness',source_profile_url=url,source_catalog_url=catalog,
                     collected_at=collected,status=status,raw_name=raw,normalized_name=normalized,
                     source_profile_id=urlsplit(url).path.strip('/').split('/')[-1])
            row.update({k:socials.get(k,'') for k in SNETWORKS})
            w.writerow(row)
    temp.replace(CSV)
    with ERRORS.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['url','stage','message','happened_at'])
        w.writerows(db.execute('SELECT url,stage,message,happened_at FROM crawl_errors ORDER BY id'))
    return len(rows)


def main():
    ap=argparse.ArgumentParser(description='Collect public Spirit Fitness trainer profiles (read-only source collection).')
    ap.add_argument('--max-profiles',type=int,default=10,help='New profiles this run; 0 for unlimited')
    ap.add_argument('--max-clicks',type=int,default=3,help='Show more clicks per city; 0 for unlimited')
    ap.add_argument('--cities',default='all',help='all, msk, spb, ekb (comma separated)')
    ap.add_argument('--show-browser',action='store_true')
    ap.add_argument('--delay',type=float,default=1.2)
    ap.add_argument('--export-only',action='store_true')
    ap.add_argument('--repair-db',action='store_true',help='Backup and repair old regional URLs/statuses; no website requests')
    ap.add_argument('--resume-queue',action='store_true',help='Process known queued URLs without rediscovering catalogs')
    ap.add_argument('--allow-without-robots',action='store_true',help='ONLY after independently verifying that robots access is permitted')
    args=ap.parse_args()
    db=connect()
    if args.repair_db:
        repair_db(db)
        print('EXPORT:',write_csv(db),'profiles; CSV:',CSV)
        return
    if args.export_only:
        print('EXPORT:',write_csv(db),'profiles; CSV:',CSV);return
    selected=[]
    codes={'msk':'Москва','spb':'Санкт-Петербург','ekb':'Екатеринбург'}
    for code in args.cities.lower().split(','):
        code=code.strip()
        if code=='all':selected=list(CITY_PAGES);break
        if code not in codes:ap.error('Unknown city code: '+code)
        if codes[code] not in selected:selected.append(codes[code])
    for city in selected:
        permitted,detail=check_robots(CITY_PAGES[city])
        if not permitted and not args.allow_without_robots:
            error(db,CITY_PAGES[city],'robots',detail)
            print('STOP: robots not confirmed for',city,'. Do not bypass site restrictions.')
            return
    done = 0
    skipped = 0
    discovered_total = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.show_browser)
            context = browser.new_context(locale='ru-RU', viewport={'width': 1280, 'height': 900},
                                          user_agent='FitnessTrainerResearchBot/1.0 (+public directory research)')
            page = context.new_page()
            all_links = {}
            if args.resume_queue:
                for url, city, catalog in db.execute("SELECT url,city,catalog_url FROM source_profiles WHERE status='queued' ORDER BY discovered_at,url"):
                    if city in selected:
                        all_links[url] = (city, catalog)
                print('RESUME QUEUE:', len(all_links), flush=True)
            else:
                for city in selected:
                    catalog = CITY_PAGES[city]
                    print('CATALOG', city, catalog, flush=True)
                    try:
                        page.goto(catalog, wait_until='domcontentloaded', timeout=45000)
                        page.wait_for_timeout(1400)
                        stalls = 0
                        clicks = 0
                        last_links = set()
                        while True:
                            links = get_listing_links(page, city)
                            current = set(links)
                            for u in links:
                                discover(db, u, city, catalog)
                                all_links[u] = (city, catalog)
                            db.commit()
                            added = len(current - last_links)
                            print(f'  links={len(links)} (+{added}) clicks={clicks}', flush=True)
                            if args.max_clicks and clicks >= args.max_clicks:
                                break
                            button = page.get_by_role('button', name=re.compile('Показать еще', re.I))
                            if button.count() == 0 or not button.first.is_visible():
                                break
                            if not dismiss_blocking_banner(page):
                                error(db, catalog, 'show_more', 'Blocking popup could not be dismissed')
                                break
                            try:
                                button.first.scroll_into_view_if_needed(timeout=6000)
                                button.first.click(timeout=8000)
                                page.wait_for_timeout(1600)
                            except Exception as exc:
                                error(db, catalog, 'show_more', exc)
                                break
                            after = set(get_listing_links(page, city))
                            stalls = stalls + 1 if not (after - current) else 0
                            clicks += 1
                            if stalls >= 3:
                                print('  STOP: no new URLs in three clicks')
                                break
                            last_links = current
                            time.sleep(max(args.delay, 0))
                    except Exception as exc:
                        error(db, catalog, 'catalog', exc)
                # Add old queue entries too; discovery may stop early due to a popup.
                for url, city, catalog in db.execute("SELECT url,city,catalog_url FROM source_profiles WHERE status='queued' ORDER BY discovered_at,url"):
                    if city in selected:
                        all_links.setdefault(url, (city, catalog))
            discovered_total = len(all_links)
            print('Discovered / queued URLs:', discovered_total)
            for url, (city, catalog) in all_links.items():
                if args.max_profiles and done >= args.max_profiles:
                    break
                status = db.execute('SELECT status FROM source_profiles WHERE url=?', (url,)).fetchone()
                if status and status[0] == 'collected':
                    skipped += 1
                    continue
                if status and status[0] != 'queued':
                    continue
                try:
                    response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    page.wait_for_timeout(450)
                    record = parse_profile(page, url, city, catalog, response)
                    db.execute("""UPDATE source_profiles SET name=?,city=?,role=?,clubs=?,specialty=?,
                      socials_json=?,catalog_url=?,raw_name=?,normalized_name=?,raw_text=?,collected_at=?,status=? WHERE url=?""",
                      (record['name'],record['city'],record['role'],record['clubs'],record['specialty'],
                       json.dumps(record['socials'],ensure_ascii=False),catalog,record['raw_name'],
                       record['normalized_name'],record['raw_text'],record['collected_at'],'collected',url))
                    db.commit()
                    done += 1
                    print(f'[{done}] {record["name"]} | {city} | {record["role"]} | {record["clubs"][:70]}',flush=True)
                except Exception as exc:
                    error(db, url, 'profile', exc)
                    # Deterministically invalid pages are quarantined; network
                    # and timeout failures stay queued for a later retry.
                    if isinstance(exc, ValueError) and (str(exc).startswith(('HTTP 404:', 'HTTP 410:', 'Invalid trainer heading:', 'Missing trainer role'))):
                        db.execute("UPDATE source_profiles SET status='invalid_page' WHERE url=? AND status='queued'", (url,))
                        db.commit()
                time.sleep(max(args.delay, 0))
            context.close()
            browser.close()
    finally:
        # Also executes for Ctrl+C, so CSV catches up with committed SQLite rows.
        count = write_csv(db)
        print(f'ГОТОВО: открыто новых анкет {done}; пропущено {skipped}; всего анкет CSV {count}; URL в запуске {discovered_total}')
    print('CSV:',CSV,'\nSQLite:',DB,'\nErrors:',ERRORS)
    print('Основной Excel не изменён. Совпадения ФИО НЕ объединялись. DaData API НЕ вызывался.')

if __name__=='__main__':main()
