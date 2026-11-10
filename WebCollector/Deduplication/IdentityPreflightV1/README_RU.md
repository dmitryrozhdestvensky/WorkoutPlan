# Fitness Identity Preflight V1

Предварительная проверка связывания профилей по исходным URL, без изменений PostgreSQL.

## Установка

Распакуйте архив в `C:\WebCollector\Deduplication\IdentityPreflightV1`.

```powershell
cd C:\WebCollector\Deduplication\IdentityPreflightV1
py -3.13 -m pip install -r .\requirements.txt
```

## Запуск

```powershell
py -3.13 .\preflight_identity.py `
  --exact "C:\WebCollector\Deduplication\Reports\LineageAudit\lineage_exact_urls.csv" `
  --ambiguous "C:\WebCollector\Deduplication\Reports\LineageAudit\lineage_ambiguous_names.csv" `
  --output "C:\WebCollector\Deduplication\Reports\IdentityPreflight"
```

Подключение: `workoutplan` на `127.0.0.1:15432`, пользователь `workoutplan_test`. Пароль стандартно берётся из pgpass.conf. Исходные таблицы и таблицы приложения не изменяются.

## Результат

- `identity_preflight_summary.json` — сколько пар безопасно планировать, сколько требуют проверки.
- `identity_link_plan.csv` — все пары с URL, сверкой ФИО, уникальностью, существующими связями, причинами отклонения.
- `fitness_schema_inspection.json` — реальные столбцы существующих таблиц для следующего, отдельно согласованного этапа записи.

`candidate_ready` — кандидат для последующего подтверждённого связывания, а НЕ выполненная операция. Скрипт не имеет режима записи. Даже при 1755 готовых парах понадобится отдельная контролируемая транзакция с предварительным резервным копированием.
