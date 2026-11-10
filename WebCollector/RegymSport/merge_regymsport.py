"""Merge public RegymSport profiles into the trainer workbook using openpyxl.
Existing data is preserved; ambiguous same-name matches go to a review sheet.
"""
import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

HERE=Path(__file__).resolve().parent
BASE=HERE/'fitness_trainers_base.xlsx'
CSV=HERE/'regymsport_trainers.csv'
OUTPUT=HERE/'fitness_trainers_merged_regymsport.xlsx'
DATE=datetime.now().date().isoformat()

def clean(v): return re.sub(r'\s+',' ',str(v or '').strip()).casefold()
def urlkey(v):
    u=urlsplit(str(v or '').strip())
    return (u.netloc.lower().removeprefix('www.') + u.path.rstrip('/').lower()) if u.netloc else ''

def read_rows():
    with CSV.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))

def run():
    if not BASE.exists() or not CSV.exists():
        raise SystemExit('Не найдены fitness_trainers_base.xlsx или regymsport_trainers.csv')
    wb=load_workbook(BASE)
    ws=wb['Тренеры']
    hdr={str(c.value).strip():c.column for c in ws[1] if c.value}
    def col(name):
        if name not in hdr:
            idx=ws.max_column+1; ws.cell(1,idx,name);hdr[name]=idx
        return hdr[name]
    names=['Тренер / имя','Город','Специализация','VK','OK','Дзен','Telegram','Instagram','TikTok','TenChat','Сайт / мультиссылка','URL источника','Статус проверки','Примечание','Дата сбора','Источник — название','Страница тренера в источнике','Дополнительные источники — URL','Клубы RegymSport','Компетенции RegymSport','Образование RegymSport']
    for x in names:col(x)
    urls={}; names_city={}
    def register(r):
        for x in ('Страница тренера в источнике','URL источника','Сайт / мультиссылка'):
            k=urlkey(ws.cell(r,col(x)).value)
            if k and k.startswith('regymsport.ru/trenery/'):urls[k]=r
        key=(clean(ws.cell(r,col('Тренер / имя')).value),clean(ws.cell(r,col('Город')).value))
        if key[0]:names_city.setdefault(key,[]).append(r)
    for r in range(2,ws.max_row+1):register(r)
    social={'vk':'VK','ok':'OK','dzen':'Дзен','telegram':'Telegram','instagram':'Instagram','tiktok':'TikTok','tenchat':'TenChat'}
    if 'Источники профилей' in wb:
        sources=wb['Источники профилей']
    else:
        sources=wb.create_sheet('Источники профилей');sources.append(['ID строки тренера','Тренер','Площадка / источник','Точный URL','Тип ссылки','Дата обнаружения','Статус подтверждения'])
    existing_sources={(str(sources.cell(i,1).value),urlkey(sources.cell(i,4).value)) for i in range(2,sources.max_row+1)}
    review=wb['Проверить совпадения'] if 'Проверить совпадения' in wb else wb.create_sheet('Проверить совпадения')
    if review.max_row==1 and review.cell(1,1).value is None:
        review.append(['ФИО','Город','URL RegymSport','Возможные строки в базе','Причина'])
    log=wb['Импорт RegymSport'] if 'Импорт RegymSport' in wb else wb.create_sheet('Импорт RegymSport')
    if log.max_row==1 and log.cell(1,1).value is None:
        log.append(['ФИО','URL','Действие','Строка в базе','Дата'])
    result={'new':0,'matched_url':0,'review':0,'invalid':0,'social_added':0,'rows':0}
    for item in read_rows():
        name=item.get('name','').strip(); source=item.get('source_profile_url','').strip()
        if not name or not urlkey(source).startswith('regymsport.ru/trenery/'):
            result['invalid']+=1;continue
        result['rows']+=1
        uk=urlkey(source); matches=names_city.get((clean(name),'нижний новгород'),[])
        if uk in urls:
            r=urls[uk]; action='existing source URL';result['matched_url']+=1
        elif matches:
            review.append([name,'Нижний Новгород',source,', '.join(map(str,matches)),'Совпадение ФИО и города: требуется ручная проверка, не объединять автоматически'])
            log.append([name,source,'needs review','',DATE]);result['review']+=1;continue
        else:
            r=ws.max_row+1
            data={'Тренер / имя':name,'Город':'Нижний Новгород','Специализация':item.get('specialty'),'URL источника':source,'Дата сбора':item.get('date_collected') or DATE,'Источник — название':'RegymSport','Страница тренера в источнике':source,'Статус проверки':'Найдено на сайте клуба; принадлежность соцсетей отдельно не проверена','Клубы RegymSport':item.get('clubs'),'Компетенции RegymSport':item.get('skills'),'Образование RegymSport':item.get('education')}
            for label,value in data.items():ws.cell(r,col(label),value)
            result['new']+=1;action='new';register(r)
        for k,field in social.items():
            val=item.get(k,'').strip()
            if val and not ws.cell(r,col(field)).value:
                ws.cell(r,col(field),val);result['social_added']+=1
        for k,label in [('clubs','Клубы RegymSport'),('skills','Компетенции RegymSport'),('education','Образование RegymSport')]:
            if item.get(k) and not ws.cell(r,col(label)).value:ws.cell(r,col(label),item[k])
        if not ws.cell(r,col('Страница тренера в источнике')).value:
            ws.cell(r,col('Страница тренера в источнике'),source)
        if not ws.cell(r,col('Источник — название')).value:
            ws.cell(r,col('Источник — название'),'RegymSport')
        if (str(r),uk) not in existing_sources:
            sources.append([r,name,'RegymSport',source,'Персональная страница тренера',item.get('date_collected') or DATE,'Найдено на сайте клуба, владение не подтверждено'])
            existing_sources.add((str(r),uk))
        log.append([name,source,action,r,DATE])
    for sheet in (log,review):
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for c in sheet[1]:c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True)
        sheet.column_dimensions['A'].width=34;sheet.column_dimensions['B'].width=65;sheet.column_dimensions['C'].width=32;sheet.column_dimensions['D'].width=22;sheet.column_dimensions['E'].width=24
    for c in ws[1]:c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True)
    ws.auto_filter.ref=ws.dimensions;ws.freeze_panes='A2'
    summary=wb['Сводка RegymSport'] if 'Сводка RegymSport' in wb else wb.create_sheet('Сводка RegymSport')
    summary.delete_rows(1,summary.max_row)
    for label,n in [('Обработано анкет',result['rows']),('Новых тренеров',result['new']),('Найдено по точному URL',result['matched_url']),('Передано на ручную проверку',result['review']),('Ошибочные URL',result['invalid']),('Новых ссылок на соцсети',result['social_added']),('Тренеров в базе, итог',ws.max_row-1)]:
        summary.append([label,n])
    summary.column_dimensions['A'].width=42;summary.column_dimensions['B'].width=20
    # Do not rewrite legacy 'Сводка' which could contain historical metrics; add fresh summary.
    wb.save(OUTPUT)
    print('ГОТОВО:',result,'Итого тренеров:',ws.max_row-1,'Файл:',OUTPUT)

if __name__=='__main__':run()
