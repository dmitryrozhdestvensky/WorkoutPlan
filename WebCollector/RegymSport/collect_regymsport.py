"""Public profile collector for regymsport.ru. Python 3.10+, Playwright.
No login, no captcha bypass, no private data scraping. Persists after every profile.
"""
import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = 'https://regymsport.ru'
LISTING = ROOT + '/trenery/'
DATA = Path(__file__).resolve().parent
CHECKPOINT = DATA / 'regymsport_checkpoint.json'
CSV_FILE = DATA / 'regymsport_trainers.csv'
ERROR_FILE = DATA / 'regymsport_errors.csv'
FIELDS = ['name','city','specialty','clubs','skills','education','vk','ok','dzen','telegram','instagram','tiktok','tenchat','source','source_profile_url','source_catalog_url','date_collected','status']
URL_RE = re.compile(r'^https://regymsport\.ru/trenery/[^/?#]+/?$', re.I)
PROVIDERS = {'vk': ('vk.com','m.vk.com','vk.ru'), 'ok': ('ok.ru',), 'dzen': ('dzen.ru',), 'telegram': ('t.me','telegram.me'), 'instagram': ('instagram.com','www.instagram.com'), 'tiktok': ('tiktok.com','www.tiktok.com'), 'tenchat': ('tenchat.ru',)}

def normalize(url):
    u = urlsplit(url or '')
    return urlunsplit((u.scheme.lower() or 'https', u.netloc.lower(), u.path.rstrip('/') + '/', '', ''))

def write_csv(path, rows, cols):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore', delimiter=';')
        writer.writeheader(); writer.writerows(rows)

def save(state):
    tmp = CHECKPOINT.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(CHECKPOINT)
    write_csv(CSV_FILE, sorted(state['profiles'].values(), key=lambda r: r['name']), FIELDS)
    write_csv(ERROR_FILE, state['errors'], ['url','error'])

def profile_links(page):
    return page.evaluate('''() => [...new Set([...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => /^https:\\/\\/regymsport\\.ru\\/trenery\\/[^/?#]+\\/?(?:[?#].*)?$/i.test(h)))].map(h => h.split(/[?#]/)[0])''')

def extract(page, url):
    """Use headings and labelled links; avoid corporate header/footer socials."""
    data = page.evaluate('''() => {
      const clean = s => (s || '').replace(/\\s+/g,' ').trim();
      const name = clean(document.querySelector('h1')?.textContent);
      const scope = document.querySelector('main') || document.body;
      const all = [...scope.querySelectorAll('a[href]')];
      const social = all.filter(a => /Тренер\\s+во\\s+[«\"]?ВКонтакте|VK\\s+тренера|Личн.*ВКонтакте|профиль\\s+тренера\\s+в\\s+ВК/i.test(clean(a.textContent)));
      const h = [...scope.querySelectorAll('h1,h2,h3,h4')];
      function section(headingText) {
        const el = h.find(x => clean(x.textContent).toLowerCase().includes(headingText.toLowerCase()));
        if (!el) return '';
        let p = el.nextElementSibling, out = [];
        for(let i=0;p && i<8;i++,p=p.nextElementSibling) {
          if (/^H[1-4]$/.test(p.tagName)) break;
          const t=clean(p.innerText);if(t)out.push(t);
        }
        return out.join(' | ').slice(0,750);
      }
      const clubsEl = [...scope.querySelectorAll('*')].find(e => e.children.length === 0 && clean(e.textContent) === 'Тренирует в клубах');
      let clubs=[];
      if (clubsEl) {
         const block=clubsEl.parentElement?.parentElement || clubsEl.parentElement;
         clubs=[...block.querySelectorAll('a[href]')].filter(a=>/Режим/i.test(clean(a.textContent))).map(a=>clean(a.textContent));
      }
      const personalLinks = social.map(a => ({text:clean(a.textContent), href:a.href}));
      const candidateLinks = all.filter(a => a.closest('header,footer,nav') === null && /Тренер\\s+в|Личная\\s+страница|Мой\\s+(Telegram|Instagram|TikTok)/i.test(clean(a.textContent))).map(a=>({text:clean(a.textContent),href:a.href}));
      const whole=clean(scope.innerText); const first=whole.indexOf(name);
      const after=first>=0?whole.slice(first+name.length,first+name.length+700):'';
      return {name, after,clubs,skills:section('С чем работает'),education:section('Образование и квалификация') || section('Образование'),links:[...personalLinks,...candidateLinks]};
    }''')
    if not data.get('name') or len(data['name']) > 125:
        raise ValueError('No plausible h1/name')
    values = {k:'' for k in FIELDS}
    values.update({'name':data['name'],'city':'Нижний Новгород','source':'RegymSport / сеть «Режим»','source_profile_url':url,'source_catalog_url':LISTING,'date_collected':datetime.now(timezone.utc).date().isoformat(),'status':'Профиль на сайте найден; личные соцсети требуют проверки'})
    values['skills']=data.get('skills') or ''
    values['education']=data.get('education') or ''
    values['clubs']=' | '.join(dict.fromkeys(data.get('clubs') or []))
    intro=data.get('after') or ''
    for phrase in ('Персональный тренер','Тренер групповых программ','Тренер','Инструктор'):
        if intro.startswith(phrase): values['specialty']=phrase;break
    for link in data.get('links') or []:
        href = link.get('href',''); host = urlsplit(href).netloc.lower().removeprefix('www.')
        for key, domains in PROVIDERS.items():
            if host in domains and not values[key]:
                values[key] = href.split('?')[0]
    return values

def run(args):
    state = {'profiles': {},'errors': [],'listing_urls': [],'started':datetime.now(timezone.utc).isoformat()}
    if CHECKPOINT.exists() and not args.fresh:
        state.update(json.loads(CHECKPOINT.read_text(encoding='utf-8')))
        print('Продолжаю сохранённый сбор:', len(state['profiles']), 'профилей')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show_browser)
        ctx = browser.new_context(locale='ru-RU', viewport={'width':1360,'height':900})
        page = ctx.new_page()
        try:
            page.goto(LISTING, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(1000)
            found = set(state.get('listing_urls') or [])
            found.update(normalize(x) for x in profile_links(page))
            misses=0
            for i in range(args.max_clicks):
                # Only visible 'more' buttons; stop if no fresh URLs after consecutive clicks.
                buttons = page.get_by_role('button', name=re.compile(r'показать\s+ещ[её]', re.I))
                visible = [buttons.nth(k) for k in range(buttons.count()) if buttons.nth(k).is_visible()]
                if not visible: break
                old=len(found)
                try:
                    visible[0].scroll_into_view_if_needed(timeout=5000)
                    visible[0].click(timeout=6000)
                    page.wait_for_timeout(1100)
                except Exception as e:
                    print('Кнопка недоступна:',str(e)[:180]);break
                found.update(normalize(x) for x in profile_links(page))
                misses = misses + 1 if len(found)==old else 0
                print(f'Каталог: нажатие {i+1}, URL {len(found)} (+{len(found)-old})')
                if misses >= 2: break
            state['listing_urls']=sorted(found)
            save(state)
            print('Ссылок на персональные профили:',len(found))
        except Exception as exc:
            print('Ошибка каталога:',exc)
            state['errors'].append({'url':LISTING,'error':str(exc)[:400]})
            save(state)
        detail = ctx.new_page()
        urls = state['listing_urls'][:args.max_profiles] if args.max_profiles else state['listing_urls']
        for idx,url in enumerate(urls,1):
            if url in state['profiles']:
                continue
            try:
                response=detail.goto(url,wait_until='domcontentloaded',timeout=45000)
                if response and response.status in (403,429):
                    print('Ограничение сайта',response.status,'— останавливаю сбор');break
                detail.wait_for_timeout(350)
                row=extract(detail,url)
                state['profiles'][url]=row
                print(f'[{idx}/{len(urls)}] {row["name"]} | VK: {"да" if row["vk"] else "нет"}')
            except Exception as exc:
                state['errors'].append({'url':url,'error':str(exc)[:350]})
                print(f'[{idx}/{len(urls)}] ошибка:',str(exc)[:130])
            finally:
                save(state)
                time.sleep(args.delay)
        browser.close()
    print(f'ГОТОВО. Анкет {len(state["profiles"])}; ошибок {len(state["errors"])}; CSV: {CSV_FILE.name}')
    print('Для Excel выполните: .\\.venv\\Scripts\\python.exe merge_regymsport.py')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-clicks',type=int,default=35)
    parser.add_argument('--max-profiles',type=int,default=0,help='0 = all; 5 for a quick test')
    parser.add_argument('--delay',type=float,default=0.8)
    parser.add_argument('--show-browser',action='store_true')
    parser.add_argument('--fresh',action='store_true',help='Discard earlier checkpoint')
    run(parser.parse_args())
