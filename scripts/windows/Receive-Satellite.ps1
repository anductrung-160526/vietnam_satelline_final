param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$RcloneConfig,
    [string]$Remote = "gdrive",
    [string]$Credentials,
    [string]$RcloneExecutable,
    [string]$LogDirectory = (Join-Path $env:LOCALAPPDATA "SatellitePipeline\logs"),
    [string]$Python = "python",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location $Repo
if ($RcloneConfig -and $Credentials) { throw "Choose RcloneConfig or Credentials, not both" }
if ($RcloneConfig) {
    $env:PROVINCE_RCLONE_CONFIG = $RcloneConfig
    $env:PROVINCE_RCLONE_REMOTE = $Remote
    if (-not $RcloneExecutable) { $RcloneExecutable = (Get-Command rclone -ErrorAction Stop).Source }
    if (-not (Test-Path -LiteralPath $RcloneExecutable)) { throw "Rclone executable not found" }
    $env:PROVINCE_RCLONE_EXECUTABLE = $RcloneExecutable
    Remove-Item Env:PROVINCE_GOOGLE_CREDENTIALS -ErrorAction SilentlyContinue
} elseif ($Credentials) {
    $env:PROVINCE_GOOGLE_CREDENTIALS = $Credentials
    Remove-Item Env:PROVINCE_RCLONE_CONFIG -ErrorAction SilentlyContinue
} else { throw "Supply -RcloneConfig (recommended) or -Credentials" }
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$logFile = Join-Path $LogDirectory ("receiver-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff") + ".log")
Start-Transcript -Path $logFile | Out-Null
$exitCode = 1
try {
    $arguments = @("-m", "province_pipeline", "--config", $Config, "receive")
    if ($DryRun) { $arguments += "--dry-run" }
    & $Python @arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0 -and -not $DryRun) {
        & $Python -m province_pipeline --config $Config aggregate
        $exitCode = $LASTEXITCODE
    }
} finally {
    Stop-Transcript | Out-Null
}
exit $exitCode
