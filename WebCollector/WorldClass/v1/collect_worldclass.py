"""World Class public trainers collector. Python 3.10+, Playwright. No login."""
import argparse, csv, json, re, sqlite3, time
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
    con.commit();return con

def write_csv(con):
    items=[json.loads(x[0]) for x in con.execute('SELECT payload FROM profiles ORDER BY url')]
    with CSV.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLS,delimiter=';');w.writeheader();w.writerows([{k:i.get(k,'') for k in COLS} for i in items])
    with ERRORS.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['URL','Ошибка','Дата']);w.writerows(con.execute('SELECT url,error,at FROM errors'))
    return len(items)

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

def press_more(page):
    """Only try generic trainer-list controls; cap clicks."""
    buttons=page.get_by_text(re.compile(r'^(?:показать ещё|показать еще|show more)$',re.I))
    for i in range(min(buttons.count(),4)):
        try:
            e=buttons.nth(i)
            if e.is_visible():
                e.click(timeout=2500);page.wait_for_timeout(1000);return True
        except Exception:continue
    return False

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
    args=ap.parse_args();con=init_db()
    processed={x[0] for x in con.execute("SELECT url FROM listing_pages WHERE status='ok'")}
    known={x[0] for x in con.execute('SELECT url FROM profiles')}
    queue=[START];seen_list=set();queue_profiles={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=not args.show_browser)
        ctx=browser.new_context(locale='ru-RU',viewport={'width':1400,'height':900})
        page=ctx.new_page();page.set_default_timeout(15000)
        while queue and len(seen_list)<args.max_list_pages:
            link=queue.pop(0)
            if link in seen_list:continue
            seen_list.add(link)
            try:
                page.goto(link,wait_until='domcontentloaded',timeout=40000)
                page.wait_for_timeout(1200)
                all_links=get_profile_links(page)
                for _ in range(100):
                    if not press_more(page):break
                    all_links.update(get_profile_links(page))
                for url,label in all_links.items():queue_profiles.setdefault(url,label)
                for next_url in find_pagination(page,link):
                    if next_url not in seen_list and next_url not in queue:queue.append(next_url)
                con.execute('INSERT OR REPLACE INTO listing_pages VALUES(?,?,?)',(link,'ok',datetime.now().isoformat()));con.commit()
                print(f'Каталог {len(seen_list)}: найдено ссылок {len(all_links)}, всего уникальных {len(queue_profiles)}, в очереди страниц {len(queue)}',flush=True)
            except Exception as e:
                con.execute('INSERT INTO errors VALUES(?,?,?)',(link,str(e)[:500],datetime.now().isoformat()));con.commit()
                print('Ошибка каталога:',link,str(e)[:160],flush=True)
            time.sleep(args.delay)
        # The site may offer a "Все" link; if pagination depends on JS, use all observed links.
        for index,(url,label) in enumerate(queue_profiles.items(),1):
            if len(known)>=args.max_profiles:break
            if url in known:continue
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=40000)
                page.wait_for_timeout(500)
                item=parse_profile(page,url,label)
                con.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)',(url,json.dumps(item,ensure_ascii=False),datetime.now().isoformat()));con.commit()
                known.add(url)
                if index%10==0:write_csv(con)
                print(f'[{index}/{len(queue_profiles)}] {item["name"]}; сохранено {len(known)}',flush=True)
            except Exception as e:
                con.execute('INSERT INTO errors VALUES(?,?,?)',(url,str(e)[:500],datetime.now().isoformat()));con.commit()
                print('Ошибка профиля:',url,str(e)[:150],flush=True)
            time.sleep(args.delay)
        browser.close()
    total=write_csv(con)
    print(f'ГОТОВО. Сохранено профилей: {total}. CSV: {CSV}. Ошибки: {ERRORS}',flush=True)

if __name__=='__main__':main()
