# Fitness DaData Cache Migrator V1

Назначение: перенести **только совпадающие с текущими карточками** ранее обработанные ФИО из `dadata_quality_progress.sqlite3` (таблица `names`, 100 строк) в `dadata_pg_cache.sqlite3` (таблица `clean_names`, сейчас 21 строка). **Никаких запросов в DaData, никакой записи в PostgreSQL.** Исходный кэш не изменяется. Существующие строки нового кэша никогда не переписываются.

## Установка

Распакуйте `migrate_dadata_cache.py` в `C:\WebCollector\DataQuality\CacheMigratorV1`. В качестве исходного списка ФИО используется уже сформированный модулем очистки `C:\WebCollector\DataQuality\PostgreSQL\trainer_quality_audit.csv`. Используется только стандартная библиотека Python.

## 1. Предварительная проверка

```powershell
cd C:\WebCollector\DataQuality\CacheMigratorV1
py -3.13 .\migrate_dadata_cache.py
```

Результат: `C:\WebCollector\DataQuality\PostgreSQL\cache_migration_summary.json`. Смотрите `to_import` и `not_in_current_catalog`. Не следует ожидать 100 новых строк: старые анкеты могут отсутствовать в новом каталоге или уже находиться в кэше.

## 2. Перенос с резервным копированием

```powershell
py -3.13 .\migrate_dadata_cache.py --apply
```

Перед переносом создаётся SQLite-копия `dadata_pg_cache_before_legacy_merge_YYYYMMDD_HHMMSS.sqlite3`. Проверяется схема обоих кэшей. Перенос выполняется одной транзакцией. `result_json` восстанавливается из сохранённых полей `normalized_name`, `surname`, `name`, `patronymic`, `qc`; добавляются признаки происхождения `_cache_origin` и `_legacy_import_note`. Он не представляется полным оригинальным API-ответом.

## 3. Повторный отчёт

```powershell
cd C:\WebCollector\DataQuality\Fitness_Data_Cleaning_V1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_cleaning.ps1 report
```

Значение `cached_names_in_scope` должно увеличиться на `to_import`. Затем можно продолжать платные запросы DaData для ещё не проверенных ФИО.
