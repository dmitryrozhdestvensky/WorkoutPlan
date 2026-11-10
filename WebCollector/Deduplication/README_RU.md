# ФитнесТренер — дедупликация V1

**Назначение:** выявлять *кандидатов* на совпадение между источниками `legacy_master`, `ddxfitness`, `worldclass`, `spiritfitness`, `regymsport`. Совпадение имени **не** приводит к автоматическому объединению. Исходные анкеты, `public.*`, `fitness.trainers`, `trainer_profile_links`, `trainer_user_links` не изменяются.

## Установка

Распакуйте ZIP в `C:\WebCollector\Deduplication` и выполните в PowerShell:

```powershell
cd C:\WebCollector\Deduplication
py -3.13 -m pip install -r .\requirements.txt
py -3.13 .\dedup_trainers.py --output "C:\WebCollector\Deduplication\Reports"
```

Используется штатная аутентификация PostgreSQL/libpq (`%APPDATA%\postgresql\pgpass.conf`). Пароль вводить в командной строке не нужно. База по умолчанию `workoutplan`, порт 15432, пользователь `workoutplan_test`.

Результат: `Reports\fitness_merge_candidates_review.csv` и `Reports\fitness_dedup_summary.json`.

## Логика кандидатов

- Для сопоставления нормализуются регистр, пробелы, `е/ё`, знаки препинания.
- Перестановка слов ФИО выявляется как кандидат, но не как подтверждённое совпадение.
- Точная одинаковая социальная ссылка — сильный признак, но сам по себе не подтверждает владение профилем.
- Одинаковые ФИО: базовый балл 48, **низкий приоритет**; тот же клуб +18, тот же город +6.
- Профили с одним словом в имени не связываются по имени без дополнительной социальной ссылки.
- Балл — только *приоритет ручной проверки*, не статистическая вероятность.
- Анализируются пары **между разными источниками**. Дубли внутри одного источника — отдельный будущий этап.

## Запись в `fitness.merge_candidates`

По умолчанию модуль **только читает** PostgreSQL. После проверки CSV можно включить необязательную запись:

```powershell
py -3.13 .\dedup_trainers.py --output "C:\WebCollector\Deduplication\Reports" --write-candidates
```

Программа сначала анализирует фактические столбцы `fitness.merge_candidates` и прекращает запись, если схема неизвестна или небезопасна. Она не удаляет и не обновляет имеющиеся решения ручной проверки. Если схема не подходит, пришлите текст ошибки: адаптируем запись к реальной структуре. Запускать запись **только после проверки отчёта**.

## Проверка

SQL для оценки заполнения основных таблиц:

```sql
SELECT s.code, count(*) AS profiles
FROM fitness.source_profiles p JOIN fitness.sources s ON s.id=p.source_id
GROUP BY s.code ORDER BY profiles DESC;
SELECT count(*) AS socials FROM fitness.profile_socials;
```

Не рассчитывайте `5652 - число кандидатов` как число уникальных тренеров: найденные совпадения требуют проверки и могут перекрываться.
