# WebCollector — Social Enrichment V1.4

Обновление **существующего** `C:\WebCollector\SocialEnrichment` на Windows (Python 3.13).

## Изменения
- На персональных страницах RegymSport извлекаются ссылки с явными подписями **«Тренер во „ВКонтакте“»** и **«Тренер в Telegram»**.
- Проверяется совпадение ФИО с заголовком H1, исключаются ссылки меню, подвала, разделов с другими тренерами и неподходящие адреса соцсетей.
- Перед добавлением кандидата проверяются соответствующее поле в общей базе и ранее собранные кандидаты; прежние ссылки не перезаписываются. Новые кандидаты имеют статус `review`.
- `--rescan-regymsport` позволяет повторно обойти RegymSport после изменения правил извлечения, даже если эти страницы отмечены обработанными ранее.
- Проверки `robots.txt`, ограничение переходов между доменами, безопасный режим без изменения Excel сохранены.

## Установка
1. Закройте работающий Social Enrichment.
2. Сохраните резервную копию файлов `social_enrichment.py`, `social_candidates.csv`, `social_errors.csv`, `social_progress.json`.
3. Распакуйте ZIP **в папку** `C:\WebCollector\SocialEnrichment`, заменив только `social_enrichment.py` и `requirements.txt`. Добавьте `test_v14.py`.
4. Окружение `.venv` и каталог `C:\WebCollector\Data` не меняйте.

В PowerShell:

```powershell
cd C:\WebCollector\SocialEnrichment
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe test_v14.py
```

## Тест на 20 персональных страниц RegymSport

```powershell
.\.venv\Scripts\python.exe social_enrichment.py --only-regymsport --rescan-regymsport --max-profiles 20
```

**Важно:** `--rescan-regymsport` намеренно обходит уже посещённые страницы. Повторный запуск не должен добавлять одинаковые кандидатуры благодаря дедупликации.

## Полный проход RegymSport

После проверки первых 20 страниц:

```powershell
.\.venv\Scripts\python.exe social_enrichment.py --only-regymsport --rescan-regymsport --max-profiles 150
```

Это перечитает до 150 персональных страниц RegymSport, включая первые 20. Проверьте `social_candidates.csv` и присылайте итог консоли.

## Безопасность данных

- Исходный файл `C:\WebCollector\Data\fitness_trainers_master.xlsx` не меняется при сборе.
- Старые 521 кандидатов остаются в `social_candidates.csv`; ошибочные 517 записей из прошлой версии не становятся автоматически подтверждёнными.
- После успешного прохода используйте аудит: `social_enrichment.py --audit-candidates` — он формирует отдельный CSV.
- Для применения в Excel **не используйте** `--apply` до ручной проверки кандидатур, а особенно старых 517 записей.
- `source_name_match` означает совпадение имени в источнике, **не** подтверждение владения аккаунтом.

## Технические ограничения

- Переадресация за пределы исходного домена не выполняется автоматически.
- Если сайт требует JavaScript для появления ссылок, текущий режим `requests + BeautifulSoup` их не увидит.
- Прямое сравнение с Excel выполняется по текстовому URL без сложной канонизации вариаций вида `m.vk.ru`/`vk.com`, такие случаи могут потребовать ручной дедупликации.
- Локальные тесты без сети не гарантируют, что реальный сайт сохранит свою структуру.
