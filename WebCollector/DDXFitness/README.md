# DDXFitness Collector V1

Рабочая папка Windows: `C:\WebCollector\DDXFitness`.

**Требования:** Python 3.13, Chromium для Playwright, доступ к публичному сайту DDX Fitness.

## Установка

В PowerShell:

```powershell
cd C:\WebCollector\DDXFitness
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Тест на 10 анкет

```powershell
.\.venv\Scripts\python.exe collect_ddxfitness.py --max-profiles 10 --max-clicks 3 --show-browser
```

Сохранённые результаты: `ddxfitness_trainers.csv`, `ddxfitness_progress.sqlite3`, `ddxfitness_discovered_urls.txt` и `ddxfitness_errors.csv`.

- Важно: `--max-profiles 10` ограничивает **новые** анкеты, а не общий CSV с ранее собранными.
- После каждого посещённого профиля запись сохраняется в SQLite и CSV. Повторный запуск продолжит сбор.
- `--max-clicks` ограничивает раскрытие каталога; `--max-profiles 0` означает обработать все обнаруженные URL.
- Город не заполняется догадкой по названию клуба. Тренеры групповых тоже включены.
- Поле `education` пока оставляется пустым: страница может смешивать достижения и образование.
- Личные социальные сети извлекаются только с персональной анкеты, без ссылок из футера.
- Если сайт перестанет добавлять записи, создаётся `ddxfitness_debug.png`.

## Полный сбор

```powershell
.\.venv\Scripts\python.exe collect_ddxfitness.py --max-profiles 0 --max-clicks 150 --show-browser
```

## Объединение с базой

Основная база читается **только** из `C:\WebCollector\Data\fitness_trainers_master.xlsx`.

```powershell
.\.venv\Scripts\python.exe merge_ddxfitness.py
```

Будет создан `fitness_trainers_merged_ddxfitness.xlsx` внутри папки DDXFitness. Основная база остаётся неизменной. Просмотрите листы «Импорт DDX Fitness», «Проверить совпадения» и «Источники профилей».

После проверки, если хотите **создать резервную копию и применить** результат к общей базе:

```powershell
.\.venv\Scripts\python.exe merge_ddxfitness.py --apply-master
```

При совпадении ФИО без совпадения URL программа НЕ объединяет людей автоматически — переносит случай в «Проверить совпадения».

## Ограничения

Сайт может менять HTML или ограничивать динамическую подгрузку. Скрипт пока не проверен на полном каталоге DDX. Не отключайте SSL-проверку; при блокировке используйте обычную сетевую диагностику. Собирайте только публичные профессиональные данные, соблюдайте условия площадки и не используйте сведения для нежелательных рассылок.
