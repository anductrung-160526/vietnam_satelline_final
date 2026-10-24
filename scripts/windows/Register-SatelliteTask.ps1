param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$RcloneConfig,
    [string]$Remote = "gdrive",
    [string]$Credentials,
    [string]$RcloneExecutable,
    [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference = "Stop"
if (($RcloneConfig -and $Credentials) -or (-not $RcloneConfig -and -not $Credentials)) {
    throw "Supply exactly one of -RcloneConfig or -Credentials"
}
$authPath = if ($RcloneConfig) { $RcloneConfig } else { $Credentials }
if ($RcloneConfig -and -not $RcloneExecutable) {
    $RcloneExecutable = (Get-Command rclone -ErrorAction Stop).Source
}
if ($RcloneExecutable -and (-not (Test-Path -LiteralPath $RcloneExecutable) -or $RcloneExecutable.Contains('"'))) {
    throw "Invalid rclone executable path"
}
foreach ($path in @($Repo, $Config, $authPath, $Python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Path missing: $path" }
    if ($path.Contains('"')) { throw "Invalid path" }
}
if ($Remote -notmatch '^[A-Za-z0-9_-]+$') { throw "Invalid remote name" }
$Repo = (Resolve-Path -LiteralPath $Repo).Path
$Config = (Resolve-Path -LiteralPath $Config).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$authPath = (Resolve-Path -LiteralPath $authPath).Path
if ($RcloneConfig) { $RcloneConfig = $authPath } else { $Credentials = $authPath }
$script = Join-Path $Repo "scripts\windows\Receive-Satellite.ps1"
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$script`" -Repo `"$Repo`" -Config `"$Config`" -Python `"$Python`""
if ($RcloneConfig) { $arguments += " -RcloneConfig `"$RcloneConfig`" -Remote `"$Remote`" -RcloneExecutable `"$RcloneExecutable`"" }
else { $arguments += " -Credentials `"$Credentials`"" }
$powerShellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory $Repo
$login = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk" -Action $action -Trigger @($login,$repeat) -Settings $settings -Description "Receive verified satellite batches; resumes when laptop and external disk are available."
