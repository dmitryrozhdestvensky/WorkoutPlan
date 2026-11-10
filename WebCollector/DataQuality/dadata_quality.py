#!/usr/bin/env python3
"""Conservative DaData name-quality pilot. Does not edit source workbook."""
from __future__ import annotations
import argparse, datetime, json, os, re, sqlite3, sys, time
from collections import defaultdict
from pathlib import Path
import requests
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

DEFAULT_MASTER = Path(r'E:\GoogleDrive\WorkoutPlan\WebCollector\Data\fitness_trainers_master.xlsx')
API_URL = 'https://cleaner.dadata.ru/api/v1/clean/name'
HEADERS = ['row','original_name','normalized_name','surname','name','patronymic','qc','difference','city','clubs','source_profile','checked_at']

def norm(s):
    return re.sub(r'\s+', ' ', str(s or '').strip()).casefold()

def require_headers(sheet):
    hdr = {norm(c.value): i for i,c in enumerate(sheet[1])}
    name = hdr.get('тренер / имя')
    if name is None:
        raise ValueError('Не найдена колонка «Тренер / имя» на первом листе')
    return hdr, name

def read_master(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        ws=wb.worksheets[0]
        hdr, name_idx=require_headers(ws)
        out=[]
        for cells in ws.iter_rows(min_row=2):
            val=cells[name_idx].value
            if not isinstance(val,str) or not val.strip(): continue
            def get(key):
                idx=hdr.get(key)
                return str(cells[idx].value or '') if idx is not None else ''
            out.append({'row':cells[0].row,'original_name':val.strip(), 'city':get('город'),
              'clubs':get('клубы ddx fitness') or get('клубы regymsport'),
              'source_profile':get('страница тренера в источнике') or get('url источника')})
        return out
    finally: wb.close()

def selection(rows, size):
    # First potentially tricky names, then a deterministic spread of remaining names.
    scores=defaultdict(int)
    by_name=defaultdict(list)
    for x in rows: by_name[norm(x['original_name'])].append(x['row'])
    for r in rows:
        n=r['original_name']
        tokens=n.split()
        scores[r['row']]= (4 if len(tokens)!=3 else 0) + (3 if len(by_name[norm(n)])>1 else 0) + (2 if '-' in n or 'ё' in n.casefold() else 0) + (1 if not r['city'] else 0)
    ordered=sorted(rows,key=lambda r:(-scores[r['row']],r['row']))
    return ordered[:size]

def db_init(db):
    conn=sqlite3.connect(db)
    conn.execute('''CREATE TABLE IF NOT EXISTS names (master_row INTEGER PRIMARY KEY, original_name TEXT NOT NULL,
      normalized_name TEXT, surname TEXT, name TEXT, patronymic TEXT, qc INTEGER, city TEXT, clubs TEXT,
      source_profile TEXT, checked_at TEXT NOT NULL)''')
    conn.commit()
    return conn

def clean_one(session, name, key, secret):
    res=session.post(API_URL, headers={'Authorization':'Token '+key,'X-Secret':secret,
      'Accept':'application/json','Content-Type':'application/json'},json=[name],timeout=25)
    if res.status_code != 200:
        detail={400:'неверный запрос',401:'неверный API/секретный ключ',403:'почта не подтверждена либо отсутствует доступный баланс/лимит',429:'превышен лимит скорости'}.get(res.status_code,'ошибка сервера')
        raise RuntimeError(f'DaData HTTP {res.status_code}: {detail}. Остановка без повторных запросов.')
    obj=res.json()
    if not isinstance(obj,list) or len(obj)!=1 or not isinstance(obj[0],dict): raise RuntimeError('Неожиданный формат ответа DaData')
    return obj[0]

def record(conn, source, payload):
    conn.execute('''INSERT OR REPLACE INTO names (master_row,original_name,normalized_name,surname,name,patronymic,qc,city,clubs,source_profile,checked_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(
      source['row'],source['original_name'],payload.get('result') or '',payload.get('surname') or '',payload.get('name') or '',
      payload.get('patronymic') or '',payload.get('qc'),source['city'],source['clubs'],source['source_profile'],
      datetime.datetime.now().isoformat(timespec='seconds')))
    conn.commit()

def run(args):
    rows=read_master(Path(args.master))
    if not rows: raise ValueError('Нет анкет для обработки')
    Path(args.out).mkdir(parents=True,exist_ok=True)
    conn=db_init(Path(args.out)/'dadata_quality_progress.sqlite3')
    selected=selection(rows,args.sample_size)
    completed={r[0] for r in conn.execute('SELECT master_row FROM names')}
    pending=[r for r in selected if r['row'] not in completed]
    print(f'В базе: {len(rows)}; в выборке: {len(selected)}; обработано ранее в выборке: {len(selected)-len(pending)}')
    if args.command=='preview':
        for x in pending[:min(args.limit,10)]: print(f"row={x['row']}: {x['original_name']} | {x['city']} | {x['clubs']}")
        print('API запросы НЕ выполнялись.')
        return
    key=os.environ.get('DADATA_API_KEY','').strip()
    secret=os.environ.get('DADATA_SECRET_KEY','').strip()
    if not key or not secret: raise ValueError('Задайте DADATA_API_KEY и DADATA_SECRET_KEY только в текущем окне PowerShell')
    if args.command=='probe': count=1
    else: count=min(args.limit,len(pending))
    if count < 1:
        print('Нет новых строк для обработки. Для отчёта используйте report.')
        return
    if args.command=='run' and not args.confirm_requests:
        raise ValueError('Для реальных запросов добавьте --confirm-requests. Каждый запрос может расходовать лимит или средства.')
    session=requests.Session()
    success=0
    for i,x in enumerate(pending[:count],1):
        try:
            d=clean_one(session,x['original_name'],key,secret)
        except (requests.RequestException,ValueError,RuntimeError) as exc:
            print('ОСТАНОВКА:',str(exc))
            break
        record(conn,x,d)
        success+=1
        print(f"[{i}/{count}] row={x['row']} {x['original_name']} → {d.get('result')} (qc={d.get('qc')})")
        if i<count: time.sleep(.25)
    print(f'Завершено за запуск: {success}; накоплено в базе ответов: {conn.execute("SELECT count(*) FROM names").fetchone()[0]}')
    print('Основной Excel не изменён.')

def make_report(args):
    master=read_master(Path(args.master))
    conn=db_init(Path(args.out)/'dadata_quality_progress.sqlite3')
    cur=conn.execute('SELECT master_row,original_name,normalized_name,surname,name,patronymic,qc,city,clubs,source_profile,checked_at FROM names ORDER BY master_row')
    records=cur.fetchall()
    w=Workbook(); ws=w.active;ws.title='Проверка ФИО';ws.append(HEADERS)
    for x in records:
        row,original,normalized,surname,name,patr,qc,city,clubs,src,at=x
        ws.append([row,original,normalized,surname,name,patr,qc,'изменено' if norm(original)!=norm(normalized) else 'без изменений',city,clubs,src,at])
    # Potential duplicates across original source database, not identity resolution.
    groups=defaultdict(list)
    for x in master: groups[norm(x['original_name'])].append(x)
    double=w.create_sheet('Совпадения ФИО'); double.append(['Нормализованное ФИО','Строки базы','Количество','Комментарий'])
    for k,people in sorted(groups.items()):
        if len(people)>1: double.append([people[0]['original_name'],', '.join(str(y['row']) for y in people),len(people),'Не объединять без доказательств'])
    normgroups=defaultdict(list)
    for x in records:
        if x[2]: normgroups[norm(x[2])].append(x)
    sheet=w.create_sheet('Совпадения DaData');sheet.append(['ФИО DaData','Строки','Количество','Примечание'])
    for k,people in sorted(normgroups.items()):
        if len(people)>1: sheet.append([people[0][2],', '.join(str(y[0]) for y in people),len(people),'Возможные однофамильцы; ручная проверка'])
    summary=w.create_sheet('Итоги',0)
    summary.append(['Показатель','Значение']);summary.append(['Записей в основной базе',len(master)])
    summary.append(['Запросов DaData успешно завершено',len(records)])
    summary.append(['Изменено написание ФИО',sum(norm(x[1])!=norm(x[2]) for x in records)])
    summary.append(['qc=1 (проверить вручную)',sum(x[6]==1 for x in records)])
    summary.append(['Одинаковые ФИО в исходной базе (групп)',double.max_row-1])
    summary.append(['Группы одинаковых нормализованных ФИО DaData',sheet.max_row-1])
    summary.append(['Важно','DaData не подтверждает личность; не объединяйте людей автоматически'])
    for sh in w:
        sh.freeze_panes='A2'; sh.auto_filter.ref=sh.dimensions
        for cell in sh[1]:cell.fill=PatternFill('solid',fgColor='193654');cell.font=Font(color='FFFFFF',bold=True)
        for j in range(1,sh.max_column+1):
            sh.column_dimensions[get_column_letter(j)].width = 14 if j in (1,7) else (40 if sh.title=='Проверка ФИО' and j in (10,11) else 26)
        for row in sh.iter_rows(min_row=2):
            for c in row:c.alignment=Alignment(vertical='top',wrap_text=False)
    out=Path(args.out)/'dadata_quality_report.xlsx';w.save(out)
    print(f'Отчёт: {out}\nОбработано ответов: {len(records)}. Исходная база не изменена.')

def main():
    p=argparse.ArgumentParser(description='DaData QA pilot. Original Excel is never edited.')
    p.add_argument('command',choices=['preview','probe','run','report'])
    p.add_argument('--master',default=str(DEFAULT_MASTER)); p.add_argument('--out',default=str(Path(__file__).resolve().parent))
    p.add_argument('--sample-size',type=int,default=100);p.add_argument('--limit',type=int,default=10)
    p.add_argument('--confirm-requests',action='store_true')
    args=p.parse_args()
    if not 1<=args.sample_size<=100: p.error('--sample-size must be 1..100 (pilot limit)')
    if not 1<=args.limit<=100: p.error('--limit must be 1..100')
    try:
        if args.command=='report':make_report(args)
        else: run(args)
    except Exception as e:
        print('ERROR:',str(e),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
