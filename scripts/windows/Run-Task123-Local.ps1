param(
    [ValidateSet("pilot", "full")][string]$Mode = "pilot",
    [string]$Python = "python",
    [string]$Root = "E:\SatelliteData",
    [string]$Config,
    [string]$EeKey
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location -LiteralPath $repo
if (-not (Test-Path -LiteralPath "E:\")) { throw "External drive E is not connected" }
if ([IO.Path]::GetPathRoot($Root) -ine "E:\") { throw "Choose a destination on external drive E" }
$logDirectory = Join-Path $env:LOCALAPPDATA "SatellitePipeline\direct-logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logFile = Join-Path $logDirectory ("local-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff") + ".log")
$arguments = @("-u", "-m", "task_pipeline.local", "run", "--mode", $Mode, "--root", $Root)
if ($Config) { $arguments += @("--config", $Config) }
if ($EeKey) { $arguments += @("--ee-key", $EeKey) }
Start-Transcript -Path $logFile | Out-Null
$exitCode = 1
try {
    & $Python @arguments
    $exitCode = $LASTEXITCODE
} finally {
    Stop-Transcript | Out-Null
}
exit $exitCode
