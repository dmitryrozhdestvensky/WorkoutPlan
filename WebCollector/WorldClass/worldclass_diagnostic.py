"""World Class listing diagnostic. Read-only except clicking its public Show more button and cookie consent.
Run: .\.venv\Scripts\python.exe worldclass_diagnostic.py
No credentials, cookies, or response bodies are written to the report.
"""
from pathlib import Path
import json, re, time
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
TARGET='https://www.worldclass.ru/trainers/'
PAT=re.compile(r'^/trainers/[^/?#]+/?$')


def get_links(page):
    values=page.locator('a[href]').evaluate_all('els => els.map(a=>a.href)')
    return sorted({u.split('?')[0].rstrip('/') for u in values if urlparse(u).hostname in ('worldclass.ru','www.worldclass.ru') and PAT.match(urlparse(u).path)})


def run():
    log=[]
    events=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=False)
        context=browser.new_context(locale='ru-RU', viewport={'width':1440,'height':900})
        page=context.new_page()
        page.on('console',lambda msg: events.append({'kind':'console','type':msg.type,'message':msg.text[:250]}) if msg.type in ('error','warning') else None)
        page.on('pageerror',lambda err:events.append({'kind':'pageerror','message':str(err)[:300]}))
        page.on('response',lambda resp:events.append({'kind':'response','status':resp.status,'method':resp.request.method,'path':urlparse(resp.url).path[:160]}) if resp.request.resource_type in ('xhr','fetch') and urlparse(resp.url).hostname.endswith('worldclass.ru') else None)
        page.goto(TARGET,wait_until='domcontentloaded',timeout=45000)
        page.wait_for_timeout(1800)
        candidates=page.get_by_role('button',name=re.compile('^\\s*принять\\s*$',re.I))
        if candidates.count():
            try:
                candidates.first.click(timeout=7000)
                page.wait_for_timeout(700)
                log.append('Cookie overlay dismissed')
            except Exception as e:log.append('Cookie overlay not dismissed: '+str(e).splitlines()[0])
        before=get_links(page)
        log.append('Initial unique profile URLs: '+str(len(before)))
        button=page.locator('button[class*="_moreButton_"]').filter(has_text=re.compile(r'^\\s*показать\\s+ещ[её]\\s*$',re.I)).first
        if button.count()==0:
            log.append('Show-more button not found')
        else:
            log.append('Button: '+json.dumps(button.evaluate('e => ({html:e.outerHTML.slice(0,400), disabled:e.disabled, rect:(()=>{let r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()})'),ensure_ascii=False))
            try:
                button.scroll_into_view_if_needed(timeout=8000)
                button.click(timeout=12000)
                log.append('Playwright click succeeded')
            except Exception as e:
                log.append('Playwright click failed: '+str(e).splitlines()[0])
            for t in (1,3,7,12):
                page.wait_for_timeout((t-(0 if t==1 else {3:1,7:3,12:7}[t]))*1000)
                log.append(f'After {t} seconds: {len(get_links(page))} unique profile URLs')
        page.screenshot(path=str(HERE/'worldclass_diagnostic.png'),full_page=True)
        report={'time':datetime.now().isoformat(),'log':log,'network_and_errors':events[-100:],'initial_profile_urls':before,'final_profile_urls':get_links(page)}
        (HERE/'worldclass_diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('\n'.join(log))
        print('Отчёт:',HERE/'worldclass_diagnostic.json')
        print('Скриншот:',HERE/'worldclass_diagnostic.png')
        browser.close()

if __name__=='__main__':run()
