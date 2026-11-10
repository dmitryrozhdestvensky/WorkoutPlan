"""Non-destructive merge: backup master; URL-based identity, name+city review."""
import argparse,csv,re,shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from openpyxl import load_workbook
from openpyxl.styles import Font,PatternFill

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
MASTER=ROOT/'Data'/'fitness_trainers_master.xlsx'
INFILE=HERE/'worldclass_trainers.csv'
OUT=HERE/'fitness_trainers_merged_worldclass.xlsx'
DATE=datetime.now().strftime('%Y-%m-%d')

def keyname(x):return re.sub(r'\s+',' ',str(x or '').strip()).casefold()
def keyurl(x):
    x=str(x or '').strip()
    if not x:return ''
    p=urlsplit(x);return p.netloc.casefold().removeprefix('www.')+p.path.rstrip('/').casefold() if p.netloc else ''

def run():
    ap=argparse.ArgumentParser();ap.add_argument('--apply-master',action='store_true',help='Replace master after creating dated backup');args=ap.parse_args()
    if not MASTER.exists():raise SystemExit('Не найдена база '+str(MASTER))
    if not INFILE.exists():raise SystemExit('Не найден CSV '+str(INFILE))
    wb=load_workbook(MASTER);ws=wb['Тренеры']
    header={str(c.value).strip():c.column for c in ws[1] if c.value}
    def col(name):
        if name not in header:header[name]=ws.max_column+1;ws.cell(1,header[name],name)
        return header[name]
    required=['Тренер / имя','Город','Специализация','VK','OK','Дзен','Telegram','Instagram','TikTok','TenChat','URL источника','Источник — название','Страница тренера в источнике','Дата сбора','Статус проверки','Клубы WorldClass','Образование WorldClass','Достижения WorldClass','Компетенции WorldClass']
    for name in required:col(name)
    url_rows={};possible=defaultdict(list)
    for r in range(2,ws.max_row+1):
        for label in ('URL источника','Страница тренера в источнике'):
            u=keyurl(ws.cell(r,col(label)).value)
            if u:url_rows[u]=r
        name=keyname(ws.cell(r,col('Тренер / имя')).value)
        if name:possible[name].append(r)
    sheet=wb['Источники профилей'] if 'Источники профилей' in wb else wb.create_sheet('Источники профилей')
    if sheet.max_row==1 and not sheet.cell(1,1).value:sheet.append(['ID строки тренера','Тренер','Площадка / источник','Точный URL','Тип ссылки','Дата обнаружения','Статус подтверждения'])
    sourcekeys={keyurl(sheet.cell(r,4).value) for r in range(2,sheet.max_row+1)}
    log=wb.create_sheet('Импорт WorldClass '+datetime.now().strftime('%m%d_%H%M'))
    log.append(['Имя','WorldClass URL','Статус','Строка базы','Примечание'])
    review=wb.create_sheet('Совпадения WorldClass '+datetime.now().strftime('%m%d_%H%M'))
    review.append(['ФИО','WorldClass URL','Строки с таким ФИО','Причина'])
    stats={'new':0,'matched_exact_url':0,'needs_review':0,'invalid':0,'social_links_added':0,'csv_rows':0}
    seen_csv=set()
    with INFILE.open(encoding='utf-8-sig',newline='') as f:
        for item in csv.DictReader(f,delimiter=';'):
            name=(item.get('name') or '').strip();url=(item.get('source_profile_url') or '').strip()
            uk=keyurl(url)
            if not name or not uk.startswith('worldclass.ru/trainers/') or uk=='worldclass.ru/trainers':stats['invalid']+=1;continue
            if uk in seen_csv:continue
            seen_csv.add(uk);stats['csv_rows']+=1
            if uk in url_rows:
                r=url_rows[uk];stats['matched_exact_url']+=1;action='совпадение URL'
            elif keyname(name) in possible:
                stats['needs_review']+=1
                review.append([name,url,', '.join(map(str,possible[keyname(name)])),'Имя совпало — проверьте город и клуб, не объединено автоматически'])
                log.append([name,url,'ручная проверка','','Возможное совпадение по ФИО']);continue
            else:
                r=ws.max_row+1;stats['new']+=1;action='новый профиль'
                mapping={'Тренер / имя':name,'Город':item.get('city') or 'Не уточнён','Специализация':item.get('specialty'),'URL источника':url,'Страница тренера в источнике':url,'Источник — название':'WorldClass','Дата сбора':item.get('date_collected') or DATE,'Статус проверки':'Публичная анкета World Class; связь соцсетей не подтверждена','Клубы WorldClass':item.get('clubs'),'Образование WorldClass':item.get('education'),'Достижения WorldClass':item.get('achievements'),'Компетенции WorldClass':item.get('skills')}
                for k,v in mapping.items():ws.cell(r,col(k),v)
                url_rows[uk]=r;possible[keyname(name)].append(r)
            for csvlabel,xlslabel in [('vk','VK'),('ok','OK'),('dzen','Дзен'),('telegram','Telegram'),('instagram','Instagram'),('tiktok','TikTok'),('tenchat','TenChat')]:
                if item.get(csvlabel) and not ws.cell(r,col(xlslabel)).value:
                    ws.cell(r,col(xlslabel),item[csvlabel]);stats['social_links_added']+=1
            for k,x in [('clubs','Клубы WorldClass'),('education','Образование WorldClass'),('achievements','Достижения WorldClass'),('skills','Компетенции WorldClass')]:
                if item.get(k) and not ws.cell(r,col(x)).value:ws.cell(r,col(x),item[k])
            if uk not in sourcekeys:
                sheet.append([r,name,'WorldClass',url,'Персональная страница фитнес-клуба',item.get('date_collected') or DATE,'Обнаружено в публичном каталоге'])
                sourcekeys.add(uk)
            log.append([name,url,action,r,''])
    summ=wb.create_sheet('Итог WorldClass '+datetime.now().strftime('%m%d_%H%M'))
    for k,v in [*stats.items(),('total_trainers',ws.max_row-1)]:summ.append([k,v])
    for sh in (log,review):
        sh.freeze_panes='A2';sh.auto_filter.ref=sh.dimensions
        for cell in sh[1]:cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(color='FFFFFF',bold=True)
        sh.column_dimensions['A'].width=37;sh.column_dimensions['B'].width=78;sh.column_dimensions['C'].width=34;sh.column_dimensions['D'].width=22
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    OUT.parent.mkdir(exist_ok=True,parents=True);wb.save(OUT)
    if args.apply_master:
        back=ROOT/'Data'/'Backups';back.mkdir(parents=True,exist_ok=True)
        backup=back/('fitness_trainers_master_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.xlsx')
        shutil.copy2(MASTER,backup);shutil.copy2(OUT,MASTER)
        print('Резервная копия:',backup)
    print('ГОТОВО:',stats,'Итого:',ws.max_row-1,'Файл:',OUT)

if __name__=='__main__':run()
