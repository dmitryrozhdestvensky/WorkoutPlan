#requires -Version 5.1
param(
    [string]$SourceRoot = 'E:\GoogleDrive\WorkoutPlan\WebCollector',
    [string]$OutputDirectory = [Environment]::GetFolderPath('Desktop')
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw "Source folder not found: $SourceRoot" }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath.TrimEnd('\')
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).ProviderPath
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$zipPath = Join-Path $OutputDirectory "WebCollector_Laptop_$stamp.zip"
$stage = Join-Path $env:TEMP "WebCollector_Export_$([guid]::NewGuid().ToString('N'))"
$payload = Join-Path $stage 'payload'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
$skipDirs = @('.venv','venv','env','__pycache__','.git','.pytest_cache','.mypy_cache','node_modules','TransferBackups','TransferArchives','playwright-browsers')
$skipNames = @('Thumbs.db','.DS_Store')
$files = New-Object 'System.Collections.Generic.List[object]'
try {
    Write-Host "Scanning $SourceRoot ..."
    # -Force includes hidden files. Skip temporary / virtualenv folders, not project data.
    $all = @(Get-ChildItem -LiteralPath $SourceRoot -File -Recurse -Force -ErrorAction Stop)
    foreach ($file in $all) {
        $relative = $file.FullName.Substring($SourceRoot.Length).TrimStart('\')
        $segments = $relative -split '[\\/]'
        $excluded = $false
        foreach ($segment in $segments) {
            if ($skipDirs -contains $segment) { $excluded = $true; break }
        }
        if ($excluded -or $skipNames -contains $file.Name) { continue }
        if ($file.Extension -in @('.pyc','.pyo','.tmp','.part')) { continue }
        if ($file.FullName -eq $zipPath) { continue }
        $relativeSlash = $relative.Replace('\','/')
        $destination = Join-Path $payload $relative
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
        $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        $files.Add([pscustomobject]@{ path = $relativeSlash; bytes = [long]$file.Length; sha256 = $hash })
    }
    if ($files.Count -eq 0) { throw 'No files found to export.' }
    $critical = @('Data/fitness_trainers_master.xlsx','SocialEnrichment/social_candidates.csv','DDXFitness/ddxfitness_trainers.csv')
    foreach ($p in $critical) {
        if (-not ($files | Where-Object { $_.path -ieq $p })) { Write-Warning "Important file absent from laptop: $p" }
    }
    $manifest = [pscustomobject]@{
        format = 'webcollector-transfer-v1'
        exported_at = (Get-Date).ToString('o')
        source_root = $SourceRoot
        file_count = $files.Count
        files = @($files.ToArray())
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage 'manifest.json') -Encoding UTF8
    Add-Type -AssemblyName 'System.IO.Compression.FileSystem'
    [System.IO.Compression.ZipFile]::CreateFromDirectory($stage, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    Write-Host "`nEXPORT OK: $zipPath"
    Write-Host "Files: $($files.Count); size: $([math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)) MB"
    Write-Host 'Copy THIS ZIP to the primary computer. Do not copy the .venv folders.'
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
