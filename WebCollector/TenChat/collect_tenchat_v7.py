"""TenChat public resume catalogue sampler V7, Windows/Python 3.10+.

Reads only public catalogue cards in visible Playwright browser. No auth, no
private endpoints, no bypasses. Resumable SQLite state, CSV exports.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DB = ROOT / "collection_state.sqlite3"
OUT = ROOT / "tenchat_trainers_v7.csv"
PAGES_OUT = ROOT / "tenchat_pages_v7.csv"
BASE = "https://tenchat.ru"
PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SKIP = {"feed", "connect", "vacancy", "partners", "plus", "business", "resume", "company", "docs", "contacts", "wallet", "search", "login", "registration", "settings"}

# Limit extraction to the catalogue's heading -> next section, avoiding post authors.
EXTRACT_JS = r"""(profession) => {
  const headings = [...document.querySelectorAll('h1,h2,h3,h4')];
  const normalize = s => (s || '').replace(/\s+/g,' ').trim().toLowerCase();
  const start = headings.find(h => {
    const s = normalize(h.innerText);
    return s.startsWith(normalize(profession)) && /\d/.test(s);
  });
  if (!start) return {valid:false, profiles:[], buttons:0, cities:[]};
  const end = headings.find(h =>
    !!(start.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING) &&
    /последние посты|часто задаваемые|похожие профессии/i.test(h.innerText || '')
  );
  const reserved = new Set(['feed','connect','vacancy','partners','plus','business','resume','company','docs','contacts','wallet','search','login','registration','settings']);
  const profiles = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    if (!(start.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
    if (end && !(a.compareDocumentPosition(end) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
    let u; try { u = new URL(a.getAttribute('href'), location.origin); } catch {continue;}
    if (u.hostname !== 'tenchat.ru' && u.hostname !== 'www.tenchat.ru') continue;
    const parts=u.pathname.split('/').filter(Boolean);
    if (parts.length !== 1 || reserved.has(parts[0].toLowerCase()) || !/^[A-Za-z0-9_.-]+$/.test(parts[0])) continue;
    const name=(a.innerText || '').replace(/\s+/g,' ').trim();
    if (!name || name.length > 130) continue;
    profiles.set(parts[0].toLowerCase(), {name, url:'https://tenchat.ru/'+parts[0]});
  }
  const cities = new Set();
  const slug = location.pathname.split('/').pop();
  document.querySelectorAll('a[href*="/resume/"]').forEach(a => {
    let u; try {u = new URL(a.href,location.origin)}catch{return}
    if (u.hostname !== 'tenchat.ru') return;
    const m = u.pathname.match(/^\/resume\/([a-z0-9-]+)\/([a-z0-9-]+)\/?$/);
    if (m && m[2] === slug) cities.add(m[1]);
  });
  return {valid:true,profiles:[...profiles.values()],cities:[...cities]};
}"""

# We select the button associated with the catalogue only, never FAQ or posts.
CLICK_JS = r"""(profession) => {
 const norm=s=>(s||'').replace(/\s+/g,' ').trim().toLowerCase();
 const buttons=[...document.querySelectorAll('button')].filter(b =>
   /показать\s+ещ[её]/i.test(b.innerText||'') && b.getClientRects().length>0 && !b.disabled);
 const desired=norm(profession);
 const matches=buttons.filter(b => {
   const ctx=norm(b.parentElement?.parentElement?.innerText||'');
   return ctx.includes(desired) && !/часто задаваемые вопросы/.test(ctx.slice(0,150));
 });
 if(!matches.length) return false;
 matches[0].scrollIntoView({block:'center'});
 matches[0].click();
 return true;
}"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(s):
    s = str(s or "").replace("\x00", "").strip()
    # Do not interpret user-provided names as Excel formulas.
    return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s


def norm_url(raw):
    try:
        u = urlparse(str(raw or "").strip())
        name = u.path.strip("/")
        if u.hostname not in ("tenchat.ru", "www.tenchat.ru") or not PROFILE_RE.fullmatch(name) or name.lower() in SKIP:
            return ""
        return "https://tenchat.ru/" + name.lower()
    except (ValueError, TypeError):
        return ""


def db_init(cx):
    cx.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS pages (
      path TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      cards INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0,
      error TEXT, checked_at TEXT
    );
    CREATE TABLE IF NOT EXISTS trainers (
      url TEXT PRIMARY KEY, name TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sightings (
      url TEXT NOT NULL, page_path TEXT NOT NULL, specialty TEXT NOT NULL,
      PRIMARY KEY(url,page_path)
    );
    """)
    cx.commit()


def add_page(cx, path):
    if not re.fullmatch(r"/resume/[a-z0-9-]+/[a-z0-9-]+", path):
        return
    cx.execute("INSERT OR IGNORE INTO pages(path) VALUES (?)", (path,))


def export(cx):
    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["Имя", "TenChat", "Специализации", "Страницы-источники", "Дата сбора", "Статус проверки"])
        query = """SELECT t.name,t.url, GROUP_CONCAT(DISTINCT s.specialty), GROUP_CONCAT(DISTINCT s.page_path),t.first_seen
          FROM trainers t LEFT JOIN sightings s ON s.url=t.url GROUP BY t.url ORDER BY t.url"""
        for name,url,profs,pages,first in cx.execute(query):
            w.writerow([clean(name),url,clean((profs or "").replace(",", " | ")),
              clean(" | ".join(BASE+p for p in (pages or "").split(",") if p)),first,
              "Найдена в открытом каталоге; владелец не подтверждён"])
    tmp.replace(OUT)
    tmp=PAGES_OUT.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['Каталог','Статус','Попыток','Карточек','Нажатий','Ошибка','Дата'])
        w.writerows(cx.execute('SELECT path,status,attempts,cards,clicks,error,checked_at FROM pages ORDER BY path'))
    tmp.replace(PAGES_OUT)


def load_seed(cx, specs):
    cities=[]
    for line in (ROOT/'cities_100.txt').read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        m=re.fullmatch(r'/resume/([a-z0-9-]+)/trener-po-fitnesu',line)
        if m: cities.append(m.group(1))
    for city in dict.fromkeys(cities):
        for spec in specs:
            add_page(cx, f"/resume/{city}/{spec['slug']}")
    cx.commit()
    return len(set(cities))


def main():
    p=argparse.ArgumentParser(description='Сбор открытых анкет TenChat с сохранением прогресса')
    p.add_argument('--max-pages',type=int,default=250,help='Максимум страниц за один запуск (по умолчанию 250)')
    p.add_argument('--max-clicks',type=int,default=20)
    p.add_argument('--headless',action='store_true',help='Без видимого окна (по умолчанию окно видно)')
    p.add_argument('--retry-errors',action='store_true')
    args=p.parse_args()
    specs=[s for s in json.loads((ROOT/'specialties.json').read_text(encoding='utf-8')) if s.get('enabled')]
    if not specs: raise SystemExit('Нет включенных специальностей в specialties.json')
    labels={s['slug']:s['label'] for s in specs}
    with sqlite3.connect(DB) as cx:
        db_init(cx)
        seeded=load_seed(cx,specs)
        if args.retry_errors: cx.execute("UPDATE pages SET status='pending' WHERE status='error'")
        cx.commit()
        rows=cx.execute("SELECT path FROM pages WHERE status='pending' ORDER BY CASE WHEN path LIKE '%/trener-po-fitnesu' THEN 0 ELSE 1 END,path LIMIT ?",(args.max_pages,)).fetchall()
        print(f'Городов в начальном списке: {seeded}; профессий: {len(specs)}; страниц в текущем запуске: {len(rows)}',flush=True)
        if not rows:
            export(cx)
            print('Новых страниц нет. Для повторной проверки используйте новую базу/список городов.');return
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=args.headless)
            context=browser.new_context(locale='ru-RU',viewport={'width':1360,'height':900})
            page=context.new_page()
            try:
                for i,(path,) in enumerate(rows,1):
                    slug=path.rsplit('/',1)[-1]
                    label=labels.get(slug,slug)
                    try:
                        resp=page.goto(BASE+path,wait_until='domcontentloaded',timeout=45000)
                        page.wait_for_timeout(1200)
                        if resp and resp.status in (403,429):
                            print(f'HTTP {resp.status}: прекращаем, не обходим ограничения',flush=True)
                            break
                        if 'captcha' in page.url.lower():
                            print('Страница проверки доступа; прекращаем работу',flush=True);break
                        result=page.evaluate(EXTRACT_JS,label)
                        # Don't mark unsupported specializations as successfully collected.
                        if not result['valid']:
                            cx.execute('UPDATE pages SET status=?,attempts=attempts+1,error=?,checked_at=? WHERE path=?',
                                ('no_catalog','Не найден заголовок нужной профессии',now(),path))
                            cx.commit(); print(f'[{i}/{len(rows)}] {path}: каталог не найден');continue
                        profiles={}
                        def consume(result):
                            for item in result['profiles']:
                                url=norm_url(item.get('url'))
                                if url: profiles[url]=clean(item.get('name'))
                        consume(result)
                        clicks=0
                        stalled=0
                        for j in range(args.max_clicks):
                            before=len(profiles)
                            if not page.evaluate(CLICK_JS,label):break
                            clicks+=1
                            page.wait_for_timeout(1100)
                            consume(page.evaluate(EXTRACT_JS,label))
                            if len(profiles)==before:
                                page.wait_for_timeout(1000)
                                consume(page.evaluate(EXTRACT_JS,label))
                            stalled=stalled+1 if len(profiles)==before else 0
                            if stalled>=3:break
                        stamp=now()
                        new=0
                        for url,name in profiles.items():
                            if cx.execute('SELECT 1 FROM trainers WHERE url=?',(url,)).fetchone() is None:new+=1
                            cx.execute('INSERT INTO trainers(url,name,first_seen,last_seen) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen',
                                (url,name,stamp,stamp))
                            cx.execute('INSERT OR IGNORE INTO sightings(url,page_path,specialty) VALUES(?,?,?)',(url,path,label))
                        # Add only same-profession city catalogue URLs visible on this page.
                        for city in result['cities']:
                            add_page(cx,f'/resume/{city}/{slug}')
                        cx.execute('UPDATE pages SET status=?,attempts=attempts+1,cards=?,clicks=?,error=NULL,checked_at=? WHERE path=?',
                            ('done',len(profiles),clicks,stamp,path))
                        cx.commit();export(cx)
                        count=cx.execute('SELECT COUNT(*) FROM trainers').fetchone()[0]
                        print(f'[{i}/{len(rows)}] {path}: {len(profiles)} карточек, {clicks} нажатий, +{new}; уникальных URL {count}',flush=True)
                        time.sleep(random.uniform(1.5,2.8))
                    except KeyboardInterrupt:
                        print('Остановлено пользователем; сохранённые данные остаются');break
                    except Exception as e:
                        cx.execute('UPDATE pages SET status=?,attempts=attempts+1,error=?,checked_at=? WHERE path=?',
                            ('error',str(e)[:400],now(),path))
                        cx.commit();export(cx)
                        print(f'[{i}/{len(rows)}] ошибка {path}: {str(e)[:150]}',flush=True)
                        time.sleep(3)
            finally:
                context.close();browser.close()
        export(cx)
        total=cx.execute('SELECT COUNT(*) FROM trainers').fetchone()[0]
        done=cx.execute("SELECT COUNT(*) FROM pages WHERE status='done'").fetchone()[0]
        remaining=cx.execute("SELECT COUNT(*) FROM pages WHERE status='pending'").fetchone()[0]
        print(f'ГОТОВО: {total} URL; страниц завершено {done}; ещё в очереди {remaining}. CSV: {OUT.name}',flush=True)

if __name__=='__main__':main()
