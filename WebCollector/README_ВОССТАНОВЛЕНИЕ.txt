ВОССТАНОВЛЕНИЕ WebCollector НА РАБОЧЕМ НОУТБУКЕ
=================================================
1. Распакуйте содержимое ЭТОГО архива непосредственно в C:\WebCollector.
   Должно быть C:\WebCollector\Data\fitness_trainers_master.xlsx и C:\WebCollector\TenChat\collect_tenchat_v7.py.
2. В PowerShell выполните:
      powershell -NoProfile -ExecutionPolicy Bypass -File C:\WebCollector\SETUP_WINDOWS.ps1
   Перед запуском можно открыть файл SETUP_WINDOWS.ps1 в Блокноте и изучить.
3. Тест RegymSport:
      cd C:\WebCollector\RegymSport
      .\.venv\Scripts\python.exe collect_regymsport.py --max-profiles 5 --show-browser
4. Тест TenChat:
      cd C:\WebCollector\TenChat
      .\.venv\Scripts\python.exe collect_tenchat_v7.py --max-pages 5

ВАЖНО
- Главная база: Data\fitness_trainers_master.xlsx — 495 записей (496 строк с заголовком).
- Внутренние файлы fitness_trainers_base_215.xlsx (TenChat) и fitness_trainers_base.xlsx (RegymSport) содержат копию ЭТОЙ базы для совместимости с прежними merge-скриптами, несмотря на старое имя.
- WorldClass восстановлен как V1.4 с известной проблемой динамической загрузки, автоматический обход пока не рекомендуем.
- Контрольные точки SQLite/JSON с основного компьютера недоступны; собранный прогресс по посещённым страницам не восстановлен. Сами 495 анкет сохранены.
- Нельзя запускать сразу несколько объединений с копиями базы и потом заменять master без проверки: объединение каждым прежним сборщиком создаёт СВОЙ выходной Excel, а не обновляет общий автоматически.
- После новых сборов проверяйте выходной Excel, сохраняйте резервную копию master в Data\Backups, затем обновляйте master. Перед следующим объединением обновляйте локальную копию базы в соответствующем сборщике.
- Для переноса на основной компьютер заберите Data\fitness_trainers_master.xlsx и новую историю/CSV/SQLite из рабочих папок, сравните даты и записи.
