World Class API — получение трёх исходных JSON-записей

Назначение:
Сохранить первые три полных объекта из публичного API World Class, включая
все вложенные поля attributes и связи. Скрипт нужен для анализа структуры API
и подготовки корректного парсера. Он не меняет существующие CSV, SQLite или PostgreSQL.

Требования:
- Python 3.10+
- Playwright уже установлен в виртуальном окружении проекта
- Chromium Playwright уже установлен

Установка:
1. Распакуйте архив, например, в C:\WebCollector\WorldClass\api_sample_tool
2. Откройте PowerShell:

   cd C:\WebCollector\WorldClass

3. Запустите тем же Python, которым работает основной сборщик:

   .\.venv\Scripts\python.exe .\api_sample_tool\diagnose_worldclass_api.py

По умолчанию откроется видимое окно браузера. Дождитесь сообщения о сохранении файла.
Результат будет создан в текущей папке:

   C:\WebCollector\WorldClass\worldclass_api_sample.json

Если нужно запускать без видимого окна:

   .\.venv\Scripts\python.exe .\api_sample_tool\diagnose_worldclass_api.py --headless

Если API вернёт ошибку, скрипт покажет HTTP-статус и фрагмент ответа.
Не запускайте основной сборщик для этой диагностики. Никакие существующие данные
не перезаписываются.

После выполнения пришлите worldclass_api_sample.json.
