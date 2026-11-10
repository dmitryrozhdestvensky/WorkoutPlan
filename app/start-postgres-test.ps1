$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'mount-workoutplan-drive.ps1')
$testDrive = 'W:'
$testRoot = "$testDrive\data"
$pgBin = Join-Path $testRoot 'postgres17/pgsql/bin'
$cluster = Join-Path $testRoot 'postgres-test-cluster'
$passwordFile = Join-Path $testRoot 'postgres-test-password.txt'
$port = 15432

if (-not (Test-Path (Join-Path $pgBin 'initdb.exe'))) {
    throw 'Extract the PostgreSQL 17 Windows binaries into data/postgres17 first.'
}
if (-not (Test-Path (Join-Path $cluster 'PG_VERSION'))) {
    if (-not (Test-Path $passwordFile)) {
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 24
        $random.GetBytes($bytes)
        $random.Dispose()
        [IO.File]::WriteAllText($passwordFile, [Convert]::ToBase64String($bytes))
    }
    & "$pgBin/initdb.exe" -D $cluster -U workoutplan_test --auth=scram-sha-256 --encoding=UTF8 --locale=C "--pwfile=$passwordFile"
    if ($LASTEXITCODE) { throw 'PostgreSQL cluster initialization failed.' }
}

& "$pgBin/pg_ctl.exe" -D $cluster status | Out-Null
if ($LASTEXITCODE) {
    & "$pgBin/pg_ctl.exe" -D $cluster -l (Join-Path $testRoot 'postgres-test.log') -o "-p $port -h 127.0.0.1" -w -t 180 start
    if ($LASTEXITCODE) { throw 'PostgreSQL startup failed. See data/postgres-test.log.' }
}

$env:PGPASSWORD = [IO.File]::ReadAllText($passwordFile).Trim()
try {
    $dbExists = & "$pgBin/psql.exe" -X -w -h 127.0.0.1 -p $port -U workoutplan_test -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='workoutplan_test'"
    if ($LASTEXITCODE) { throw 'Cannot connect to the test PostgreSQL server.' }
    if ($dbExists -ne '1') {
        & "$pgBin/createdb.exe" -w -h 127.0.0.1 -p $port -U workoutplan_test workoutplan_test
        if ($LASTEXITCODE) { throw 'Cannot create the test database.' }
    }
    & "$pgBin/psql.exe" -X -w -h 127.0.0.1 -p $port -U workoutplan_test -d workoutplan_test -c 'SELECT current_database(), current_user;'
    if ($LASTEXITCODE) { throw 'Test database verification failed.' }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
