# Fitness Data Cleaning V1 — PostgreSQL + DaData (Windows)

Работает исключительно в режиме чтения PostgreSQL. При необходимости посылает **только ФИО** на DaData Cleaner API. Не меняет карточки, исходные анкеты и связи. Ответы DaData сохраняет в локальный SQLite и повторно не оплачивает уже обработанные уникальные строки. **Совпадение нормализованных ФИО не устанавливает личность.**

## Установка

Распакуйте содержимое архива в `C:\WebCollector\DataQuality\Fitness_Data_Cleaning_V1`.

```powershell
cd C:\WebCollector\DataQuality\Fitness_Data_Cleaning_V1
py -3.13 -m pip install -r .\requirements.txt
```

Используется ранее созданный `C:\WebCollector\Config\.env` с `DADATA_API_KEY` и `DADATA_SECRET_KEY`. Ключи не требуется присылать в чат. Пароль PostgreSQL читается psycopg из стандартного pgpass.

## 1. Аудит без обращения к DaData и расходов

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_cleaning.ps1 audit
```

Итоги в `C:\WebCollector\DataQuality\PostgreSQL\cleaning_summary.json`, `trainer_quality_audit.csv`, `trainer_issues_review.csv`, `name_duplicate_candidates.csv`.

## 2. Пробный запрос к DaData (потенциально платный)

После проверки доступного баланса/тарифа:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_cleaning.ps1 probe -Limit 1 -ConfirmRequests -MaxSpendRub 0.20
```

## 3. Пробная обработка 20 новых уникальных ФИО

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_cleaning.ps1 run -Limit 20 -ConfirmRequests -MaxSpendRub 4
```

Каждый вызов сохраняется в локальный кэш. Скрипт оценивает верхнюю стоимость из предположения **0,20 ₽/запись**; фактический тариф и баланс проверьте в DaData. Вызовы `audit`/`report` никогда не обращаются к DaData.

## 4. Пересобрать отчёты, не запрашивая API

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_cleaning.ps1 report
```

**Важно:** система ожидает 3897 карточек и 5652 исходные анкеты, в иных условиях останавливается. Для расширенной дедупликации нужны клубы, URL, города и социальные ссылки. Этот этап формирует **кандидатов по ФИО**, без подтверждения личности и без DB UPDATE/INSERT/DELETE. Не отправляйте `.env` и SQLite с ответами в чат без удаления секретов и персональных данных, если это не требуется.
