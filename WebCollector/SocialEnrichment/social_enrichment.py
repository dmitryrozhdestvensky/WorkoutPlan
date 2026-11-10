"""WebCollector Social Enrichment V1.4. Public source evidence, conservative merging.

No bypass of robots, anti-bot or authentication. Candidates are never auto-approved.
"""
from __future__ import annotations
import argparse
import csv
import ipaddress
import json
import re
import shutil
import socket
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
MASTER = HERE.parent / 'Data' / 'fitness_trainers_master.xlsx'
CANDIDATES = HERE / 'social_candidates.csv'
ERRORS = HERE / 'social_errors.csv'
STATE = HERE / 'social_progress.json'
HEADER = ['trainer_row','trainer_name','city','platform','profile_url','account_type','evidence_page',
          'evidence_label','evidence_type','confidence','status','collected_at']
ERROR_HEADER = ['trainer_row','trainer_name','source_url','error','detail']
DOMAINS = {'vk.com':'VK','m.vk.com':'VK','vk.ru':'VK','m.vk.ru':'VK','vkontakte.ru':'VK',
           'ok.ru':'OK','dzen.ru':'Дзен','zen.yandex.ru':'Дзен','t.me':'Telegram',
           'telegram.me':'Telegram','instagram.com':'Instagram','tiktok.com':'TikTok',
           'tenchat.ru':'TenChat'}
BAD_PATHS = {'VK':{'feed','video','wall','search','login','groups','away.php'},
             'Telegram':{'share','s','iv','login','addstickers','proxy','joinchat','c','blog','faq'},
             'Instagram':{'p','reel','reels','stories','explore','accounts','about'},
             'TikTok':{'discover','tag','music','video','login'},
             'OK':{'feed','group','groups','video','dk','photo','photos','topic','music','events','games','messages','notifications'},
             'Дзен':{'news','search','media'},
             'TenChat':{'feed','resume','search','company','connect','business','media','vacancy','partners','plus','wallet','post','posts','login','settings','notifications','messenger','profile','subscribe'}}
UA = 'WebCollectorSocialEnrichment/1.4 (public pages; contact: site administrator)'


def normalized(raw):
    raw = str(raw or '').strip()
    if raw.startswith('//'): raw = 'https:' + raw
    try:
        p = urlparse(raw)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password: return ''
        host = p.hostname.lower()
        if host in {'localhost','localhost.localdomain'}: return ''
        try:
            if not ipaddress.ip_address(host).is_global: return ''
        except ValueError: pass
        path = re.sub('/+', '/', unquote(p.path or '/')).rstrip('/')
        return urlunparse(('https',host,path,'','',''))
    except (ValueError,TypeError): return ''



def safe_fetch_url(raw):
    """Validate a public HTTP(S) URL WITHOUT stripping trailing slash or query.

    A path ending in / is significant for HTTP redirects.  This function is for
    fetching pages; normalized() remains the account-identity deduplication key.
    """
    raw = str(raw or '').strip()
    if raw.startswith('//'): raw = 'https:' + raw
    try:
        p = urlparse(raw)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise UnsafeRedirect('invalid URL or credentials')
        host = p.hostname.lower()
        if host in {'localhost', 'localhost.localdomain'}:
            raise UnsafeRedirect('local address')
        try:
            if not ipaddress.ip_address(host).is_global:
                raise UnsafeRedirect('nonpublic IP')
        except ValueError:
            pass
        if not re.fullmatch(r'[a-z0-9.-]+', host) or host.endswith('.'):
            raise UnsafeRedirect('invalid hostname')
        port = p.port
        if port not in (None, 80, 443):
            raise UnsafeRedirect('nonstandard port')
        # Preserve case, path, ending slash, and query for redirect handling.
        return urlunparse((p.scheme.lower(), host, p.path or '/', '', p.query, ''))
    except (ValueError, TypeError) as ex:
        raise UnsafeRedirect('invalid URL: '+str(ex)) from ex


def same_site(host1, host2):
    return (host1 or '').lower().removeprefix('www.') == (host2 or '').lower().removeprefix('www.')

def platform_of(raw):
    url = normalized(raw)
    if not url: return None
    p = urlparse(url)
    host = (p.hostname or '').removeprefix('www.')
    platform = DOMAINS.get(host)
    parts = [x for x in p.path.split('/') if x]
    if not platform or not parts or parts[0].lower() in BAD_PATHS.get(platform,set()): return None
    if platform == 'TikTok' and not parts[0].startswith('@'): return None
    if platform in {'Telegram','Instagram','TenChat','Дзен','TikTok'} and len(parts)>1: return None
    if platform == 'OK' and len(parts)>1 and not (len(parts)==2 and parts[0].lower()=='profile' and parts[1].isdigit()): return None
    return platform


def person_key(s):
    s = unicodedata.normalize('NFKC',str(s or '')).lower().replace('ё','е')
    return ' '.join(re.findall(r'[а-яa-z]+',s))


def account_type(platform,label,url):
    value = (label+' '+url).lower()
    if re.search(r'\bbot\b|бот|марафон.*бот',value): return 'bot'
    if 'Telegram' == platform and re.search(r'канал|рецепт|новости|авторский',value): return 'channel'
    if re.search(r'проект|команд|студи|фитнес.клуб|сообщество',value): return 'project'
    return 'profile_or_channel_unverified'


def is_shared_site_link(a):
    for node in a.parents:
        if getattr(node,'name',None) in {'nav','header','footer'}: return True
        if hasattr(node,'get'):
            attrs=(' '.join(str(x) for x in node.get('class',[]))+' '+str(node.get('id',''))).lower()
            if any(x in attrs for x in ('footer','header','navigation','share-widget','social-share','socials-common')): return True
    return False


def source_is_shared_listing(url):
    """A listing/group/feed can't provide an ownership link to an individual."""
    u = normalized(url)
    if not u: return True
    p = urlparse(u)
    host = (p.hostname or '').removeprefix('www.').removeprefix('m.')
    parts = [x.lower() for x in p.path.split('/') if x]
    if host == 'tenchat.ru':
        # Even a personal TenChat account page can contain recommendations;
        # it should not be scanned for OTHER account handles.
        return True
    if host == 'ok.ru': return True
    if host in ('t.me','telegram.me'): return True
    if host in ('instagram.com','vk.com','vk.ru','tiktok.com','dzen.ru'): return True
    if host == 'bbpro.ru' and (not parts or parts[0] == 'trainersinfo' and len(parts)<=2): return True
    return False


def candidate_reason(item):
    """Explain conservative audit results; no claim of identity verification."""
    url = normalized(item.get('profile_url'))
    src = normalized(item.get('evidence_page'))
    platform = item.get('platform','')
    if not url or platform_of(url)!=platform:
        return 'reject_invalid_account_url'
    if source_is_shared_listing(src):
        return 'reject_shared_listing_or_social_feed'
    source_host = (urlparse(src).hostname or '').removeprefix('www.')
    if source_host in ('tenchat.ru','ok.ru','t.me','telegram.me'):
        return 'reject_shared_listing_or_social_feed'
    if item.get('account_type') in ('bot','project'):
        return 'review_project_or_bot_not_personal'
    return 'review_source_link_not_owner_verified'


def audit_candidates(args):
    existing = load_csv(CANDIDATES)
    checked=[]
    for item in existing:
        item=dict(item)
        item['audit_reason']=candidate_reason(item)
        item['audit_decision']='reject' if item['audit_reason'].startswith('reject_') else 'review'
        # Any earlier approval is not transferred into the audited output.
        item['status']='rejected_auto' if item['audit_decision']=='reject' else 'review'
        checked.append(item)
    out=HERE/'social_candidates_audited_v12.csv'
    write_csv(out,checked,HEADER+['audit_decision','audit_reason'])
    from collections import Counter
    counts=Counter(c['audit_decision'] for c in checked)
    reasons=Counter(c['audit_reason'] for c in checked)
    print('АУДИТ:',len(checked),'кандидатов',dict(counts))
    for k,v in reasons.most_common(): print(' ',k,v)
    print('Результат:',out)
    print('Исходный CSV и основная база не изменены.')


def extract(html,source,trainer):
    if source_is_shared_listing(source): return []
    soup = BeautifulSoup(html,'html.parser')
    title = ' '.join(x.get_text(' ',strip=True) for x in soup.select('h1,h2')[:5])
    if soup.title: title += ' ' + soup.title.get_text(' ',strip=True)
    words = person_key(trainer).split()
    name_present = len(words)>=2 and all(w in person_key(title) for w in words[:2])
    # RegymSport has personal VK and Telegram link captions. Only collect links
    # explicitly marked "Trainer in VK/Telegram" on the named profile page.
    # Generic club/footer links, navigation, recommendations are NOT evidence.
    src = urlparse(source)
    if same_site(src.hostname, 'regymsport.ru') and src.path.startswith('/trenery/'):
        h1 = ' '.join(x.get_text(' ',strip=True) for x in soup.select('h1'))
        name_tokens = person_key(trainer).split()
        h1_tokens = person_key(h1).split()
        if len(name_tokens) < 2 or not all(w in h1_tokens for w in name_tokens[:2]):
            return []
        result=[]; seen=set()
        for a in soup.select('a[href]'):
            label = ' '.join(a.stripped_strings).strip()
            if is_shared_site_link(a): continue
            if any(x.name=='section' and any(re.search(r'другие\s+тренер|похожие\s+тренер', h.get_text(' ',strip=True),re.I) for h in x.select('h2,h3')) for x in a.parents if getattr(x,'name',None)): continue
            if re.search(r'^тренер\s+во?\s*[«\"„]?вконтакте[»\"]?$',label,re.I) or re.search(r'^тренер\s+в\s+vk$',label,re.I):
                expected='VK'
            elif re.search(r'^тренер\s+в\s+telegram$',label,re.I) or re.search(r'^тренер\s+в\s+телеграм(?:е)?$',label,re.I):
                expected='Telegram'
            else:
                continue
            dest = normalized(urljoin(source,a.get('href','')))
            if platform_of(dest)!=expected or (expected,dest) in seen: continue
            seen.add((expected,dest))
            result.append({'platform':expected,'profile_url':dest,
                           'account_type':account_type(expected,label,dest),
                           'evidence_label':label[:150],
                           'confidence':'source_name_match',
                           'evidence_type':'именная анкета RegymSport; явная ссылка на '+expected+'; владение не проверено'})
        return result
    result=[];seen=set()
    for a in soup.select('a[href]'):
        if is_shared_site_link(a): continue
        dest = normalized(urljoin(source,a.get('href','')))
        platform = platform_of(dest)
        if not platform or (platform,dest) in seen: continue
        if normalized(source)==dest: continue
        label = a.get_text(' ',strip=True)[:150]
        parent_text = a.parent.get_text(' ',strip=True)[:200] if a.parent else ''
        if re.search(r'поделиться|share|репост|поделитесь',label+' '+parent_text,re.I): continue
        seen.add((platform,dest))
        result.append({'platform':platform,'profile_url':dest,'account_type':account_type(platform,label,dest),
                       'evidence_label':label or '[без подписи]',
                       'confidence':'source_name_match' if name_present else 'review',
                       'evidence_type':'ссылка на исходной странице; владение не проверено'})
    return result


def load_csv(path):
    if not path.exists(): return []
    with path.open('r',newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f,delimiter=';'))


def write_csv(path,records,columns):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=columns,delimiter=';',extrasaction='ignore')
        w.writeheader();w.writerows(records)
    tmp.replace(path)


def master_rows():
    wb=load_workbook(MASTER,read_only=True,data_only=True)
    ws=wb['Тренеры']; columns=[str(c.value or '').strip() for c in ws[1]]
    try:
        for ix, values in enumerate(ws.iter_rows(min_row=2,values_only=True),start=2):
            row=dict(zip(columns,values))
            if row.get('Тренер / имя'): yield ix,row
    finally: wb.close()


def source_url(row):
    options = [row.get(x) for x in ('Страница тренера в источнике','URL источника','Сайт / мультиссылка')]
    for raw in options:
        url=normalized(raw)
        if not url: continue
        p=urlparse(url)
        if platform_of(url): continue
        # An intermediate VK Link URL is not a trainer webpage; handle separately if it is a source.
        if p.hostname in {'vk.link','www.vk.link'}: return url
        if p.path in ('','/','/trainersinfo','/coaches','/trainers'): continue
        return url
    return ''


class RobotsUnavailable(Exception): pass
class RobotsDisallowed(Exception): pass
class UnsafeRedirect(Exception): pass


def robots_check(session,url,cache):
    p=urlparse(url); origin=f'{p.scheme}://{p.netloc}'
    if origin not in cache:
        try:
            resp=session.get(origin+'/robots.txt',timeout=12,allow_redirects=False)
            if resp.status_code in (404,410): lines=[]
            elif resp.status_code==200: lines=resp.text.splitlines()
            else: raise RobotsUnavailable('robots HTTP '+str(resp.status_code))
            parser=RobotFileParser();parser.parse(lines)
            cache[origin]=('ok',parser)
        except requests.RequestException as exc:
            cache[origin]=('unavailable',type(exc).__name__)
        except RobotsUnavailable as exc:
            cache[origin]=('unavailable',str(exc))
    status,data=cache[origin]
    if status!='ok': raise RobotsUnavailable('robots.txt unavailable: '+data)
    if not data.can_fetch(UA,url): raise RobotsDisallowed('robots.txt disallow')


def get_public_html(session,url,cache):
    """Follow same-site redirects, preserving the exact trailing slash and query.

    Robots permission is checked on EACH destination; cross-site redirects are
    refused.  A true redirect cycle is logged instead of repeatedly requesting
    a rewritten URL.
    """
    current=safe_fetch_url(url)
    visited=set()
    for _ in range(8):
        if current in visited:
            raise UnsafeRedirect('redirect cycle: '+current)
        visited.add(current)
        robots_check(session,current,cache)
        r=session.get(current,timeout=22,allow_redirects=False)
        if r.status_code in (301,302,303,307,308):
            location=r.headers.get('Location','').strip()
            if not location: raise UnsafeRedirect('redirect without Location')
            next_url=safe_fetch_url(urljoin(current,location))
            old=urlparse(current).hostname or ''
            new=urlparse(next_url).hostname or ''
            if not same_site(old,new):
                raise UnsafeRedirect(f'redirect changed domain: {old} -> {new}; review manually')
            # Keep the slash: /trainer/name and /trainer/name/ are different
            # request URLs even though normalized() deduplicates them in CSV.
            current=next_url
            continue
        r.raise_for_status()
        if 'text/html' not in r.headers.get('Content-Type','').lower():
            raise ValueError('not HTML')
        return r.text[:2_000_000], current
    raise UnsafeRedirect('too many redirects')


def state_read():
    try: return set(json.loads(STATE.read_text(encoding='utf-8')).get('done',[]))
    except (FileNotFoundError,ValueError): return set()


def state_write(done):
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps({'done':sorted(done)},ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(STATE)


def collect(args):
    if not MASTER.exists(): raise SystemExit('Не найдена база: '+str(MASTER))
    candidates=load_csv(CANDIDATES); errors=load_csv(ERRORS);done=state_read()
    # V1 incorrectly marked transient robots failures as completed. Unmark those.
    legacy_retry={str(e.get('trainer_row'))+'|'+str(e.get('source_url')) for e in errors
                  if 'robots.txt unavailable' in str(e.get('error','')).lower()}
    done.difference_update(legacy_retry)
    seen={(str(c.get('trainer_row')),c.get('platform'),normalized(c.get('profile_url'))) for c in candidates}
    session=requests.Session();session.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
    robots={}; domain_failed=set(); n=0; new_total=0
    for idx,row in master_rows():
        if n>=args.max_profiles: break
        url=source_url(row)
        if not url:continue
        if args.only_regymsport and not same_site(urlparse(url).hostname, 'regymsport.ru'): continue
        if source_is_shared_listing(url): continue
        key=f'{idx}|{url}'
        if key in done and not (args.only_regymsport and args.rescan_regymsport):continue
        host=urlparse(url).hostname or ''
        if host in domain_failed:continue  # one error per origin per run, retry next run
        name=str(row['Тренер / имя']);n+=1
        try:
            if host.removeprefix('www.')=='vk.link':
                # Don't follow shorteners with stored cookies or treat redirects as verified.
                raise UnsafeRedirect('vk.link shortlink: manual review required')
            html,evidence=get_public_html(session,url,robots)
            discovered=extract(html,evidence,name)
            add=0
            for c in discovered:
                if normalized(row.get(c['platform'])) == c['profile_url']:continue
                itemkey=(str(idx),c['platform'],c['profile_url'])
                if itemkey in seen:continue
                candidates.append({'trainer_row':idx,'trainer_name':name,'city':str(row.get('Город') or ''),
                                   **c,'evidence_page':evidence,'status':'review',
                                   'collected_at':datetime.now(timezone.utc).strftime('%Y-%m-%d')})
                seen.add(itemkey);add+=1;new_total+=1
            print(f'[{n}] row={idx} {name}: links +{add}',flush=True)
            done.add(key)
        except RobotsDisallowed as ex:
            print(f'[{n}] row={idx} {name}: SKIP {ex}',flush=True)
            done.add(key)
            errors.append({'trainer_row':idx,'trainer_name':name,'source_url':url,'error':'robots disallow','detail':str(ex)})
        except RobotsUnavailable as ex:
            domain_failed.add(host)
            print(f'[{n}] domain={host}: SKIP once per run ({ex})',flush=True)
            errors.append({'trainer_row':idx,'trainer_name':name,'source_url':url,'error':'robots unavailable','detail':str(ex)})
            # Transient availability failure is NOT marked done.
        except (requests.RequestException,UnsafeRedirect,ValueError) as ex:
            print(f'[{n}] row={idx} {name}: SKIP {ex}',flush=True)
            errors.append({'trainer_row':idx,'trainer_name':name,'source_url':url,'error':type(ex).__name__,'detail':str(ex)[:240]})
            # Don't retry in a tight loop in the same run; allow an explicit future retry.
        write_csv(CANDIDATES,candidates,HEADER)
        write_csv(ERRORS,errors,ERROR_HEADER)
        state_write(done)
        time.sleep(max(1.0,args.delay))
    print(f'ГОТОВО: обработано {n}; новых кандидатов {new_total}; всего кандидатов {len(candidates)}; ошибок в журнале {len(errors)}')
    print('Исходная база НЕ изменена. Проверяйте social_candidates.csv перед одобрением.')


def apply(args):
    if not MASTER.exists(): raise SystemExit('Не найдена основная база')
    approved=[x for x in load_csv(CANDIDATES) if x.get('status','').strip().lower()=='approved' and candidate_reason(x)=='review_source_link_not_owner_verified']
    print('Применение исключает общие каталоги, посты, группы, ботов и проекты.')
    wb=load_workbook(MASTER);ws=wb['Тренеры'];headers={str(c.value):i+1 for i,c in enumerate(ws[1])}
    source=wb['Источники профилей'] if 'Источники профилей' in wb.sheetnames else wb.create_sheet('Источники профилей')
    if source.max_row==1 and not source.cell(1,1).value:
        source.append(['ID строки тренера','Тренер','Площадка / источник','Точный URL','Тип ссылки','Дата обнаружения','Статус подтверждения'])
    accounts=wb['Социальные аккаунты'] if 'Социальные аккаунты' in wb.sheetnames else wb.create_sheet('Социальные аккаунты')
    if accounts.max_row==1 and not accounts.cell(1,1).value:
        accounts.append(['Строка тренера','ФИО','Платформа','URL аккаунта','Тип аккаунта','URL доказательства','Подпись ссылки','Проверка','Дата'])
    indexed={(str(accounts.cell(r,1).value),str(accounts.cell(r,3).value),normalized(accounts.cell(r,4).value)) for r in range(2,accounts.max_row+1)}
    main_updates=[];account_add=[];conflicts=[];reserve={}
    for a in approved:
        try: idx=int(a.get('trainer_row',0))
        except ValueError:continue
        plat=a.get('platform','');u=normalized(a.get('profile_url'));ev=normalized(a.get('evidence_page'))
        if idx<2 or idx>ws.max_row or plat not in DOMAINS.values() or platform_of(u)!=plat or not ev: continue
        name=str(ws.cell(idx,headers['Тренер / имя']).value or '')
        if person_key(name)!=person_key(a.get('trainer_name')):
            conflicts.append((idx,'name differs',u));continue
        key=(str(idx),plat,u)
        if key in indexed:continue
        account_add.append((idx,name,plat,u,a.get('account_type','profile_or_channel_unverified'),ev,a.get('evidence_label',''),
                            'Одобрено оператором; владение не подтверждено',a.get('collected_at','')))
        indexed.add(key)
        # Do not overwrite a different platform URL; retain multiple handles in separate accounts sheet.
        if plat in headers and a.get('account_type') not in ('bot','project'):
            old=normalized(ws.cell(idx,headers[plat]).value)
            if not old and (idx,plat) not in reserve:
                reserve[(idx,plat)]=u
                main_updates.append((idx,headers[plat],u))
            elif old and old!=u:conflicts.append((idx,'additional '+plat+' account (preserved)',u))
    print(f'Одобрено: {len(approved)}; новых записей аккаунтов: {len(account_add)}; новых главных ссылок: {len(main_updates)}; конфликтов/доп.аккаунтов: {len(conflicts)}')
    if args.dry_run:
        print('DRY RUN: файлы не изменены.');return
    if not account_add:
        print('Нет новых одобренных ссылок.');return
    for r,c,u in main_updates:ws.cell(r,c).value=u
    for values in account_add:accounts.append(values)
    preview=HERE/'fitness_trainers_social_preview.xlsx'
    wb.save(preview)
    print('Предварительный Excel:',preview,'(основная база не изменена)')
    print('ВНИМАНИЕ: перед переносом preview в Data вручную сделайте резервную копию текущего master.')


def main():
    p=argparse.ArgumentParser(description='Social Enrichment V1.4 — проверяемый поиск публичных ссылок')
    p.add_argument('--max-profiles',type=int,default=20)
    p.add_argument('--only-regymsport',action='store_true',help='Тестировать только персональные анкеты RegymSport')
    p.add_argument('--rescan-regymsport',action='store_true',help='Повторно проверить ранее обработанные RegymSport анкеты; старые кандидаты сохраняются и дедуплицируются')
    p.add_argument('--delay',type=float,default=2.0)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--audit-candidates',action='store_true',help='Безопасно классифицировать существующий CSV без изменения оригинала')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.rescan_regymsport and not a.only_regymsport:
        p.error('--rescan-regymsport требует --only-regymsport')
    if a.audit_candidates: audit_candidates(a)
    elif a.apply:apply(a)
    else:collect(a)

if __name__=='__main__': main()
