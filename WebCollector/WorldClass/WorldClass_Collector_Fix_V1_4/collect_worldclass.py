"""World Class public trainers collector. Python 3.10+, Playwright. No login."""
import argparse, csv, json, re, sqlite3, time, shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
DATA=ROOT/'Data'
DB=HERE/'worldclass_progress.sqlite3'
CSV=HERE/'worldclass_trainers.csv'
ERRORS=HERE/'worldclass_errors.csv'
START='https://www.worldclass.ru/trainers/'
PROFILE_RE=re.compile(r'^/trainers/[^/?#]+/?$', re.I)
COLS=['name','source_profile_url','city','specialty','clubs','education','achievements','skills','vk','ok','dzen','telegram','instagram','tiktok','tenchat','date_collected','source_name']
SOCIAL_DOMAINS={'vk':'vk.com','ok':'ok.ru','dzen':'dzen.ru','telegram':'t.me','instagram':'instagram.com','tiktok':'tiktok.com','tenchat':'tenchat.ru'}

def normurl(u):
    try:
        p=urlsplit(u)
        if p.scheme not in ('http','https') or p.netloc.lower() not in ('worldclass.ru','www.worldclass.ru'):return ''
        path=p.path.rstrip('/')+'/'
        if not PROFILE_RE.fullmatch(path) or path=='/trainers/':return ''
        return 'https://www.worldclass.ru'+path
    except Exception:return ''

def init_db():
    con=sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS profiles (url TEXT PRIMARY KEY, payload TEXT NOT NULL, collected_at TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS listing_pages (url TEXT PRIMARY KEY, status TEXT NOT NULL, processed_at TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS errors (url TEXT, error TEXT, at TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS discovered_profiles (url TEXT PRIMARY KEY, listing_name TEXT, first_seen_at TEXT NOT NULL)')
    con.commit();return con

def safeguard_and_reconcile(con):
    """Backup existing files and recover CSV profiles missing from SQLite."""
    backup=HERE/'Backups'
    backup.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    if DB.exists():
        # Online SQLite backup is consistent even if WAL is enabled.
        target=sqlite3.connect(backup/f'worldclass_progress_{stamp}.sqlite3')
        try: con.backup(target)
        finally: target.close()
    if CSV.exists() and CSV.stat().st_size:
        shutil.copy2(CSV,backup/f'worldclass_trainers_{stamp}.csv')
        with CSV.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f,delimiter=';')
            restored=0
            for row in reader:
                url=normurl(row.get('source_profile_url',''))
                if not url:continue
                payload={k:row.get(k,'') for k in COLS}
                count=con.execute('INSERT INTO profiles(url,payload,collected_at) VALUES(?,?,?) ON CONFLICT(url) DO NOTHING',
                    (url,json.dumps(payload,ensure_ascii=False),datetime.now().isoformat())).rowcount
                restored+=count
            con.commit()
        if restored:print(f'Восстановлено из CSV в SQLite: {restored}',flush=True)
    print('Резервные копии: ',backup,flush=True)

def write_csv(con):
    items=[json.loads(x[0]) for x in con.execute('SELECT payload FROM profiles ORDER BY url')]
    with CSV.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLS,delimiter=';');w.writeheader();w.writerows([{k:i.get(k,'') for k in COLS} for i in items])
    with ERRORS.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['URL','Ошибка','Дата']);w.writerows(con.execute('SELECT url,error,at FROM errors'))
    return len(items)

def store_discovered(con, links):
    for url, label in links.items():
        con.execute('INSERT INTO discovered_profiles(url,listing_name,first_seen_at) VALUES (?,?,?) ON CONFLICT(url) DO NOTHING', (url,label,datetime.now(timezone.utc).isoformat()))
    con.commit()

def get_profile_links(page):
    raw=page.locator('a[href]').evaluate_all('els => els.map(a => ({url:a.href,text:(a.innerText||a.textContent||"").trim()}))')
    out={}
    for item in raw:
        u=normurl(item['url'])
        if u:out[u]=item['text']
    return out

def find_pagination(page,cur):
    """Discover links to pagination without trying guessed API endpoints."""
    raw=page.locator('a[href]').evaluate_all('els => els.map(a => ({url:a.href,text:(a.innerText||a.textContent||"").trim()}))')
    result=[]
    for a in raw:
        try:
            p=urlsplit(a['url'])
            if p.netloc.lower() not in ('worldclass.ru','www.worldclass.ru') or p.path.rstrip('/')!='/trainers':continue
            if a['url']==cur:continue
            text=a['text'].casefold().strip()
            if text.isdigit() or text in ('все','след.','след','конец','пред.','пред','next','all') or p.query:
                result.append(a['url'])
        except Exception:pass
    return list(dict.fromkeys(result))

def cookie_overlay_visible(page):
    try:
        return page.get_by_text('Мы используем cookies', exact=False).first.is_visible(timeout=700)
    except Exception:
        return False


def dismiss_cookie_overlay(page, wait_ms=5000):
    """Handle delayed cookie consent pop-up before attempting pagination."""
    deadline = time.monotonic() + wait_ms / 1000
    while time.monotonic() < deadline:
        if cookie_overlay_visible(page):
            for candidate in [page.get_by_role('button', name=re.compile(r'^\s*принять\s*$', re.I)),
                              page.locator('button').filter(has_text=re.compile(r'^\s*принять\s*$', re.I)),
                              page.get_by_text('Принять', exact=True)]:
                try:
                    if candidate.count() and candidate.first.is_visible(timeout=500):
                        candidate.first.click(timeout=5000)
                        page.wait_for_timeout(500)
                        print('  Окно cookies закрыто', flush=True)
                        return True
                except Exception as exc:
                    print('  Cookies не закрыты:', str(exc).splitlines()[0][:160], flush=True)
        page.wait_for_timeout(250)
    return False


def save_click_diagnostics(page, reason, before, after, attempt):
    """Capture click interception and UI state, excluding authentication details."""
    try:
        data = page.evaluate("""() => {
          const b=document.querySelector('button[class*="_moreButton_"]');
          const r=b?.getBoundingClientRect();
          const x=r ? Math.min(innerWidth-1,Math.max(0,r.left+r.width/2)) : 0;
          const y=r ? Math.min(innerHeight-1,Math.max(0,r.top+r.height/2)) : 0;
          const top=r ? document.elementFromPoint(x,y) : null;
          return {button_found:!!b,button_text:b?.innerText||'',
            button_busy:b?.getAttribute('aria-busy'),button_disabled:!!b?.disabled,
            button_rect:r?{x:r.x,y:r.y,width:r.width,height:r.height}:null,
            element_at_center:top?.outerHTML?.slice(0,500)||null,
            button_receives_pointer:!!(b && top && (b===top || b.contains(top))),
            cookie_dialog:document.body.innerText.includes('Мы используем cookies')};
        }""")
        data.update({'reason':reason,'before':before,'after':after,'attempt':attempt,'time':datetime.now().isoformat()})
        (HERE/'worldclass_click_diagnostic.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        page.screenshot(path=str(HERE/'worldclass_debug.png'),full_page=True)
    except Exception as exc:
        print('  Диагностика не сохранена:',str(exc).splitlines()[0][:140],flush=True)


def find_show_more_button(page):
    """Select the actual 'show more' button, never the adjacent 'collapse' button.

    WorldClass can render BOTH 'свернуть' and 'показать ещё' with the same
    CSS _moreButton_* class after the first expansion. CSS .first is wrong.
    """
    candidates = page.locator('button[class*="_moreButton_"]')
    for idx in range(candidates.count()):
        button = candidates.nth(idx)
        try:
            label = button.inner_text(timeout=1500).strip().casefold()
            if re.fullmatch(r'показать\s+ещ[её]', label) and button.is_visible(timeout=1000):
                return button
        except Exception:
            continue
    # The site's class names can change; try a semantic selector as fallback.
    buttons = page.get_by_role('button', name=re.compile(r'^\s*показать\s+ещ[её]\s*$', re.I))
    for idx in range(buttons.count()):
        button = buttons.nth(idx)
        try:
            if button.is_visible(timeout=1000):
                return button
        except Exception:
            continue
    return None


def click_show_more(page, current_links):
    """Expand the next batch without accidentally pressing 'свернуть'."""
    before = len(current_links)
    dismiss_cookie_overlay(page, wait_ms=1000)

    def wait_for_new(ms=11000):
        deadline = time.monotonic() + ms / 1000
        while time.monotonic() < deadline:
            page.wait_for_timeout(500)
            current_links.update(get_profile_links(page))
            if len(current_links) > before:
                return True
        return False

    for attempt in range(1, 4):
        dismiss_cookie_overlay(page, wait_ms=500)
        button = find_show_more_button(page)
        if button is None:
            # Do not click 'collapse' as a substitute. The current list may
            # already be fully expanded; caller will check any pagination.
            print('  Кнопки «Показать ещё» больше нет (кнопка «Свернуть» игнорируется).',flush=True)
            return 'missing', current_links
        try:
            if button.get_attribute('aria-busy') == 'true' or button.is_disabled():
                if wait_for_new(12000):
                    return 'expanded', current_links
                print(f'  «Показать ещё» занята (попытка {attempt}/3)',flush=True)
                continue
            button.scroll_into_view_if_needed(timeout=6000)
            button.click(timeout=9000)
            print(f'  Нажатие #{attempt}: именно «Показать ещё»',flush=True)
        except Exception as exc:
            print('  Клик по «Показать ещё»:',str(exc).splitlines()[0][:180],flush=True)
            # Only click the SAME button via DOM; never use CSS .first.
            try:
                fresh = find_show_more_button(page)
                if fresh is not None:
                    fresh.evaluate('(el) => el.click()')
                    print('  DOM click: именно «Показать ещё»',flush=True)
            except Exception as fallback_exc:
                print('  DOM click:',str(fallback_exc).splitlines()[0][:180],flush=True)
        if wait_for_new(12000):
            return 'expanded', current_links
        print(f'  Новых URL пока нет (попытка {attempt}/3)',flush=True)
        page.wait_for_timeout(900 * attempt)
    save_click_diagnostics(page,'correct show-more button produced no additional URLs',before,len(current_links),3)
    return 'unchanged', current_links

def list_section(page,label):
    script="""(label) => {
      const nodes=[...document.querySelectorAll('h1,h2,h3,h4,h5,strong,b')];
      const target=nodes.find(x=>x.textContent.trim().toLowerCase()===label.toLowerCase());
      if(!target)return '';
      let out=[],p=target.nextElementSibling;
      for(let i=0;i<8 && p;i++,p=p.nextElementSibling){
        if(/^H[1-5]$/.test(p.tagName))break;
        const t=(p.innerText||'').trim();if(t)out.push(t);
      }
      if(!out.length){let q=target.parentElement?.nextElementSibling;if(q)out.push((q.innerText||'').trim());}
      return out.join('; ').slice(0,1800);
    }"""
    try:return page.evaluate(script,label)
    except Exception:return ''

def parse_profile(page,url,listing_name=''):
    h=page.locator('h1').first
    name=h.inner_text(timeout=5000).strip() if h.count() else ''
    if not name: name=listing_name
    if not name:raise ValueError('Нет ФИО на странице')
    # Limit role to elements adjacent to h1; not entire footer.
    spec=page.evaluate('''() => {let h=document.querySelector('h1');if(!h)return '';let a=h.nextElementSibling;return (a?.innerText||h.parentElement?.querySelector('p')?.innerText||'').trim().slice(0,250)}''')
    links=page.locator('main a[href], article a[href]').evaluate_all('els=>els.map(a=>({href:a.href,label:(a.innerText||a.getAttribute("aria-label")||"").trim()}))')
    socials={k:'' for k in SOCIAL_DOMAINS}
    for link in links:
        host=urlsplit(link['href']).netloc.lower().removeprefix('www.')
        # Only explicitly identified trainer links; avoid site-wide club socials.
        label=link['label'].casefold()
        if not any(x in label for x in ('тренер','личн','мой профиль','соцсет')):continue
        for key,domain in SOCIAL_DOMAINS.items():
            if (host==domain or host.endswith('.'+domain)) and not socials[key]:socials[key]=link['href']
    data={'name':name,'source_profile_url':url,'city':'Не уточнён (проверить по клубу)',
          'specialty':spec,'clubs':list_section(page,'Клубы'),'education':list_section(page,'Образование и сертификаты'),
          'achievements':list_section(page,'Творческие и спортивные достижения'),
          'skills':list_section(page,'Фитнес-специализация'),
          'date_collected':datetime.now().date().isoformat(),'source_name':'World Class'}
    data.update(socials)
    return data

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--max-profiles',type=int,default=1500)
    ap.add_argument('--max-list-pages',type=int,default=120)
    ap.add_argument('--show-browser',action='store_true')
    ap.add_argument('--delay',type=float,default=1.4)
    ap.add_argument('--max-clicks',type=int,default=160)
    args=ap.parse_args()
    con=init_db()
    safeguard_and_reconcile(con)
    known={x[0] for x in con.execute('SELECT url FROM profiles')}
    print(f'Ранее сохранено {len(known)} анкет. Старые данные не удаляются.',flush=True)
    # Always reopen the catalog to find new profiles. All discovered URLs are
    # saved in SQLite, so even a partial catalog load can be resumed later.
    queue=[START]
    seen_list=set()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=not args.show_browser)
            ctx=browser.new_context(locale='ru-RU',viewport={'width':1400,'height':900})
            page=ctx.new_page()
            page.set_default_timeout(15000)
            net_events=[]
            def note_response(resp):
                try:
                    u=urlsplit(resp.url)
                    if u.netloc.endswith('worldclass.ru') and (resp.status >= 400 or 'trainer' in u.path.lower()):
                        net_events.append({'status':resp.status,'method':resp.request.method,'path':u.path[:180], 'at':datetime.now().isoformat()})
                        del net_events[:-100]
                except Exception:
                    pass
            def note_request_failed(req):
                try:
                    u=urlsplit(req.url)
                    if u.netloc.endswith('worldclass.ru'):
                        net_events.append({'failed':str(req.failure)[:200],'path':u.path[:180], 'at':datetime.now().isoformat()})
                        del net_events[:-100]
                except Exception:
                    pass
            page.on('response', note_response)
            page.on('requestfailed', note_request_failed)
            try:
                while queue and len(seen_list)<args.max_list_pages:
                    link=queue.pop(0)
                    if link in seen_list:continue
                    seen_list.add(link)
                    all_links={}
                    status='partial'
                    try:
                        page.goto(link,wait_until='domcontentloaded',timeout=40000)
                        page.wait_for_timeout(1200)
                        dismiss_cookie_overlay(page,wait_ms=2500)
                        all_links=get_profile_links(page)
                        store_discovered(con,all_links)
                        presses=0
                        for step in range(args.max_clicks):
                            if len(all_links)>=args.max_profiles:break
                            before=len(all_links)
                            click_status,all_links=click_show_more(page,all_links)
                            store_discovered(con,all_links)
                            if click_status=='missing':
                                status='ok'
                                print('  Кнопка закончилась; ссылок:',len(all_links),flush=True)
                                break
                            if click_status in ('error','unchanged'):
                                (HERE/'worldclass_network_diagnostic.json').write_text(json.dumps(net_events[-100:], ensure_ascii=False, indent=2), encoding='utf-8')
                                print('  Диагностика сети: worldclass_network_diagnostic.json', flush=True)
                                print('  Каталог загружен частично; продолжаю с найденными URL.',flush=True)
                                con.execute('INSERT INTO errors VALUES(?,?,?)',(link,'Show-more: '+click_status,datetime.now().isoformat()))
                                con.commit()
                                break
                            presses+=1
                            print(f'  Показать ещё #{presses}: +{len(all_links)-before}; ссылок {len(all_links)}',flush=True)
                        else:
                            status='partial'  # Reached max-clicks; not proven complete.
                        for next_url in find_pagination(page,link):
                            if next_url not in seen_list and next_url not in queue:queue.append(next_url)
                        con.execute('INSERT INTO listing_pages(url,status,processed_at) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET status=excluded.status,processed_at=excluded.processed_at', (link,status,datetime.now().isoformat()))
                        con.commit()
                        print(f'Каталог {len(seen_list)}: ссылок {len(all_links)}; накоплено {con.execute("SELECT COUNT(*) FROM discovered_profiles").fetchone()[0]}; статус {status}',flush=True)
                    except Exception as exc:
                        store_discovered(con,all_links)
                        con.execute('INSERT INTO errors VALUES(?,?,?)',(link,str(exc)[:500],datetime.now().isoformat()))
                        con.commit()
                        print('Ошибка каталога:',link,str(exc)[:160],flush=True)
                    time.sleep(args.delay)
                pending=con.execute('SELECT url,listing_name FROM discovered_profiles ORDER BY url').fetchall()
                print(f'Всего обнаружено URL: {len(pending)}. Новых для обработки: {sum(url not in known for url,_ in pending)}',flush=True)
                for index,(url,label) in enumerate(pending,1):
                    if len(known)>=args.max_profiles:break
                    if url in known:continue
                    try:
                        page.goto(url,wait_until='domcontentloaded',timeout=40000)
                        page.wait_for_timeout(500)
                        item=parse_profile(page,url,label or '')
                        con.execute('INSERT INTO profiles(url,payload,collected_at) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET payload=excluded.payload,collected_at=excluded.collected_at',(url,json.dumps(item,ensure_ascii=False),datetime.now().isoformat()))
                        con.commit()
                        known.add(url)
                        if len(known)%10==0:write_csv(con)
                        print(f'[{index}/{len(pending)}] {item["name"]}; сохранено {len(known)}',flush=True)
                    except Exception as exc:
                        con.execute('INSERT INTO errors VALUES(?,?,?)',(url,str(exc)[:500],datetime.now().isoformat()))
                        con.commit()
                        print('Ошибка профиля:',url,str(exc)[:150],flush=True)
                    time.sleep(args.delay)
            finally:
                browser.close()
    except KeyboardInterrupt:
        print('Остановлено пользователем. Сохраняю CSV.',flush=True)
    finally:
        total=write_csv(con)
        print(f'ГОТОВО. Сохранено профилей: {total}. CSV: {CSV}. Ошибки: {ERRORS}',flush=True)
        con.close()

if __name__=='__main__':main()
