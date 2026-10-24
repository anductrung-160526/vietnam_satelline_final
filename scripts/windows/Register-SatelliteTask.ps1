param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$RcloneConfig,
    [string]$Remote = "gdrive",
    [string]$Credentials,
    [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference = "Stop"
if (($RcloneConfig -and $Credentials) -or (-not $RcloneConfig -and -not $Credentials)) {
    throw "Supply exactly one of -RcloneConfig or -Credentials"
}
$authPath = if ($RcloneConfig) { $RcloneConfig } else { $Credentials }
foreach ($path in @($Repo, $Config, $authPath, $Python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Path missing: $path" }
    if ($path.Contains('"')) { throw "Invalid path" }
}
if ($Remote -notmatch '^[A-Za-z0-9_-]+$') { throw "Invalid remote name" }
$script = Join-Path $Repo "scripts\windows\Receive-Satellite.ps1"
$arguments = "-NoProfile -File `"$script`" -Repo `"$Repo`" -Config `"$Config`" -Python `"$Python`""
if ($RcloneConfig) { $arguments += " -RcloneConfig `"$RcloneConfig`" -Remote `"$Remote`"" }
else { $arguments += " -Credentials `"$Credentials`"" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $Repo
$login = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk" -Action $action -Trigger @($login,$repeat) -Settings $settings -Description "Receive verified satellite batches; resumes when laptop and external disk are available."
