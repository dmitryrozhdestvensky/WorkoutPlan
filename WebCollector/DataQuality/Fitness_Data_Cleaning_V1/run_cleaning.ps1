param(
  [Parameter(Position=0)][ValidateSet('audit','probe','run','report')][string]$Command='audit',
  [int]$Limit=20,
  [double]$MaxSpendRub=0,
  [switch]$ConfirmRequests
)
$ErrorActionPreference='Stop'
$envPath=$env:WEBCOLLECTOR_CONFIG
if (-not $envPath) { $envPath=Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "Config\.env" }
$keys=@('DADATA_API_KEY','DADATA_SECRET_KEY')
try {
  if ($Command -in @('probe','run')) {
    if (-not (Test-Path -LiteralPath $envPath)) { throw "Config file not found: $envPath" }
    foreach($line in [System.IO.File]::ReadAllLines($envPath)) {
      if($line -match '^\s*(DADATA_API_KEY|DADATA_SECRET_KEY)\s*=\s*(.*?)\s*$') {
        $value=$Matches[2].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($Matches[1],$value,'Process')
      }
    }
  }
  $parameters=@((Join-Path $PSScriptRoot 'fitness_clean.py'),$Command,'--output','E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\PostgreSQL','--limit',"$Limit")
  if ($ConfirmRequests) { $parameters+='--confirm-requests' }
  if($MaxSpendRub -gt 0) { $parameters+=@('--max-spend-rub',([string]::Format([Globalization.CultureInfo]::InvariantCulture,'{0}', $MaxSpendRub))) }
  & (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") @parameters
  if($LASTEXITCODE -ne 0){throw "Python exited with code $LASTEXITCODE"}
} finally {
  foreach($key in $keys){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
}
