# -*- coding: utf-8 -*-
"""Read-only browser-side API diagnostic for World Class catalog."""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
START = 'https://www.worldclass.ru/trainers/'
REDACT = re.compile(r'(token|key|secret|auth|session|password|cookie)', re.I)

def summarized_json(obj, depth=0):
    if isinstance(obj, list):
        result = {'type': 'list', 'count': len(obj)}
        if obj and isinstance(obj[0], dict):
            result['item_keys'] = sorted(obj[0].keys())[:60]
        return result
    if isinstance(obj, dict):
        result = {'type': 'dict', 'keys': sorted(obj.keys())[:80]}
        if depth < 2:
            result['nested'] = {str(k): summarized_json(v, depth+1) for k, v in obj.items() if isinstance(v, (list, dict))}
        return result
    return {'type': type(obj).__name__}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clicks', type=int, default=38)
    ap.add_argument('--wait', type=float, default=3.0)
    ap.add_argument('--headless', action='store_true')
    args = ap.parse_args()
    events=[]
    out = HERE / 'worldclass_api_diagnostic_result.json'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(locale='ru-RU', viewport={'width': 1400, 'height': 900})
        page = ctx.new_page()
        def record_response(resp):
            u=urlsplit(resp.url)
            if not u.netloc.endswith('worldclass.ru') or not u.path.startswith('/api/trainers'):
                return
            item={
                'time':datetime.now().isoformat(timespec='seconds'),
                'path':u.path,
                'query':{k: ('[redacted]' if REDACT.search(k) else v[:120]) for k,v in parse_qsl(u.query)},
                'method':resp.request.method,
                'status':resp.status,
                'request_post_data_present': bool(resp.request.post_data),
            }
            try:
                body=resp.json()
                item['response_structure']=summarized_json(body)
            except Exception as e:
                item['response_error']=str(e)[:160]
            events.append(item)
        page.on('response',record_response)
        try:
            page.goto(START,wait_until='domcontentloaded',timeout=60000)
            page.wait_for_timeout(1500)
            for step in range(args.clicks):
                btn=page.get_by_role('button',name=re.compile(r'^\s*показать\s+ещ[её]\s*$',re.I))
                try:
                    link_count=page.locator('a[href*="/trainers/"]').count()
                    visible=[btn.nth(i) for i in range(min(btn.count(),4)) if btn.nth(i).is_visible()]
                    if not visible:
                        print('No visible show-more button; stop at',step,'clicks; links',link_count, flush=True)
                        break
                    button=visible[-1]
                    busy=button.get_attribute('aria-busy')
                    if busy=='true' or button.is_disabled():
                        print(f'#{step+1}: busy={busy}, waiting',flush=True)
                        page.wait_for_timeout(int(args.wait*2000))
                        continue
                    button.scroll_into_view_if_needed(timeout=8000)
                    button.click(timeout=12000)
                    page.wait_for_timeout(int(args.wait*1000))
                    after=page.locator('a[href*="/trainers/"]').count()
                    print(f'#{step+1}: links {link_count} -> {after}, api responses={len(events)}',flush=True)
                except Exception as e:
                    events.append({'step':step+1,'click_error':str(e).splitlines()[0][:250]})
                    print(f'#{step+1}: click issue: {str(e).splitlines()[0][:120]}',flush=True)
                    page.wait_for_timeout(int(args.wait*1000))
            page.wait_for_timeout(2000)
        finally:
            out.write_text(json.dumps({'created_at':datetime.now().isoformat(),'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()
    print('Diagnostic saved:',out)

if __name__=='__main__':
    main()
