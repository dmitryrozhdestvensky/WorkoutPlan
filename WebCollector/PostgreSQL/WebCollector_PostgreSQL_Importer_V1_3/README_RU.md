# WebCollector PostgreSQL Importer V1.3 — World Class

Добавлена опция `--kind worldclass_csv`. Импорт в **существующую** БД `workoutplan`, схему `fitness`; `public.*` не изменяется.

Источник: `C:\WebCollector\WorldClass\worldclass_trainers.csv` после успешного V1.7.1. Полный JSON из таблицы SQLite `api_records` можно сохранить в PostgreSQL `raw_data.api_record`, передав `--raw-sqlite`.

Не копируйте файл CSV в архив. Пароли не нужны в командной строке: используется стандартный pgpass.conf.

## Установка

Распакуйте в `C:\WebCollector\PostgreSQL\WebCollector_PostgreSQL_Importer_V1_3`.

```powershell
cd C:\WebCollector\PostgreSQL\WebCollector_PostgreSQL_Importer_V1_3
py -3.13 -m pip install -r .\requirements.txt
```

## 1. Предпроверка без обращения к PostgreSQL

```powershell
py -3.13 .\import_trainers.py --kind worldclass_csv --file "C:\WebCollector\WorldClass\worldclass_trainers.csv" --raw-sqlite "C:\WebCollector\WorldClass\worldclass_progress.sqlite3" --expected-rows 1580 --dry-run
```

Должно показать `rows: 1580`. Если ошибка `API JSON not found`, пришлите текст ошибки и не запускайте импорт: качество исходной SQLite нужно проверить. CSV и SQLite не изменяются.

## 2. Пробный импорт (ТОЛЬКО после резервной копии PostgreSQL)

```powershell
py -3.13 .\import_trainers.py --kind worldclass_csv --file "C:\WebCollector\WorldClass\worldclass_trainers.csv" --raw-sqlite "C:\WebCollector\WorldClass\worldclass_progress.sqlite3" --limit 5
```

## 3. Полный импорт

```powershell
py -3.13 .\import_trainers.py --kind worldclass_csv --file "C:\WebCollector\WorldClass\worldclass_trainers.csv" --raw-sqlite "C:\WebCollector\WorldClass\worldclass_progress.sqlite3" --expected-rows 1580
```

Импорт идемпотентен по источнику+URL. При повторном запуске старые записи обновляются, не дублируются. Все поля CSV доступны в `fitness.source_profiles.raw_data.fields`; оригинальные API JSON доступны в `raw_data.api_record`. В соответствующих столбцах `raw_name`, `normalized_name`, `clubs`, `specialty`, `city` — структурированные значения. Соцсети: `fitness.profile_socials`, статус `unverified`. Данные не связываются автоматически с пользователями приложения.

## Проверка после импорта

```sql
SELECT s.code, count(*) AS profiles
FROM fitness.source_profiles p JOIN fitness.sources s ON s.id=p.source_id
GROUP BY s.code ORDER BY s.code;
SELECT count(*) FROM fitness.source_profiles;
SELECT count(*) FROM fitness.profile_socials;
```

Ожидается `worldclass = 1580`, общий объём профилей 5652, если остальные источники не менялись. Эти записи — не обязательно уникальные люди.
