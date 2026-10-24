param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$RcloneConfig,
    [string]$Remote = "gdrive",
    [string]$Credentials,
    [string]$Python = "python",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location $Repo
if ($RcloneConfig -and $Credentials) { throw "Choose RcloneConfig or Credentials, not both" }
if ($RcloneConfig) {
    $env:PROVINCE_RCLONE_CONFIG = $RcloneConfig
    $env:PROVINCE_RCLONE_REMOTE = $Remote
    Remove-Item Env:PROVINCE_GOOGLE_CREDENTIALS -ErrorAction SilentlyContinue
} elseif ($Credentials) {
    $env:PROVINCE_GOOGLE_CREDENTIALS = $Credentials
    Remove-Item Env:PROVINCE_RCLONE_CONFIG -ErrorAction SilentlyContinue
} else { throw "Supply -RcloneConfig (recommended) or -Credentials" }
$arguments = @("-m", "province_pipeline", "--config", $Config, "receive")
if ($DryRun) { $arguments += "--dry-run" }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $DryRun) {
    & $Python -m province_pipeline --config $Config aggregate
    exit $LASTEXITCODE
}
