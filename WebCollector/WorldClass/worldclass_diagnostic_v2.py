"""World Class show-more diagnostic, no changes to collected data.
Run with the same Python environment used for collect_worldclass.py.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'worldclass_diagnostic_v2.json'
SCREEN=ROOT/'worldclass_diagnostic_v2.png'
SITE='https://www.worldclass.ru/trainers/'
URL_RE=re.compile(r'^/trainers/\d+/?$')

def profile_urls(page):
    urls=page.locator('a[href]').evaluate_all('els => els.map(a=>a.href)')
    return sorted({u.split('?')[0].rstrip('/') for u in urls
        if urlsplit(u).hostname in ('www.worldclass.ru','worldclass.ru') and URL_RE.match(urlsplit(u).path)})

def safe_url(url):
    p=urlsplit(url)
    return f'{p.scheme}://{p.netloc}{p.path}'

def main():
    data={'date':datetime.now().isoformat(timespec='seconds'),'initial':{},'click':{},'final':{},'network':[],'notes':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False)
        context=browser.new_context(locale='ru-RU',viewport={'width':1280,'height':900})
        page=context.new_page()
        page.on('requestfailed',lambda req: data['network'].append({'type':'requestfailed','method':req.method,'url':safe_url(req.url),'failure':req.failure}))
        page.on('response',lambda res: data['network'].append({'type':'http_error','status':res.status,'url':safe_url(res.url)}) if res.status>=400 else None)
        page.on('pageerror',lambda exc:data['notes'].append('JS error: '+str(exc)[:250]))
        try:
            page.goto(SITE,wait_until='domcontentloaded',timeout=45000)
            page.wait_for_timeout(2500)
            accept=page.get_by_role('button',name=re.compile(r'^\s*Принять\s*$',re.I))
            if accept.count() and accept.first.is_visible():
                accept.first.click(timeout=10000)
                data['notes'].append('Cookie modal accepted')
                page.wait_for_timeout(600)
            before=profile_urls(page)
            data['initial']['count']=len(before)
            data['initial']['urls']=before
            buttons=page.locator('button[class*="_moreButton_"]')
            data['initial']['buttons_count']=buttons.count()
            data['initial']['buttons']=buttons.evaluate_all('els => els.map(el=>({outerHTML:el.outerHTML.slice(0,500),text:(el.innerText||"").trim(),rect:{width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height},disabled:el.disabled,display:getComputedStyle(el).display,visibility:getComputedStyle(el).visibility}))')
            print('Начальные профили:',len(before),'кнопок:',buttons.count(),flush=True)
            if buttons.count():
                button=buttons.first
                data['click']['visible']=button.is_visible()
                data['click']['enabled']=button.is_enabled()
                button.scroll_into_view_if_needed(timeout=10000)
                try:
                    button.click(timeout=15000)
                    data['click']['result']='clicked'
                except Exception as exc:
                    data['click']['result']='failed'
                    data['click']['error']=str(exc)[-1500:]
                for sec in range(1,16):
                    page.wait_for_timeout(1000)
                    current=profile_urls(page)
                    if len(current)>len(before):
                        data['click']['seconds_to_new_urls']=sec
                        break
                after=profile_urls(page)
                print('После нажатия:',len(after),flush=True)
                data['final']={'count':len(after),'new_urls':sorted(set(after)-set(before))}
            else:
                data['click']['result']='button-not-found-by-class'
            page.screenshot(path=str(SCREEN),full_page=True)
        except Exception as exc:
            data['notes'].append('Diagnostic failed: '+repr(exc))
            try:page.screenshot(path=str(SCREEN),full_page=True)
            except Exception:pass
        finally:
            data['network']=data['network'][-120:]
            OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print('Отчёт:',OUTPUT,flush=True)
            print('Скриншот:',SCREEN,flush=True)
            browser.close()

if __name__=='__main__':
    main()
