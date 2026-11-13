$ErrorActionPreference = "Stop"
$root = "E:\GoogleDrive\WorkoutPlan\WebCollector"
if (-not (Test-Path "$root\Data\fitness_trainers_master.xlsx")) { throw "Сначала распакуйте содержимое архива в E:\GoogleDrive\WorkoutPlan\WebCollector" }
& py -3.13 --version
foreach ($name in @("TenChat","RegymSport","WorldClass")) {
  $dir = Join-Path $root $name
  Write-Host "`nНастройка $name..." -ForegroundColor Cyan
  Push-Location $dir
  try {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать .venv для $name" }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Ошибка установки pip для $name" }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Ошибка установки зависимостей для $name" }
  } finally { Pop-Location }
}
Push-Location "$root\TenChat"
try { & .\.venv\Scripts\python.exe -m playwright install chromium; if ($LASTEXITCODE -ne 0) { throw "Ошибка Chromium" } } finally {Pop-Location}
Write-Host "`nГотово. Сначала запустите небольшой тест TenChat или RegymSport." -ForegroundColor Green
