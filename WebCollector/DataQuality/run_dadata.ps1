$ErrorActionPreference = "Stop"

$config = $env:WEBCOLLECTOR_CONFIG
if (-not $config) { $config = "E:\GoogleDrive\WorkoutPlan\WebCollector\Config\.env" }
$python = "E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\.venv\Scripts\python.exe"
$program = "E:\GoogleDrive\WorkoutPlan\WebCollector\DataQuality\dadata_quality.py"

if (-not (Test-Path $config)) {
    throw "Config file not found: $config"
}

if (-not (Test-Path $python)) {
    throw "Python not found: $python"
}

if (-not (Test-Path $program)) {
    throw "Program not found: $program"
}

$keys = @{}

foreach ($line in [System.IO.File]::ReadAllLines($config)) {
    $line = $line.Trim()

    if (-not $line -or $line.StartsWith("#")) {
        continue
    }

    $parts = $line -split "=", 2

    if ($parts.Count -eq 2) {
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        $keys[$name] = $value
    }
}

foreach ($name in @("DADATA_API_KEY", "DADATA_SECRET_KEY")) {
    if (-not $keys.ContainsKey($name)) {
        throw "Missing key: $name"
    }

    $value = $keys[$name]

    if (
        [string]::IsNullOrWhiteSpace($value) -or
        $value -match '[\x00-\x1F\x7F]'
    ) {
        throw "Invalid value: $name"
    }

    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

try {
    & $python $program @args
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:DADATA_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:DADATA_SECRET_KEY -ErrorAction SilentlyContinue
}

exit $exitCode