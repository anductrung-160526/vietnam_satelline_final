param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$Credentials,
    [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference = "Stop"
foreach ($path in @($Repo, $Config, $Credentials, $Python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Path missing: $path" }
    if ($path.Contains('"')) { throw "Invalid path" }
}
$script = Join-Path $Repo "scripts\windows\Receive-Satellite.ps1"
$arguments = "-NoProfile -File `"$script`" -Repo `"$Repo`" -Config `"$Config`" -Credentials `"$Credentials`" -Python `"$Python`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $Repo
$login = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk" -Action $action -Trigger @($login,$repeat) -Settings $settings -Description "Receive verified satellite batches; resumes when laptop and external disk are available."
