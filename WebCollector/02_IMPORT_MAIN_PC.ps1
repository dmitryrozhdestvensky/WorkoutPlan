#requires -Version 5.1
param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [string]$TargetRoot = 'E:\GoogleDrive\WorkoutPlan\WebCollector'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) { throw "ZIP not found: $Archive" }
$Archive = (Resolve-Path -LiteralPath $Archive).ProviderPath
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\')
New-Item -Path $TargetRoot -ItemType Directory -Force | Out-Null
$backupBase = Join-Path $TargetRoot 'TransferBackups'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $backupBase $stamp
$stage = Join-Path $env:TEMP "WebCollector_Import_$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    Write-Host 'Unpacking transfer archive ...'
    # Prevalidate archive entry paths before extraction.
    Add-Type -AssemblyName 'System.IO.Compression.FileSystem'
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\','/')
            if ($name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)' -or $name -match '^[A-Za-z]:' -or $name -notmatch '^(payload/|manifest\.json$)') {
                throw "Unsafe/unexpected archive path: $name"
            }
        }
    } finally { $zip.Dispose() }
    Expand-Archive -LiteralPath $Archive -DestinationPath $stage -Force
    $manifestPath = Join-Path $stage 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'manifest.json is missing.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.format -ne 'webcollector-transfer-v1') { throw 'Unexpected transfer format.' }
    if (@($manifest.files).Count -ne [int]$manifest.file_count) { throw 'Manifest count mismatch.' }
    $seen = @{}
    $items = New-Object 'System.Collections.Generic.List[object]'
    Write-Host "Verifying $($manifest.file_count) file hashes ..."
    foreach ($item in $manifest.files) {
        $rel = [string]$item.path
        if ([string]::IsNullOrWhiteSpace($rel) -or $rel.StartsWith('/') -or $rel -match '(^|/)\.\.(/|$)' -or $rel -match '^[A-Za-z]:' -or $rel.Contains('\') -or $rel -match '[\x00-\x1f]') {
            throw "Unsafe manifest path: $rel"
        }
        $key = $rel.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { throw "Duplicate file path: $rel" }
        $seen[$key] = $true
        $localRel = $rel.Replace('/', '\')
        $source = Join-Path (Join-Path $stage 'payload') $localRel
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing payload file: $rel" }
        if ((Get-Item -LiteralPath $source).Length -ne [long]$item.bytes) { throw "Size mismatch: $rel" }
        $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne ([string]$item.sha256).ToLowerInvariant()) { throw "Hash mismatch: $rel" }
        $items.Add([pscustomobject]@{ path = $rel; localRel = $localRel; source = $source; hash = $hash })
    }
    # Backup ALL existing files which could be overwritten before changing any files.
    $collisions = @($items | Where-Object { Test-Path -LiteralPath (Join-Path $TargetRoot $_.localRel) -PathType Leaf })
    Write-Host "Verified files: $($items.Count); existing files to replace: $($collisions.Count)"
    Write-Host "Existing files will be backed up in: $backupDir"
    $confirm = Read-Host 'Type YES to import (anything else cancels)'
    if ($confirm -cne 'YES') { Write-Host 'Cancelled, nothing changed.'; return }
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    foreach ($item in $collisions) {
        $oldPath = Join-Path $TargetRoot $item.localRel
        $backupPath = Join-Path $backupDir $item.localRel
        $parent = Split-Path -Parent $backupPath
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath $oldPath -Destination $backupPath -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $oldPath -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash) { throw "Backup verification failed: $($item.path)" }
    }
    $logPath = Join-Path $backupDir 'imported_files.txt'
    $items.path | Set-Content -LiteralPath $logPath -Encoding UTF8
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $backupDir 'source_manifest.json')
    foreach ($item in $items) {
        $destination = Join-Path $TargetRoot $item.localRel
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $tempTarget = Join-Path $parent ('.webcollector_incoming_' + [guid]::NewGuid().ToString('N'))
        try {
            Copy-Item -LiteralPath $item.source -Destination $tempTarget -ErrorAction Stop
            Move-Item -LiteralPath $tempTarget -Destination $destination -Force -ErrorAction Stop
        } finally { if (Test-Path -LiteralPath $tempTarget) { Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue } }
        $resultHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($resultHash -ne $item.hash) { throw "Post-import hash mismatch: $($item.path)" }
    }
    Write-Host "`nIMPORT OK: $($items.Count) files"
    Write-Host "Primary folder: $TargetRoot"
    Write-Host "Previous versions backed up at: $backupDir"
    $master = Join-Path $TargetRoot 'Data\fitness_trainers_master.xlsx'
    if (Test-Path -LiteralPath $master) { Write-Host "Master Excel: $master" }
    Write-Host 'Virtual environments were NOT transferred. Reuse or recreate .venv on this computer.'
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
