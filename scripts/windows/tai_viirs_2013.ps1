# Tai bu anh VIIRS nam 2013 cho du 63 tinh.
# File nay chi dung ky tu ASCII: PowerShell 5.1 doc file UTF-8 khong BOM
# theo bang ma ANSI, nen dau tieng Viet se thanh ky tu rac va vo cu phap.
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows\tai_viirs_2013.ps1
#
# VI SAO CAN: nam 2013 la nam duy nhat ca DMSP lan VIIRS cung hoat dong. Buoc hieu chinh
# lien ket (task_pipeline/harmonize.py) khop mo hinh tren chinh nam do va tu choi chay khi
# duoi 30 tinh co ca hai nguon. VIIRS 2013 KHONG vao chuoi chi so nam - nam 2013 van luon
# lay tu DMSP - no chi dung de hoc ra he so quy doi.
#
# --only night la BAT BUOC: thieu no thi run tu dong chay tiep sang anh ngay theo tinh
# theo thang (63 tinh x 22 nam x 12 thang), du de dot het han muc Earth Engine.
#
# Moi nhom tinh dung mot project Earth Engine rieng, nen phai doi profile dang nhap
# tuong ung truoc moi nhom (xem bang trong CLAUDE.md).

param(
  [string]$Root = 'E:\SatelliteData',
  [string]$Python = '',
  [switch]$ChiKiemTra,      # chi dem, khong tai
  [switch]$KhongDung        # chay het du co nhom loi
)

$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

if (-not $Python) {
  $Python = if (Test-Path '.\.venv\Scripts\python.exe') { (Resolve-Path '.\.venv\Scripts\python.exe').Path } else { 'python' }
}

# nhom tinh -> project Earth Engine -> thu muc profile dang nhap tren Windows
$NHOM = @(
  @{ Range='1-11';  Project='vngis-ee-2';                    Profile='' },
  @{ Range='12-22'; Project='vngis-ee-ha-tinh-lai-chau';     Profile='C:\ee-profiles\acc-ftu' },
  @{ Range='23-33'; Project='vngis-ee-soc-trang-yen-bai';    Profile='C:\ee-profiles\acc-quynhmai' },
  @{ Range='34-43'; Project='vngis-ee-cao-bang-hanoi';       Profile='C:\ee-profiles\acc-work' },
  @{ Range='44-53'; Project='vngis-ee-lam-dong-quang-tri';   Profile='C:\ee-profiles\acc-qec' },
  @{ Range='54-63'; Project='vgis-ee-6';                     Profile='C:\ee-profiles\acc-4usd' }
)

function Dem-2013 {
  $goc = Join-Path $Root 'VN_NTL_Panel_2004_2025\raw_data\NTL\VIIRS'
  if (-not (Test-Path $goc)) { return @{ Du=0; Thieu=63 } }
  $du = 0
  foreach ($t in Get-ChildItem $goc -Directory | Where-Object Name -match '^\d{2}_') {
    $n = (Get-ChildItem $t.FullName -Filter '*2013-*.tif' -File -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($n -ge 12) { $du++ }
  }
  return @{ Du=$du; Thieu=(63 - $du) }
}

$truoc = Dem-2013
Write-Host "=== VIIRS 2013 ===" -ForegroundColor Cyan
Write-Host ("Truoc khi chay: {0}/63 tinh du 12 thang, thieu {1} tinh" -f $truoc.Du, $truoc.Thieu)
Write-Host "Buoc hieu chinh can toi thieu 30 tinh."

if ($ChiKiemTra) { exit 0 }
if ($truoc.Du -ge 63) { Write-Host "Da du ca 63 tinh, khong can tai." -ForegroundColor Green; exit 0 }

$batDau = Get-Date
$hong = @()
$dau = $true
foreach ($n in $NHOM) {
  Write-Host ""
  Write-Host ("--- Nhom {0} | project {1} ---" -f $n.Range, $n.Project) -ForegroundColor Yellow
  if ($n.Profile) {
    if (-not (Test-Path $n.Profile)) {
      Write-Host ("    KHONG THAY profile {0}" -f $n.Profile) -ForegroundColor Red
      Write-Host "    Xem muc 4.2 trong task_pipeline/SETUP_LUONG_GEE_VI.md de tao va dang nhap."
      $hong += $n.Range; continue
    }
    $env:USERPROFILE = $n.Profile
    Write-Host ("    profile: {0}" -f $n.Profile)
  } else {
    $env:USERPROFILE = "C:\Users\$env:USERNAME"
    Write-Host "    profile: mac dinh cua may"
  }

  $t = Get-Date
  & $Python -m task_pipeline.local run --mode full --range $n.Range --root $Root --start night --only night
  if ($LASTEXITCODE -ne 0) {
    Write-Host ("    HONG (ma loi {0})" -f $LASTEXITCODE) -ForegroundColor Red
    $hong += $n.Range
    if ($dau -and -not $KhongDung) {
      Write-Host ""
      Write-Host "Nhom dau tien hong -> nhieu kha nang la loi dang nhap Earth Engine." -ForegroundColor Red
      Write-Host "Kiem tra:  $Python -m task_pipeline.local authenticate --project $($n.Project)"
      Write-Host "Muon chay het du co loi thi them: -KhongDung"
      exit 1
    }
  } else {
    Write-Host ("    xong sau {0:n0} phut" -f ((Get-Date) - $t).TotalMinutes) -ForegroundColor Green
  }
  $dau = $false
}

$sau = Dem-2013
Write-Host ""
Write-Host "=== Ket qua ===" -ForegroundColor Cyan
Write-Host ("Tong thoi gian: {0:n0} phut" -f ((Get-Date) - $batDau).TotalMinutes)
Write-Host ("VIIRS 2013: {0}/63 tinh du (truoc khi chay: {1})" -f $sau.Du, $truoc.Du)
if ($hong.Count) { Write-Host ("Nhom bi loi: {0}" -f ($hong -join ', ')) -ForegroundColor Red }

if ($sau.Du -ge 30) {
  Write-Host "Du dieu kien hieu chinh. Buoc tiep theo:" -ForegroundColor Green
  Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\windows\chi_so_dem.ps1"
  Write-Host "  $Python -m app.data.build_indices --root $Root"
} else {
  Write-Host ("Van chua du 30 tinh ({0}). Buoc hieu chinh se tu choi chay." -f $sau.Du) -ForegroundColor Red
}
