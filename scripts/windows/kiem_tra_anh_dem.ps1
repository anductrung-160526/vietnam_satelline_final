# Xem anh dem dang nam o dau va theo layout nao.
# File nay chi dung ky tu ASCII: PowerShell 5.1 doc file UTF-8 khong BOM
# theo bang ma ANSI, nen dau tieng Viet se thanh ky tu rac va vo cu phap.
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows\kiem_tra_anh_dem.ps1
#
# Co HAI layout khac nhau cung nam duoi raw_data/NTL/, va buoc tinh chi so
# (task_pipeline.local derive) chi doc duoc MOT trong hai:
#
#   raw_data\NTL\VIIRS\VN_VIIRS_2024\tiles\    <- 10 luong national.py tai. KHONG doc duoc.
#   raw_data\NTL\VIIRS\01_ha_noi\              <- pipeline theo tinh tai.  DOC DUOC.
#
# Script nay chi doc, khong sua gi.

param([string]$Root = 'E:\SatelliteData')

$ErrorActionPreference = 'Continue'

Write-Host "=== Kiem tra anh dem trong $Root ===" -ForegroundColor Cyan

if (-not (Test-Path $Root)) {
  Write-Host "KHONG THAY $Root" -ForegroundColor Red
  Write-Host "O cung chua duoc cam, hoac no mang chu o khac. Xem danh sach o:"
  Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{n='Trong(GB)';e={[math]::Round($_.Free/1GB,1)}}, @{n='Tong(GB)';e={[math]::Round(($_.Used+$_.Free)/1GB,1)}} | Format-Table
  exit 1
}

foreach ($nguon in @('VIIRS','DMSP')) {
  $thuMuc = Join-Path $Root "VN_NTL_Panel_2004_2025\raw_data\NTL\$nguon"
  Write-Host ""
  Write-Host "--- $nguon ---" -ForegroundColor Yellow
  Write-Host "    $thuMuc"

  if (-not (Test-Path $thuMuc)) {
    Write-Host "    CHUA CO thu muc nay - chua tai anh $nguon ve o nay." -ForegroundColor Red
    continue
  }

  $con = Get-ChildItem $thuMuc -Directory -ErrorAction SilentlyContinue
  if (-not $con) {
    Write-Host "    Thu muc rong - chua co anh nao." -ForegroundColor Red
    continue
  }

  # Layout quoc gia: ten thu muc dang VN_<NGUON>_<nam>
  $quocGia = @($con | Where-Object { $_.Name -match "^VN_${nguon}_\d{4}$" })
  # Layout theo tinh: ten thu muc dang <2 chu so>_<slug>
  $theoTinh = @($con | Where-Object { $_.Name -match '^\d{2}_' })

  if ($theoTinh.Count) {
    $soAnh = (Get-ChildItem $thuMuc -Recurse -Filter *.tif -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "    DUNG LAYOUT: $($theoTinh.Count) thu muc tinh, $soAnh file .tif" -ForegroundColor Green
    Write-Host "    Tinh dau tien: $($theoTinh[0].Name)"
    if ($theoTinh.Count -lt 63) {
      Write-Host "    Luu y: moi co $($theoTinh.Count)/63 tinh." -ForegroundColor Yellow
    }
  }

  if ($quocGia.Count) {
    $nam = ($quocGia.Name | ForEach-Object { $_ -replace '\D','' } | Sort-Object) -join ', '
    Write-Host "    SAI LAYOUT cho buoc tinh chi so: $($quocGia.Count) thu muc kieu quoc gia" -ForegroundColor Red
    Write-Host "    Cac nam: $nam"
    Write-Host "    Day la anh do 10 luong national.py tai (chia theo o, toan quoc)." -ForegroundColor Red
    Write-Host "    derive.py KHONG doc duoc layout nay - can cat theo tinh truoc." -ForegroundColor Red
  }

  if (-not $theoTinh.Count -and -not $quocGia.Count) {
    Write-Host "    Co thu muc con nhung khong khop layout nao:" -ForegroundColor Yellow
    $con | Select-Object -First 5 | ForEach-Object { Write-Host "      $($_.Name)" }
  }
}

# Co phieu nhan (receipt) khong: derive.py chi nhan anh da co phieu.
Write-Host ""
Write-Host "--- Phieu nhan trong _control ---" -ForegroundColor Yellow
$control = Join-Path $Root '_control'
if (Test-Path $control) {
  foreach ($nhanh in Get-ChildItem $control -Directory -ErrorAction SilentlyContinue) {
    $soPhieu = (Get-ChildItem (Join-Path $nhanh.FullName '.receipts') -Filter *.json -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "    $($nhanh.Name): $soPhieu phieu"
  }
  Write-Host "    (0 phieu o moi nhanh nghia la derive.py se coi nhu chua co anh nao)"
} else {
  Write-Host "    CHUA CO $control" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- Dung luong ---" -ForegroundColor Yellow
$goi = Join-Path $Root 'VN_NTL_Panel_2004_2025'
if (Test-Path $goi) {
  $gb = [math]::Round((Get-ChildItem $goi -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1GB, 2)
  Write-Host "    VN_NTL_Panel_2004_2025: $gb GB"
}
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Name -eq $Root.Substring(0,1) } |
  ForEach-Object { Write-Host ("    O {0}: con trong {1:n1} GB" -f $_.Name, ($_.Free/1GB)) }

Write-Host ""
Write-Host "Gui ket qua nay cho Claude de biet buoc tiep theo." -ForegroundColor Cyan
