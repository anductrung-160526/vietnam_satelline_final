param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$Credentials,
    [string]$Python = "python",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location $Repo
$env:PROVINCE_GOOGLE_CREDENTIALS = $Credentials
$arguments = @("-m", "province_pipeline", "--config", $Config, "receive")
if ($DryRun) { $arguments += "--dry-run" }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $DryRun) {
    & $Python -m province_pipeline --config $Config aggregate
    exit $LASTEXITCODE
}
