# WorldClass Collector V1

Распакуйте **содержимое** архива в `C:\WebCollector\WorldClass`. Основная база должна находиться в `C:\WebCollector\Data\fitness_trainers_master.xlsx`. В архив не включена база, чтобы не перезаписать ваши 495 записей.

## Установка (PowerShell)

```powershell
cd C:\WebCollector\WorldClass
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Сначала тест (10 профилей)

```powershell
.\.venv\Scripts\python.exe collect_worldclass.py --max-profiles 10 --max-list-pages 3 --show-browser
```

Проверьте `worldclass_trainers.csv`: должны быть реальные ФИО, правильные персональные ссылки `www.worldclass.ru/trainers/<slug>/`. Если результат корректен, запускайте полный проход:

```powershell
.\.venv\Scripts\python.exe collect_worldclass.py --max-profiles 1500 --max-list-pages 120
```

Прогресс хранится в `worldclass_progress.sqlite3`; повторный запуск пропускает уже сохранённые профили. Если сайт ограничивает частоту запросов, сборщик **не** обходит CAPTCHA и защиту. Уменьшите нагрузку `--delay 3` или остановите обход.

## Объединение с 495 тренерами

```powershell
.\.venv\Scripts\python.exe merge_worldclass.py
```

Создаст `fitness_trainers_merged_worldclass.xlsx` в папке WorldClass, **не изменяя** главный файл. Проверив результат, примените:

```powershell
.\.venv\Scripts\python.exe merge_worldclass.py --apply-master
```

Это создаст резервную копию в `C:\WebCollector\Data\Backups` и обновит единый Excel.

## Что сохраняется

- ФИО, профессиональная специализация, клубы, образование, достижения и компетенции (если опубликованы).
- Точный URL профиля World Class, название источника и дата сбора.
- Только явно обнаруженные ссылки на соцсети, без догадок по ФИО.
- Возможные совпадения по ФИО — в лист ручной проверки; автоматически объединяются только точные URL.

## Ограничения

Сайт имеет разные версии интерфейса и может изменяться. Скрипт пробует ссылочную пагинацию и кнопку «Показать ещё»; полный доступ к 1439 анкетам не гарантируется. World Class показывает также филиалы за пределами РФ; город в V1 отмечен как предполагаемый, его следует подтвердить перед окончательным включением в базу России. Страница может показывать общие ссылки клуба: при сомнениях не считайте их личной соцсетью тренера. Публичное размещение данных и рассылки требуют соблюдения применимого законодательства о персональных данных и рекламе.
