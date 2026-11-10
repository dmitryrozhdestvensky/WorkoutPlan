"""World Class public trainers collector V1.7. Python 3.10+, Playwright. No login.
API-first enrichment: full name, club, education, achievements, specialties, photo and raw JSON."""
import argparse, csv, json, re, sqlite3, time, shutil, html
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
COLS=['name','source_profile_url','city','specialty','clubs','education','achievements','skills','vk','ok','dzen','telegram','instagram','tiktok','tenchat','date_collected','source_name','first_name','surname','position','club_address','grade','gender','photo_url','source_external_id','api_updated_at']
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
    con.execute('CREATE TABLE IF NOT EXISTS api_records (url TEXT PRIMARY KEY, external_id TEXT, raw_json TEXT NOT NULL, captured_at TEXT NOT NULL)')
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


def html_to_text(value):
    """Convert API HTML fragments (ul/li/p/br) to readable plain text."""
    if not isinstance(value, str) or not value.strip():
        return ''
    value = re.sub(r'(?i)<\s*li\b[^>]*>', '\n• ', value)
    value = re.sub(r'(?i)</\s*(li|p|div|ul|ol)\s*>', '\n', value)
    value = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', value)
    value = re.sub(r'<[^>]+>', ' ', value)
    value = html.unescape(value).replace('\xa0', ' ')
    lines = [re.sub(r'\s+', ' ', x).strip(' \t•') for x in value.splitlines()]
    return '\n'.join(('• ' + x) if x and not x.startswith('•') else x for x in lines if x).strip()


def nested_attrs(obj):
    if not isinstance(obj, dict):
        return {}
    data = obj.get('data')
    if isinstance(data, dict):
        attrs = data.get('attributes')
        return attrs if isinstance(attrs, dict) else {}
    return {}


def api_item_to_profile(item, url):
    """Map the observed WorldClass API object to our CSV profile fields."""
    attrs = item.get('attributes') or {}
    if not isinstance(attrs, dict):
        attrs = {}

    first = str(attrs.get('name') or '').strip()
    surname = str(attrs.get('second_name') or '').strip()
    full_name = ' '.join(x for x in (first, surname) if x).strip()

    club = nested_attrs(attrs.get('club'))
    grade = nested_attrs(attrs.get('grade'))
    gender = nested_attrs(attrs.get('gender'))
    image = nested_attrs(attrs.get('additional_image'))

    photo = ''
    if image:
        photo = str(image.get('url') or '').strip()
        if not photo:
            formats = image.get('formats') or {}
            if isinstance(formats, dict):
                for size in ('large', 'medium', 'small', 'thumbnail'):
                    candidate = formats.get(size) or {}
                    if isinstance(candidate, dict) and candidate.get('url'):
                        photo = str(candidate['url']).strip()
                        break
        if photo:
            photo = urljoin('https://www.worldclass.ru', photo)

    updated_at = str(attrs.get('updatedAt') or '').strip()
    external_id = str(item.get('id') or '').strip()

    return {
        'name': full_name,
        'source_profile_url': url,
        'city': '',  # API sample does not expose a separate city field.
        'specialty': str(attrs.get('position') or '').strip(),
        'clubs': str(club.get('name') or '').strip(),
        'education': html_to_text(attrs.get('education_and_certs')),
        'achievements': html_to_text(attrs.get('achievements')),
        'skills': html_to_text(attrs.get('fitness_specialty')),
        'first_name': first,
        'surname': surname,
        'position': str(attrs.get('position') or '').strip(),
        'club_address': str(club.get('address') or '').strip(),
        'grade': str(grade.get('name') or '').strip(),
        'gender': str(gender.get('value') or '').strip(),
        'photo_url': photo,
        'source_external_id': external_id,
        'api_updated_at': updated_at,
        'date_collected': datetime.now().date().isoformat(),
        'source_name': 'World Class',
    }


def upsert_api_profile(con, url, item):
    """Update API-backed fields, preserve existing non-empty manual/social values."""
    incoming = api_item_to_profile(item, url)
    row = con.execute('SELECT payload FROM profiles WHERE url=?', (url,)).fetchone()
    existing = json.loads(row[0]) if row else {}
    merged = {k: existing.get(k, '') for k in COLS}

    # API fields are authoritative when populated; blank API values never erase data.
    api_fields = {
        'name', 'source_profile_url', 'specialty', 'clubs', 'education',
        'achievements', 'skills', 'first_name', 'surname', 'position',
        'club_address', 'grade', 'gender', 'photo_url',
        'source_external_id', 'api_updated_at', 'date_collected', 'source_name'
    }
    for key, value in incoming.items():
        if value not in ('', None):
            if key in api_fields:
                merged[key] = value
            elif not merged.get(key):
                merged[key] = value

    # A previously guessed placeholder city is not a verified city.
    if not merged.get('city') or 'не уточн' in str(merged.get('city')).casefold():
        merged['city'] = ''

    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        'INSERT INTO profiles(url,payload,collected_at) VALUES(?,?,?) '
        'ON CONFLICT(url) DO UPDATE SET payload=excluded.payload,collected_at=excluded.collected_at',
        (url, json.dumps(merged, ensure_ascii=False), now)
    )
    con.execute(
        'INSERT INTO api_records(url,external_id,raw_json,captured_at) VALUES(?,?,?,?) '
        'ON CONFLICT(url) DO UPDATE SET external_id=excluded.external_id,raw_json=excluded.raw_json,captured_at=excluded.captured_at',
        (url, str(item.get('id') or ''), json.dumps(item, ensure_ascii=False), now)
    )


def discover_via_api(page, con, max_pages=500, delay=1.5):
    """Fetch every public trainer record and enrich profiles directly from API."""
    endpoint = 'https://www.worldclass.ru/api/trainers'
    new_urls = set()
    page_num = 1
    page_count = None
    total_reported = None
    done = False
    staged = {}
    validated = False
    prev = {row[0] for row in con.execute('SELECT url FROM discovered_profiles')}

    while page_num <= max_pages:
        params = {
            'pagination[page]': str(page_num),
            'pagination[pageSize]': '12',
            'populate[0]': 'club',
            'populate[1]': 'additional_image',
            'populate[2]': 'grade',
            'populate[3]': 'gender',
            'filters[training_categories][service_type][$eq]': 'fitness',
        }
        payload = None
        for attempt in range(1, 5):
            try:
                response = page.evaluate("""async ({endpoint, params}) => {
                  const query = new URLSearchParams(params);
                  const controller = new AbortController();
                  const timeout = setTimeout(() => controller.abort(), 45000);
                  try {
                    const resp = await fetch(endpoint + '?' + query.toString(), {
                      method: 'GET', credentials: 'same-origin',
                      headers: {'Accept':'application/json'},
                      signal: controller.signal
                    });
                    const status = resp.status;
                    if (!resp.ok) return {status, payload:null};
                    return {status, payload:await resp.json()};
                  } finally { clearTimeout(timeout); }
                }""", {'endpoint': endpoint, 'params': params})
                status = response['status']
                if status in (429, 500, 502, 503, 504):
                    print(f'  API страница {page_num}: HTTP {status}, повтор {attempt}/4', flush=True)
                    time.sleep(min(6 * attempt, 25))
                    continue
                if status in (401, 403):
                    print(f'  API страница {page_num}: HTTP {status}; API недоступен.', flush=True)
                    return False
                if status != 200:
                    raise RuntimeError(f'HTTP {status}')
                payload = response['payload']
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                    raise ValueError('Ответ API не содержит список data')
                break
            except Exception as exc:
                print(f'  API страница {page_num}: {str(exc)[:170]}; попытка {attempt}/4', flush=True)
                if attempt < 4:
                    time.sleep(min(4 * attempt, 15))

        if payload is None:
            print(f'  API не удалось получить страницу {page_num}. Можно повторить позднее.', flush=True)
            break

        meta = (payload.get('meta') or {}).get('pagination') or {}
        try:
            page_count = int(meta['pageCount'])
            total_reported = int(meta['total'])
        except (KeyError, ValueError, TypeError):
            print('  API не вернул корректные pageCount/total; остановка.', flush=True)
            break

        rows = payload['data']
        batch = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            identifier = item.get('id')
            if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                continue
            url = normurl(f'https://www.worldclass.ru/trainers/{identifier}/')
            if url:
                batch[url] = item

        # Validate the observed numeric ID -> profile URL convention against prior links.
        if not validated:
            staged.update(batch)
            if not prev or (prev & set(staged)):
                validated = True
                for url, item in staged.items():
                    attrs = item.get('attributes') or {}
                    label = ' '.join(x for x in (str(attrs.get('name') or '').strip(),
                                                  str(attrs.get('second_name') or '').strip()) if x)
                    store_discovered(con, {url: label})
                    upsert_api_profile(con, url, item)
                con.commit()
                print(f'  API ID проверен; сохранено образцов/записей: {len(staged)}.', flush=True)
                staged.clear()
            elif page_num >= min(page_count, 5):
                (HERE / 'worldclass_api_id_check.json').write_text(json.dumps({
                    'reason': 'API IDs did not match previously discovered profile URLs',
                    'sample_urls': list(staged)[:10],
                    'page': page_num, 'pageCount': page_count, 'total': total_reported
                }, ensure_ascii=False, indent=2), encoding='utf-8')
                print('  ВНИМАНИЕ: ID API не совпали с прежними URL. Запись остановлена.', flush=True)
                return False
        else:
            for url, item in batch.items():
                attrs = item.get('attributes') or {}
                label = ' '.join(x for x in (str(attrs.get('name') or '').strip(),
                                              str(attrs.get('second_name') or '').strip()) if x)
                store_discovered(con, {url: label})
                upsert_api_profile(con, url, item)
            con.commit()

        new_urls.update(batch)
        print(f'  API {page_num}/{page_count}: записей {len(rows)}, обновлено API-карточек {len(batch)}, всего в проходе {len(new_urls)}/{total_reported}', flush=True)

        if not rows or page_num >= page_count:
            done = page_num >= page_count
            break
        page_num += 1
        time.sleep(max(delay, 0.5))

    status = 'ok' if done else 'partial'
    con.execute(
        'INSERT INTO listing_pages(url,status,processed_at) VALUES(?,?,?) '
        'ON CONFLICT(url) DO UPDATE SET status=excluded.status,processed_at=excluded.processed_at',
        (endpoint, status, datetime.now().isoformat())
    )
    con.commit()
    print(f'API каталог: {status}; URL в текущем проходе: {len(new_urls)}; total по API: {total_reported}', flush=True)
    return done


def discover_via_browser(page, con, max_clicks=150, delay=1.5):
    """Safe fallback: use the working V1.4 explicit show-more selector."""
    current=get_profile_links(page)
    store_discovered(con,current)
    complete=False
    for num in range(1,max_clicks+1):
        result,current=click_show_more(page,current)
        if result=='expanded':
            store_discovered(con,current)
            print(f'  Резервный каталог #{num}: ссылок {len(current)}',flush=True)
            page.wait_for_timeout(int(max(0.5,delay)*1000))
            continue
        if result=='missing':
            complete=True
        else:
            print('  Резервный каталог временно остановлен; уже найденные ссылки сохранены.',flush=True)
        break
    status='ok' if complete else 'partial'
    con.execute('INSERT INTO listing_pages(url,status,processed_at) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET status=excluded.status,processed_at=excluded.processed_at',
                (START,status,datetime.now().isoformat()))
    con.commit()
    print(f'Резервный каталог: {status}; ссылок в проходе {len(current)}',flush=True)
    return complete


def main():
    ap=argparse.ArgumentParser(description='WorldClass collector V1.7: API-first full profile enrichment + UI fallback')
    ap.add_argument('--max-profiles',type=int,default=5000)
    ap.add_argument('--show-browser',action='store_true')
    ap.add_argument('--delay',type=float,default=1.5)
    ap.add_argument('--api-max-pages',type=int,default=500)
    ap.add_argument('--max-clicks',type=int,default=150,help='Maximum show-more clicks if in-browser API is blocked')
    ap.add_argument('--discover-only',action='store_true',help='Fetch and enrich all profiles from API; do not open individual trainer pages')
    ap.add_argument('--skip-api',action='store_true',help='Only retry previously discovered profiles; no API requests')
    args=ap.parse_args()
    con=init_db()
    safeguard_and_reconcile(con)
    known={x[0] for x in con.execute('SELECT url FROM profiles')}
    print(f'Ранее сохранено {len(known)} анкет. Старые данные не удаляются.',flush=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=not args.show_browser)
            ctx=browser.new_context(locale='ru-RU',viewport={'width':1400,'height':900})
            page=ctx.new_page()
            page.set_default_timeout(15000)
            try:
                if not args.skip_api:
                    try:
                        page.goto(START, wait_until='domcontentloaded', timeout=45000)
                    except Exception as exc:
                        print('  Главная страница каталога недоступна; пробую публичный API:',str(exc).splitlines()[0][:140],flush=True)
                    api_done=discover_via_api(page,con,max_pages=args.api_max_pages,delay=args.delay)
                    # API records already contain full trainer data; refresh known URLs so we do not
                    # reopen all profile pages unnecessarily. Existing HTML/social fields are preserved.
                    known={x[0] for x in con.execute('SELECT url FROM profiles')}
                    if not api_done:
                        print('  API-каталог не завершён. Пробую резервное обнаружение URL через интерфейс сайта.',flush=True)
                        try:
                            page.goto(START, wait_until='domcontentloaded', timeout=45000)
                            discover_via_browser(page,con,max_clicks=args.max_clicks,delay=args.delay)
                        except Exception as exc:
                            print('  Резервный обход не выполнен:',str(exc).splitlines()[0][:180],flush=True)
                pending=con.execute('SELECT url,listing_name FROM discovered_profiles ORDER BY url').fetchall()
                print(f'Обнаруженных URL в SQLite: {len(pending)}; ранее сохранено {len(known)}; новых/ошибочных для обработки: {sum(u not in known for u,_ in pending)}',flush=True)
                if args.discover_only:
                    print('Режим --discover-only: подробные страницы не открываются.',flush=True)
                else:
                    for index,(url,label) in enumerate(pending,1):
                        if len(known)>=args.max_profiles:
                            print(f'Достигнут лимит --max-profiles {args.max_profiles}; можно продолжить позже.',flush=True)
                            break
                        if url in known:continue
                        for attempt in range(1,4):
                            try:
                                page.goto(url,wait_until='domcontentloaded',timeout=50000)
                                page.wait_for_timeout(500)
                                item=parse_profile(page,url,label or '')
                                con.execute('INSERT INTO profiles(url,payload,collected_at) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET payload=excluded.payload,collected_at=excluded.collected_at',
                                            (url,json.dumps(item,ensure_ascii=False),datetime.now().isoformat()))
                                con.commit()
                                known.add(url)
                                if len(known)%10==0:write_csv(con)
                                print(f'[{index}/{len(pending)}] {item["name"]}; сохранено {len(known)}',flush=True)
                                break
                            except Exception as exc:
                                if attempt==3:
                                    con.execute('INSERT INTO errors VALUES(?,?,?)',(url,str(exc)[:500],datetime.now().isoformat()))
                                    con.commit()
                                    print('Ошибка профиля:',url,str(exc)[:150],flush=True)
                                else:
                                    print(f'  Повтор профиля {index}, попытка {attempt+1}/3',flush=True)
                                    time.sleep(2*attempt)
                        time.sleep(max(args.delay,0))
            finally:
                browser.close()
    except KeyboardInterrupt:
        print('Остановлено пользователем. Сохраняю CSV.',flush=True)
    finally:
        total=write_csv(con)
        print(f'ГОТОВО. Сохранено профилей: {total}. CSV: {CSV}. Ошибки: {ERRORS}',flush=True)
        con.close()

if __name__=='__main__':main()
