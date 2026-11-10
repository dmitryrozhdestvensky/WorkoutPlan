"""Merge DDX public profiles into shared master workbook, with review & provenance.
Uses openpyxl on user's Windows computer. Never alters master without --apply-master.
"""
from __future__ import annotations
import argparse,csv,re,shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

HERE=Path(__file__).resolve().parent
MASTER=HERE.parent/'Data'/'fitness_trainers_master.xlsx'
INPUT=HERE/'ddxfitness_trainers.csv'
OUTPUT=HERE/'fitness_trainers_merged_ddxfitness.xlsx'
DATE=datetime.now().date().isoformat()

def norm(v):return re.sub(r'\s+',' ',str(v or '').strip()).casefold()
def urlkey(v):
    u=urlsplit(str(v or '').strip())
    return (u.hostname or '').removeprefix('www.').lower()+u.path.rstrip('/').lower() if u.hostname else ''
def read_csv():
    with INPUT.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f,delimiter=';'))
def sheet(wb,name,columns):
    ws=wb[name] if name in wb.sheetnames else wb.create_sheet(name)
    if ws.max_row==1 and ws.cell(1,1).value is None:ws.append(columns)
    return ws

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply-master',action='store_true',help='Create dated backup then replace global master with merged result')
    args=parser.parse_args()
    if not MASTER.exists():raise SystemExit(f'Не найдена общая база: {MASTER}')
    if not INPUT.exists():raise SystemExit(f'Не найден CSV: {INPUT}')
    wb=load_workbook(MASTER)
    if 'Тренеры' not in wb.sheetnames:raise SystemExit('Нет листа «Тренеры» в общей базе')
    ws=wb['Тренеры']
    hdr={str(c.value).strip():c.column for c in ws[1] if c.value is not None}
    def col(name):
        if name not in hdr:
            idx=ws.max_column+1;ws.cell(1,idx,name);hdr[name]=idx
        return hdr[name]
    columns=['Тренер / имя','Город','Специализация','Источник — название','Страница тренера в источнике','URL источника','Дополнительные источники — URL','Дата сбора','Статус проверки','Клубы DDX Fitness','Роль DDX Fitness','Стаж DDX (лет)','Образование DDX Fitness','VK','OK','Дзен','Telegram','Instagram','TikTok','TenChat']
    for name in columns:col(name)
    sources=sheet(wb,'Источники профилей',['ID строки тренера','Тренер','Площадка / источник','Точный URL','Тип ссылки','Дата обнаружения','Статус подтверждения'])
    review=sheet(wb,'Проверить совпадения',['ФИО','Город','URL DDX','Возможные строки базы','Причина'])
    log=sheet(wb,'Импорт DDX Fitness',['Имя','URL DDX','Действие','Строка','Дата'])
    seen_urls={}; name_rows={}; existing_sources=set()
    for r in range(2,ws.max_row+1):
        for field in ('Страница тренера в источнике','URL источника','Сайт / мультиссылка','Дополнительные источники — URL'):
            if field in hdr:
                val=str(ws.cell(r,col(field)).value or '')
                for part in re.split(r'\s*[|;,]\s*',val):
                    key=urlkey(part)
                    if key.startswith('ddxfitness.ru/coaches/'):
                        seen_urls[key]=r
        n=norm(ws.cell(r,col('Тренер / имя')).value)
        if n:name_rows.setdefault(n,[]).append(r)
    for r in range(2,sources.max_row+1):
        k=urlkey(sources.cell(r,4).value)
        if k.startswith('ddxfitness.ru/coaches/'):
            existing_sources.add((str(sources.cell(r,1).value),k))
            # Source sheet stores original row ownership.
            try:seen_urls.setdefault(k,int(sources.cell(r,1).value))
            except (ValueError,TypeError):pass
    social={'vk':'VK','ok':'OK','dzen':'Дзен','telegram':'Telegram','instagram':'Instagram','tiktok':'TikTok','tenchat':'TenChat'}
    stats={'csv_rows':0,'new':0,'matched_url':0,'review':0,'invalid':0,'social_added':0}
    for item in read_csv():
        name=str(item.get('name') or '').strip();url=str(item.get('source_profile_url') or '').strip();uk=urlkey(url)
        if not name or not re.fullmatch(r'ddxfitness\.ru/coaches/\d+',uk):
            stats['invalid']+=1;continue
        stats['csv_rows']+=1
        if uk in seen_urls:
            r=seen_urls[uk];stats['matched_url']+=1;action='existing URL'
        elif norm(name) in name_rows:
            review.append([name,item.get('city',''),url,', '.join(map(str,name_rows[norm(name)])),'Совпадает ФИО; нужна ручная проверка личности'])
            log.append([name,url,'review','',DATE]);stats['review']+=1;continue
        else:
            r=ws.max_row+1
            values={
                'Тренер / имя':name,'Город':item.get('city',''),
                'Специализация':item.get('specialty') or item.get('role') or '',
                'Источник — название':'DDX Fitness',
                'Страница тренера в источнике':url,'URL источника':url,
                'Дата сбора':item.get('date_collected') or DATE,
                'Статус проверки':'Публичная анкета DDX; личность и соцсети не подтверждены',
                'Клубы DDX Fitness':item.get('clubs',''),
                'Роль DDX Fitness':item.get('role',''),
                'Стаж DDX (лет)':int(item['experience_years']) if str(item.get('experience_years','')).isdigit() else '',
                'Образование DDX Fitness':item.get('education','')}
            for k,v in values.items():ws.cell(r,col(k),v)
            stats['new']+=1;action='new'
            name_rows.setdefault(norm(name),[]).append(r)
            seen_urls[uk]=r
        # Add personal social links only if empty. Never replace existing link.
        for key,label in social.items():
            val=str(item.get(key) or '').strip()
            if val and not ws.cell(r,col(label)).value:
                ws.cell(r,col(label),val);stats['social_added']+=1
        if (str(r),uk) not in existing_sources:
            sources.append([r,name,'DDX Fitness',url,'Персональная страница тренера',item.get('date_collected') or DATE,'Профиль найден; владение не подтверждено'])
            existing_sources.add((str(r),uk))
        log.append([name,url,action,r,DATE])
    summary=wb['Сводка DDX Fitness'] if 'Сводка DDX Fitness' in wb.sheetnames else wb.create_sheet('Сводка DDX Fitness')
    if summary.max_row:summary.delete_rows(1,summary.max_row)
    for k,v in [('Всего строк в CSV',stats['csv_rows']),('Новые строки',stats['new']),('Точные совпадения URL',stats['matched_url']),('На ручную проверку',stats['review']),('Отклонено',stats['invalid']),('Добавлено соцссылок',stats['social_added']),('Записей в объединенной базе',ws.max_row-1)]:summary.append([k,v])
    for table in (ws,sources,review,log):
        table.freeze_panes='A2';table.auto_filter.ref=table.dimensions
        for cell in table[1]:cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(color='FFFFFF',bold=True)
    for s in (review,log):
        s.column_dimensions['A'].width=33;s.column_dimensions['B'].width=70;s.column_dimensions['C'].width=35
    summary.column_dimensions['A'].width=44;summary.column_dimensions['B'].width=18
    wb.save(OUTPUT)
    print('ГОТОВО',stats,'Записей:',ws.max_row-1,'Файл:',OUTPUT)
    if args.apply_master:
        backup=MASTER.parent/'Backups';backup.mkdir(parents=True,exist_ok=True)
        dest=backup/f'fitness_trainers_master_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        shutil.copy2(MASTER,dest)
        shutil.copy2(OUTPUT,MASTER)
        print('Резервная копия:',dest,'Основная база обновлена:',MASTER)
if __name__=='__main__':main()
