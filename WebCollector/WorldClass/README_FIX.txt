WorldClass Collector V1.3 — замена только одного файла

1) Скопируйте collect_worldclass.py из этого архива в C:\WebCollector\WorldClass с заменой.
2) Не удаляйте worldclass_progress.sqlite3, CSV или merge_worldclass.py.
3) Из PowerShell:
   cd C:\WebCollector\WorldClass
   .\.venv\Scripts\python.exe collect_worldclass.py --max-profiles 1500 --max-list-pages 120 --max-clicks 160 --show-browser
4) Сначала дождитесь строки «Показать еще #1» и проверьте, что показано +12.
5) Только по завершении сборки: .\.venv\Scripts\python.exe merge_worldclass.py

Изменения: закрытие всплывающего окна cookies, точный селектор кнопки World Class,
ожидание появления новых URL, диагностический скриншот при неудаче.
Окно cookies может появиться повторно в зависимости от настроек сайта.
Скрипт не проверен на полноценном живом обходе в Windows.
