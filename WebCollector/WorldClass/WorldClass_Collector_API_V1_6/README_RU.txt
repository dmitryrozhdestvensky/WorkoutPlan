WorldClass Collector V1.6 — исправление HTTP 403 и резервный сбор

Проблема V1.5: ctx.request.get() — отдельный HTTP-клиент Playwright, который может
получать HTTP 403 даже после открытия браузером https://www.worldclass.ru/trainers/.

Исправление: запрос /api/trainers выполняется через fetch() внутри страницы сайта,
с браузерной сессией и same-origin cookies. Если сервер отвечает HTTP 403,
скрипт прекращает повторы и переходит к проверенному механизму V1.4:
нажимает ТОЛЬКО кнопку «Показать ещё», сохраняет URL по мере обнаружения.

УСТАНОВКА (PowerShell):
1) cd C:\WebCollector\WorldClass
2) Copy-Item .\collect_worldclass.py .\Backups\collect_worldclass_before_v16.py
   (если папки Backups нет, сначала создать)
3) Из ZIP скопировать collect_worldclass.py непосредственно в
   C:\WebCollector\WorldClass\collect_worldclass.py
   НЕ копировать папку ZIP целиком в WorldClass: скрипт должен лежать
   рядом с worldclass_progress.sqlite3 и worldclass_trainers.csv.

ПРОВЕРКА И СБОР URL (без подробных страниц):
.\.venv\Scripts\python.exe collect_worldclass.py --discover-only --api-max-pages 500 --max-clicks 150 --delay 2 --show-browser

ПОСЛЕ СБОРА URL — ОБРАБОТКА ПРОФИЛЕЙ:
.\.venv\Scripts\python.exe collect_worldclass.py --skip-api --max-profiles 5000 --delay 2 --show-browser

Проверить строки «API ...» и «API каталог: ok».
Если сработал резервный режим, искать строку «Резервный каталог: ok/partial».
При partial сохраняются все обнаруженные URL; следующий запуск безопасен.
Не изменять CSV, SQLite и PostgreSQL вручную.

ВНИМАНИЕ: эта версия не протестирована на сайте из этой среды; синтаксис Python
и целостность ZIP проверены. API может менять правила доступа и формат ответа.
