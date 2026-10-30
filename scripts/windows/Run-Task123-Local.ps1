param(
    [ValidateSet("run", "derive", "migrate")][string]$Command = "run",
    [ValidateSet("pilot", "full")][string]$Mode = "full",
    [ValidateSet("1-11", "12-22", "23-33", "34-43", "44-53", "54-63")][string]$Range,
    [ValidateSet("night", "day")][string]$Start = "night",
    [string]$Python = "python",
    [string]$Root = "E:\SatelliteData",
    [string]$Project,
    [string]$Config,
    [string]$EeKey
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location -LiteralPath $repo
if (-not (Test-Path -LiteralPath "E:\")) { throw "External drive E is not connected" }
if ([IO.Path]::GetPathRoot($Root) -ine "E:\") { throw "Choose a destination on external drive E" }
$tag = if ($Range) { $Range } else { "branch" }
$logDirectory = Join-Path $env:LOCALAPPDATA "SatellitePipeline\direct-logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logFile = Join-Path $logDirectory ("local-" + $Command + "-" + $tag + "-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff") + ".log")
if ($Command -eq "migrate") {
    $arguments = @("-u", "-m", "task_pipeline.local", "migrate", "--root", $Root)
} else {
    $arguments = @("-u", "-m", "task_pipeline.local", $Command, "--mode", $Mode, "--root", $Root)
    if ($Range) { $arguments += @("--range", $Range) }
    if ($Command -eq "run") { $arguments += @("--start", $Start) }
    if ($Project) { $arguments += @("--project", $Project) }
    if ($Config) { $arguments += @("--config", $Config) }
    if ($EeKey) { $arguments += @("--ee-key", $EeKey) }
}
$Host.UI.RawUI.WindowTitle = "Satellite $Command $tag"
Start-Transcript -Path $logFile | Out-Null
$exitCode = 1
try {
    & $Python @arguments
    $exitCode = $LASTEXITCODE
} finally {
    Stop-Transcript | Out-Null
}
Write-Host "Exit code: $exitCode  (0 = xong, 2 = loi mang/quyen: chay lai, 4 = o E gan day, 130 = da dung)"
exit $exitCode
