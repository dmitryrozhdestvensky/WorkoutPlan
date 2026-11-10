WORLD CLASS API SAMPLE TOOL V1.1

Исправление:
- Навигация больше не ждёт DOMContentLoaded. Используется wait_until="commit",
  чтобы медленная загрузка скриптов и ресурсов страницы не прерывала диагностику.
- Если навигация всё же превышает таймаут, скрипт проверяет текущий URL и
  пробует выполнить API-запрос в открытом контексте браузера.
- В JSON добавляется информация о результате навигации.

Установка:
1. Распакуйте архив, например, в C:\WebCollector\WorldClass\api_sample_tool_v1_1
2. Откройте PowerShell:
   cd C:\WebCollector\WorldClass
3. Запустите:
   .\.venv\Scripts\python.exe .\api_sample_tool_v1_1\diagnose_worldclass_api.py

При необходимости увеличьте таймаут навигации:
   .\.venv\Scripts\python.exe .\api_sample_tool_v1_1\diagnose_worldclass_api.py --navigation-timeout 60000

Результат по умолчанию:
   C:\WebCollector\WorldClass\worldclass_api_sample.json

Скрипт только читает публичный API. Он НЕ меняет worldclass_trainers.csv,
worldclass_progress.sqlite3 и PostgreSQL.
