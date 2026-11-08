# Tinh chi so anh dem cho ca 63 tinh, roi nap vao ung dung VNGISDash.
# File nay chi dung ky tu ASCII: PowerShell 5.1 doc file UTF-8 khong BOM
# theo bang ma ANSI, nen dau tieng Viet se thanh ky tu rac va vo cu phap.
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows\chi_so_dem.ps1
#
# Chi chay nua anh dem (--only night). Anh dem nhe (500 m - 1 km) nen nhanh;
# nua anh ngay cham hon nhieu va chay rieng sau bang:  -Only day
#
# Khong goi Earth Engine: chi doc anh da tai tren o E va tinh ra bang chi so.
# Chay lai duoc bao nhieu lan cung duoc - phan nao da tinh xong thi bo qua.

param(
  [string]$Root = 'E:\SatelliteData',
  [ValidateSet('night','day','all')][string]$Only = 'night',
  [string[]]$Ranges = @('1-11','12-22','23-33','34-43','44-53','54-63')
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

if (-not (Test-Path $Root)) {
  Write-Error "Khong thay $Root. Cam o cung chua anh roi chay lai."
}

$batDau = Get-Date
Write-Host "=== Tinh chi so ($Only) cho 63 tinh, doc tu $Root ===" -ForegroundColor Cyan

$hong = @()
foreach ($r in $Ranges) {
  Write-Host ""
  Write-Host "--- Nhom tinh $r ---" -ForegroundColor Yellow
  $t = Get-Date
  & python -m task_pipeline.local derive --mode full --range $r --root $Root --only $Only
  if ($LASTEXITCODE -ne 0) {
    Write-Host "    HONG (ma loi $LASTEXITCODE)" -ForegroundColor Red
    $hong += $r
  } else {
    Write-Host ("    xong sau {0:n0} giay" -f ((Get-Date) - $t).TotalSeconds) -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "=== Ket qua ===" -ForegroundColor Cyan
Write-Host ("Tong thoi gian: {0:n0} phut" -f ((Get-Date) - $batDau).TotalMinutes)

# Bang chi so da duoc derive.merge() gop san vao data_processed.
$bang = Join-Path $Root 'VN_NTL_Panel_2004_2025\data_processed\ntl_annual.csv'
if (Test-Path $bang) {
  $soDong = (Import-Csv $bang | Measure-Object).Count
  Write-Host "ntl_annual.csv: $soDong dong" -ForegroundColor Green
  Write-Host "  (du kien 63 tinh x 22 nam = 1386 dong khi day du)"
} else {
  Write-Host "CHUA CO $bang" -ForegroundColor Red
}

if ($hong.Count) {
  Write-Host ("Nhom tinh bi loi: {0}" -f ($hong -join ', ')) -ForegroundColor Red
  Write-Host "Chay lai rieng nhom do, vi du:  -Ranges 12-22"
}

Write-Host ""
Write-Host "Nap vao ung dung:" -ForegroundColor Cyan
Write-Host "  python -m app.data.build_indices --root $Root"
Write-Host "  uvicorn app.api.main:app --reload"
Write-Host "  roi mo http://localhost:8000"
