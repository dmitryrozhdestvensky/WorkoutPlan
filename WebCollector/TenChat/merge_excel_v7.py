"""Merge V7 public-profile CSV with master workbook, preserving all existing sheets.
Run: .venv\\Scripts\\python.exe merge_excel_v7.py
"""
import csv
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/'fitness_trainers_base_215.xlsx'
CSV=ROOT/'tenchat_trainers_v7.csv'
OUTPUT=ROOT/'fitness_trainers_merged_v7.xlsx'


def norm(url):
    try:
        x=urlparse(str(url or '').strip())
        slug=x.path.strip('/')
        if x.hostname not in ('tenchat.ru','www.tenchat.ru') or not re.fullmatch(r'[a-zA-Z0-9_.-]+',slug):return ''
        return 'https://tenchat.ru/'+slug.lower()
    except (ValueError,TypeError):return ''


def clean(value):
    v=str(value or '').replace('\x00','').strip()
    return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v


def main():
    if not MASTER.exists():raise SystemExit(f'Не найден файл {MASTER.name}')
    if not CSV.exists():raise SystemExit(f'Не найден {CSV.name}. Сначала запустите сборщик.')
    wb=load_workbook(MASTER)
    ws=wb['Тренеры']
    cols={str(c.value or '').strip().lower():c.column for c in ws[1]}
    tc=cols.get('tenchat')
    if tc is None:raise SystemExit('В таблице Тренеры нет столбца TenChat')
    def column(key,default=None):return cols.get(key.lower(),default)
    name=column('тренер / имя',1)
    spec=column('специализация',3)
    source=column('url источника')
    status=column('статус проверки')
    notes=column('примечание')
    collected=column('дата сбора')
    existing=set()
    for row in ws.iter_rows(min_row=2,max_col=tc):
        u=norm(row[tc-1].value)
        if u:existing.add(u)
    with CSV.open(encoding='utf-8-sig',newline='') as f:
        imported=list(csv.DictReader(f,delimiter=';'))
    if imported and 'TenChat' not in imported[0]:raise SystemExit('CSV не содержит столбец TenChat')
    added=overlaps=invalid=0
    log=wb.create_sheet('Импорт V7') if 'Импорт V7' not in wb.sheetnames else wb.create_sheet('Импорт V7 (новый)')
    log.append(['Имя','TenChat','Результат','Специализации','Страницы-источники'])
    for record in imported:
        url=norm(record.get('TenChat'))
        nm=clean(record.get('Имя'))
        sp=clean(record.get('Специализации') or 'Фитнес')
        src=clean(record.get('Страницы-источники'))
        if not url:
            invalid+=1; result='Некорректный URL'
        elif url in existing:
            overlaps+=1; result='Уже существует'
        else:
            result='Добавлен';added+=1;existing.add(url)
            r=ws.max_row+1
            ws.cell(r,name,nm)
            ws.cell(r,tc,url)
            ws.cell(r,tc).hyperlink=url
            ws.cell(r,tc).style='Hyperlink'
            if spec:ws.cell(r,spec,sp)
            if source:ws.cell(r,source,(src.split(' | ')[0] if src else 'https://tenchat.ru/resume/'))
            if status:ws.cell(r,status,'Найдена ссылка в каталоге; владелец не подтверждён')
            if notes:ws.cell(r,notes,'Импорт V7; дедупликация по TenChat URL')
            if collected:ws.cell(r,collected,date.today().isoformat())
        log.append([nm,url or clean(record.get('TenChat')),result,sp,src])
    log.freeze_panes='A2';log.auto_filter.ref=log.dimensions
    for c in log[1]:
        c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True)
    for col,width in {'A':32,'B':45,'C':24,'D':36,'E':90}.items():log.column_dimensions[col].width=width
    ws.auto_filter.ref=f'A1:{get_column_letter(ws.max_column)}{ws.max_row}'
    # Previous 'Сводка' is a snapshot; update visible counts to avoid stale totals.
    if 'Сводка' in wb.sheetnames:
        sw=wb['Сводка']
        count=ws.max_row-1
        social={k:sum(bool(str(ws.cell(r,ix).value or '').strip()) for r in range(2,ws.max_row+1))
                for k in ('vk','ok','дзен','telegram','instagram','tiktok','tenchat') if (ix:=cols.get(k))}
        for row in sw:
            for cell in row:
                if isinstance(cell.value,str):
                    label=cell.value.strip().lower()
                    if label in ('всего тренеров','уникальных тренеров','количество тренеров'):
                        sw.cell(cell.row,cell.column+1,count)
                    elif label in ('vk','ok','дзен','telegram','instagram','tiktok','tenchat'):
                        sw.cell(cell.row,cell.column+1,social.get(label,0))
    stats=wb.create_sheet('Сводка V7') if 'Сводка V7' not in wb.sheetnames else wb.create_sheet('Сводка V7 (новая)')
    for a,b in [('Показатель','Значение'),('Всего тренеров',ws.max_row-1),('Импортировано строк',len(imported)),('Добавлено новых',added),('Совпадений по URL',overlaps),('Ошибочных URL',invalid),('Дата',date.today().isoformat())]:stats.append([a,b])
    stats.column_dimensions['A'].width=30;stats.column_dimensions['B'].width=25
    for cell in stats[1]:cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(color='FFFFFF',bold=True)
    wb.save(OUTPUT)
    print(f'ГОТОВО: всего {ws.max_row-1}; добавлено {added}; дубликатов {overlaps}; неверных URL {invalid}')
    print('Excel:',OUTPUT)

if __name__=='__main__': main()
