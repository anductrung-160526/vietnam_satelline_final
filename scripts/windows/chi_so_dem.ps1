# Tính chỉ số ảnh đêm cho cả 63 tỉnh, rồi nạp vào ứng dụng VNGISDash.
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows\chi_so_dem.ps1
#
# Chỉ chạy nửa ảnh đêm (--only night). Ảnh đêm nhẹ (500 m - 1 km) nên nhanh;
# nửa ảnh ngày chậm hơn nhiều và chạy riêng sau bằng:  -Only day
#
# Không gọi Earth Engine: chỉ đọc ảnh đã tải trên ổ E và tính ra bảng chỉ số.
# Chạy lại được bao nhiêu lần cũng được — phần nào đã tính xong thì bỏ qua.

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
Write-Host "  rồi mở http://localhost:8000"
