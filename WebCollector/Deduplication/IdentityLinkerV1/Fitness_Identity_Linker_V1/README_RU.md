# Fitness Identity Linker V1 — формирование единых карточек тренеров

Назначение: создать **3 897 предварительных карточек** на базе 5 652 исходных анкет с учётом **1 755 подтверждённых пар по URL**. Остальные анкеты получают отдельные предварительные карточки. Совпадения только по ФИО НЕ объединяются.

## Безопасность
- По умолчанию — **только чтение**.
- Режим `--apply` требует явного подтверждения и выполняет все изменения одной транзакцией; при ошибке откат.
- Перед записью повторно проверяются исходные URL и ФИО непосредственно в PostgreSQL, число исходных анкет и непересекаемость групп.
- Исходные `fitness.source_profiles`, `fitness.sources` и вся схема `public` не меняются.
- В `fitness.trainers` создаются предварительные карточки (`provisional`); в `fitness.trainer_profile_links` — ссылки на исходные анкеты.
- Скрипт не объединяет уже существующие карточки и останавливается при несовместимых связях.
- Повторный запуск не создаёт дубликатов (если БД не изменена другим процессом).
- Журнал-результат JSON создаётся локально. Сначала обязательно делайте резервную копию PostgreSQL.

## Установка в Windows PowerShell

Распаковать ZIP так, чтобы файл лежал по пути `C:\WebCollector\Deduplication\IdentityLinkerV1\link_identities.py`.

```powershell
cd C:\WebCollector\Deduplication\IdentityLinkerV1
py -3.13 -m pip install -r .\requirements.txt
```

## 1. Резервная копия до записи

```powershell
New-Item -ItemType Directory -Path 'C:\WebCollector\Backups' -Force | Out-Null
$pg = 'E:\GoogleDrive\Проекты\ФитнесТренер\data\postgres17\pgsql\bin'
& "$pg\pg_dump.exe" -h 127.0.0.1 -p 15432 -U workoutplan_test -Fc -f 'C:\WebCollector\Backups\workoutplan_before_identity_linking.backup' workoutplan
if ($LASTEXITCODE -ne 0) { throw 'Резервное копирование не удалось — остановитесь' }
Get-Item 'C:\WebCollector\Backups\workoutplan_before_identity_linking.backup' | Select-Object Name,Length,LastWriteTime
```

## 2. Обязательная проверка без записи

```powershell
py -3.13 .\link_identities.py `
  --exact 'C:\WebCollector\Deduplication\Reports\LineageAudit\lineage_exact_urls.csv' `
  --output 'C:\WebCollector\Deduplication\Reports\IdentityLinker'
```

Должно получиться: `input_pairs=1755`, `expected_groups_after_linking=3897`. Если существующих карточек ещё нет, `new_trainers_to_create=3897`, `new_links_to_create=5652`.

## 3. Запись после проверки результата и резервной копии

```powershell
py -3.13 .\link_identities.py `
  --exact 'C:\WebCollector\Deduplication\Reports\LineageAudit\lineage_exact_urls.csv' `
  --output 'C:\WebCollector\Deduplication\Reports\IdentityLinker' `
  --apply --confirm LINK_1755_EXACT_URL_PAIRS
```

После выполнения ожидается `trainers_after=3897`, `links_after=5652`, `distinct_profiles_linked_after=5652`. Результат сохраняется в `identity_apply_result.json`.

## 4. SQL-контроль

```powershell
& "$pg\psql.exe" -h 127.0.0.1 -p 15432 -U workoutplan_test -d workoutplan -c 'SELECT COUNT(*) AS trainers FROM fitness.trainers;'
& "$pg\psql.exe" -h 127.0.0.1 -p 15432 -U workoutplan_test -d workoutplan -c 'SELECT COUNT(*) AS linked_profiles,COUNT(DISTINCT source_profile_id) AS unique_profiles FROM fitness.trainer_profile_links;'
& "$pg\psql.exe" -h 127.0.0.1 -p 15432 -U workoutplan_test -d workoutplan -c 'SELECT COUNT(*) AS original_profiles FROM fitness.source_profiles;'
```

Число 3897 — **предварительные группы анкет**, а не доказанное число уникальных людей.

## При ошибке
Не повторяйте `--apply` вслепую. Отправьте текст ошибки, итоговый JSON и число существующих карточек/связей. Не удаляйте таблицы и не восстанавливайте резервную копию поверх работающей БД без отдельной проверки.
