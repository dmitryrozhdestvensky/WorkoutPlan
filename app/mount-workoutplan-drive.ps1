$ErrorActionPreference = 'Stop'
$testDrive = 'W:'
Add-Type -Name DriveMapping -Namespace WorkoutPlan -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern uint QueryDosDevice(string name, System.Text.StringBuilder target, int capacity);
'@
$target = New-Object System.Text.StringBuilder 32768
$mapped = [WorkoutPlan.DriveMapping]::QueryDosDevice($testDrive, $target, $target.Capacity)
if (-not $mapped) {
    if (Test-Path "$testDrive\") { throw 'Drive W: is already in use.' }
    & subst.exe $testDrive $PSScriptRoot
    if ($LASTEXITCODE) { throw 'Could not map the project to drive W:.' }
} elseif ($PSScriptRoot.TrimEnd('\') -ine $testDrive -and
          $target.ToString().TrimEnd('\') -ine ('\??\' + $PSScriptRoot.TrimEnd('\'))) {
    throw 'Drive W: is mapped to another folder.'
}
