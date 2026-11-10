"""DDX Fitness public coach catalog collector. Python 3.13 + Playwright."""
from __future__ import annotations
import argparse, csv, json, re, sqlite3, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
CATALOG = 'https://www.ddxfitness.ru/coaches/'
DB = HERE / 'ddxfitness_progress.sqlite3'
OUT = HERE / 'ddxfitness_trainers.csv'
ERRORS = HERE / 'ddxfitness_errors.csv'
FIELDS = ['name','city','role','specialty','clubs','experience_years','education','vk','ok','dzen','telegram','instagram','tiktok','tenchat','source','source_profile_url','source_catalog_url','date_collected','status']
PROFILE_RE = re.compile(r'^/coaches/(\d+)/?$')
SOCIAL_DOMAINS = {'vk.com':'vk','m.vk.com':'vk','ok.ru':'ok','dzen.ru':'dzen','t.me':'telegram','telegram.me':'telegram','instagram.com':'instagram','www.instagram.com':'instagram','tiktok.com':'tiktok','www.tiktok.com':'tiktok','tenchat.ru':'tenchat'}


def profile_url(url):
    u = urlparse(urljoin(CATALOG, url))
    if u.hostname not in ('ddxfitness.ru','www.ddxfitness.ru') or not PROFILE_RE.fullmatch(u.path):
        return None
    return f'https://www.ddxfitness.ru{u.path.rstrip("/")}/'


def init_db(db):
    db.execute('CREATE TABLE IF NOT EXISTS profiles (url TEXT PRIMARY KEY, payload TEXT NOT NULL, scraped_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS errors (url TEXT, error TEXT, at TEXT)')
    db.commit()


def save_profile(db, result):
    db.execute('INSERT OR REPLACE INTO profiles(url,payload,scraped_at) VALUES (?,?,?)', (result['source_profile_url'],json.dumps(result,ensure_ascii=False),datetime.now().isoformat(timespec='seconds')))
    db.commit()


def log_error(db, url, msg):
    db.execute('INSERT INTO errors VALUES (?,?,?)',(url,str(msg)[:1000],datetime.now().isoformat(timespec='seconds')))
    db.commit()
    print('ОШИБКА:',url,str(msg)[:170],flush=True)


def export(db):
    records = [json.loads(r[0]) for r in db.execute('SELECT payload FROM profiles ORDER BY url')]
    with OUT.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=';',extrasaction='ignore');w.writeheader();w.writerows(records)
    with ERRORS.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['url','error','at']);w.writerows(db.execute('SELECT url,error,at FROM errors ORDER BY at'))
    return len(records)


def collect_links(page):
    values = page.locator('a[href]').evaluate_all('(nodes) => nodes.map(n => n.href)')
    return {link for v in values if (link := profile_url(v))}


def dismiss_cookies(page):
    for text in ('Принять все','Принять','Согласен','Хорошо'):
        btn=page.get_by_role('button',name=re.compile('^'+re.escape(text)+'$',re.I))
        try:
            if btn.count() and btn.first.is_visible(timeout=800):
                btn.first.click(timeout=2500)
                page.wait_for_timeout(300)
                return True
        except Exception:
            continue
    return False


def expand_catalog(page,max_clicks,delay):
    links=collect_links(page)
    print('Каталог: первоначально уникальных ссылок',len(links),flush=True)
    failed=0
    for step in range(1,max_clicks+1):
        dismiss_cookies(page)
        # Button is identified by both its element type and text, not by a brittle CSS module hash.
        btn=page.get_by_role('button',name=re.compile(r'показать\s+ещ[её]',re.I))
        if not btn.count():
            print('Кнопка «Показать еще» исчезла — конец доступной выдачи',flush=True)
            break
        # Prefer visible and enabled button; no forced clicks or hidden API calls.
        visible=None
        for i in range(min(btn.count(),5)):
            candidate=btn.nth(i)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    visible=candidate;break
            except Exception: pass
        if visible is None:
            print('Кнопка существует, но сейчас недоступна',flush=True)
            break
        before=len(links)
        try:
            visible.scroll_into_view_if_needed(timeout=6000)
            visible.click(timeout=12000)
            # Wait for the actual arrival of new cards, not merely a network-idle event.
            try:
                page.wait_for_function('''(old) => {
                  const u = new Set([...document.querySelectorAll('a[href]')]
                     .map(a => { try { return new URL(a.href).pathname; } catch(e) { return ''; } })
                     .filter(p => /^\\/coaches\\/\\d+\\/?$/.test(p)));
                  return u.size > old;
                }''', arg=before, timeout=12000)
            except PWTimeout: pass
            page.wait_for_timeout(delay)
            links |= collect_links(page)
            delta=len(links)-before
            print(f'  Показать еще #{step}: +{delta}, всего URL {len(links)}',flush=True)
            if delta==0:
                failed+=1
                if failed>=2:
                    page.screenshot(path=str(HERE/'ddxfitness_debug.png'),full_page=True)
                    print('После двух нажатий новых URL нет; остановка и скриншот ddxfitness_debug.png',flush=True)
                    break
            else: failed=0
        except Exception as e:
            page.screenshot(path=str(HERE/'ddxfitness_debug.png'),full_page=True)
            print('Ошибка кнопки:',str(e)[:250],flush=True)
            break
    return sorted(links)


def parse_profile(page,url):
    # Use public, visible profile content, not header/footer navigation.
    data=page.evaluate('''() => {
      const h=document.querySelector('h1');
      const main=document.querySelector('main') || document.body;
      const text=main.innerText||document.body.innerText||'';
      const name=(h?.innerText||'').trim();
      const after=text.indexOf(name);
      let t=after>=0?text.slice(after+name.length):text;
      const end=t.search(/(?:\\n|^)(?:Тренировки|Клубы и услуги|Скачивай мобильное приложение)(?:\\n|$)/i);
      if(end>=0)t=t.slice(0,end);
      const refs=[...main.querySelectorAll('a[href]')].map(a=>({text:(a.innerText||'').trim(),url:a.href}));
      return {name,profile_text:t.slice(0,10000),refs};
    }''')
    name=re.sub(r'\s+',' ',data['name']).strip()
    if not name or 'тренер' in name.lower() and len(name)>90:
        raise ValueError('Не найдено корректное ФИО в h1')
    t=data['profile_text']
    role=''
    for term in ('Персональный тренер','Тренер групповых'):
        if re.search(re.escape(term),t,re.I): role=term;break
    exp=re.search(r'стаж\s*(\d+)\s*(?:год|года|лет)',t,re.I)
    # Specialty text between headings; never fall back to arbitrary marketing prose.
    spec=re.search(r'(?:^|\n)Специализация\s*\n(.*?)(?=\n(?:О тренере|Расписание занятий|Тренировки|Достижения|Образование|Клубы и услуги)(?:\n|$)|\Z)',t,re.I|re.S)
    specialty='; '.join(x.strip(' \t•-') for x in spec.group(1).splitlines() if x.strip()) if spec else ''
    clubs=[]
    for a in data['refs']:
        if '/clubs/' in urlparse(a['url']).path and a['text']:
            v=re.sub(r'\s+',' ',a['text'])
            if v not in clubs:clubs.append(v)
    # No guessing city from club names (many club names are non-geographical).
    socials={k:'' for k in ['vk','ok','dzen','telegram','instagram','tiktok','tenchat']}
    for a in data['refs']:
        host=(urlparse(a['url']).hostname or '').lower()
        key=SOCIAL_DOMAINS.get(host)
        if key and not socials[key]:socials[key]=a['url'].split('?')[0]
    # No artificial 'education' inferred from biography; leave blank unless independently parsed later.
    result=dict(name=name,city='',role=role,specialty=specialty,clubs='; '.join(clubs),experience_years=exp.group(1) if exp else '',education='',source='DDX Fitness',source_profile_url=url,source_catalog_url=CATALOG,date_collected=datetime.now().date().isoformat(),status='Анкета найдена на сайте DDX; соцсети требуют проверки')
    result.update(socials)
    return result


def main():
    p=argparse.ArgumentParser(description='DDX Fitness coach profiles collector')
    p.add_argument('--max-profiles',type=int,default=30,help='Сколько новых анкет обработать (0 = все найденные)')
    p.add_argument('--max-clicks',type=int,default=150)
    p.add_argument('--show-browser',action='store_true')
    p.add_argument('--delay-ms',type=int,default=800)
    args=p.parse_args()
    db=sqlite3.connect(DB);init_db(db)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=not args.show_browser)
        context=browser.new_context(locale='ru-RU',viewport={'width':1400,'height':950})
        page=context.new_page()
        try:
            page.goto(CATALOG,wait_until='domcontentloaded',timeout=45000)
            page.wait_for_timeout(1500)
            dismiss_cookies(page)
            all_urls=expand_catalog(page,args.max_clicks,args.delay_ms)
            (HERE/'ddxfitness_discovered_urls.txt').write_text('\n'.join(all_urls)+'\n',encoding='utf-8')
            total=len(all_urls);scraped=0;already=0
            for i,url in enumerate(all_urls,1):
                if db.execute('SELECT 1 FROM profiles WHERE url=?',(url,)).fetchone():
                    already+=1;continue
                if args.max_profiles and scraped>=args.max_profiles:break
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    page.locator('h1').first.wait_for(timeout=12000)
                    item=parse_profile(page,url)
                    save_profile(db,item);scraped+=1
                    print(f'[{i}/{total}] {item["name"]} | {item["role"]} | {item["clubs"][:35]}',flush=True)
                    export(db)
                except Exception as e:log_error(db,url,e)
                time.sleep(max(args.delay_ms,0)/1000)
            print(f'ГОТОВО: найдено URL {total}, новых обработано {scraped}, уже было {already}, всего анкет в CSV {export(db)}',flush=True)
            print('CSV:',OUT,flush=True)
        finally:browser.close();db.close()

if __name__=='__main__':main()
