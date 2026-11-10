# Spirit Fitness Collector V1.1 — Windows / Python 3.13

Обновление на основе исходного `collect_spiritfitness.py`, присланного пользователем. Не удаляйте `spiritfitness.sqlite3` и не копируйте SQLite из этого архива: его здесь нет.

## Исправления

- У региональных анкет сохраняется региональный префикс `/spb/coaches/` или `/ekb/coaches/`, даже если исходная ссылка на странице каталога выглядит как `/coaches/`.
- Страницы «Страница не найдена» и HTTP 404/410 не записываются в качестве тренеров.
- Для достоверной анкеты требуется корректный H1 (ФИО) и роль тренера/инструктора.
- Пробует закрыть всплывающее окно `#banner` обычной кнопкой закрытия либо `Escape`; никакого принудительного клика сквозь модальное окно.
- CSV экспортируется из SQLite даже при `Ctrl+C`.
- Поддерживается восстановление прежних ссылок с резервной копией SQLite, без удаления исторических записей.
- `--resume-queue` открывает только ожидающие URL, не загружая повторно каталоги.
- Основная Excel-база и DaData не затрагиваются.

## Установка

1. Остановите запущенный сборщик и закройте программы, которые держат SQLite.
2. Сохраните предыдущий `C:\WebCollector\SpiritFitness\collect_spiritfitness.py` под другим именем, например `collect_spiritfitness_v1_old.py`.
3. Из ZIP скопируйте `collect_spiritfitness.py` и `test_spirit_v11.py` прямо в `C:\WebCollector\SpiritFitness`. Не переносите файлы из других вложенных папок.
4. В PowerShell:

```powershell
cd C:\WebCollector\SpiritFitness
.\.venv\Scripts\python.exe test_spirit_v11.py
.\.venv\Scripts\python.exe collect_spiritfitness.py --repair-db
```

`--repair-db` делает резервную копию `Backups\spiritfitness_before_repair_*.sqlite3`, помечает страницы ошибок и устаревшие региональные URL, создаёт правильные URL для очереди и экспортирует CSV. Это локальная операция, без сетевых запросов. Исторические записи сохраняются.

Далее тест на 10 отложенных страниц СПб:

```powershell
.\.venv\Scripts\python.exe collect_spiritfitness.py --cities spb --resume-queue --max-profiles 10
```

Если всё корректно, продолжайте:

```powershell
.\.venv\Scripts\python.exe collect_spiritfitness.py --cities all --resume-queue --max-profiles 0
```

Для расширения каталога после обработки очереди:

```powershell
.\.venv\Scripts\python.exe collect_spiritfitness.py --cities all --max-profiles 0 --max-clicks 0
```

`--export-only` повторно формирует CSV из всех подтверждённых собранных анкет SQLite.

## Ограничения

- Исправление региональной части URL основано на структуре официального сайта. Некоторые индивидуальные страницы могли быть удалены; они будут отклонены, но не считаться тренерами.
- Если всплывающее окно невозможно закрыть корректно, расширение каталога остановится с записью в журнале.
- Повторные локальные тесты не заменяют полноценный сетевой тест на вашем ПК.
- Сборщик соблюдает `robots.txt`; при невозможности получить разрешённый доступ по умолчанию останавливается.
