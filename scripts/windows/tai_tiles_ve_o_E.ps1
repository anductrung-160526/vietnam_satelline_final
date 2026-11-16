# Tai goi tiles tu Cloud Storage ve o E va giai nen dung cho.
# File nay chi dung ky tu ASCII: PowerShell 5.1 doc file UTF-8 khong BOM
# theo bang ma ANSI, nen dau tieng Viet se thanh ky tu rac va vo cu phap.
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows\tai_tiles_ve_o_E.ps1 -Nam 2016 -Bucket gs://vngis-transfer-2024
#   powershell -ExecutionPolicy Bypass -File scripts\windows\tai_tiles_ve_o_E.ps1 -LietKe -Bucket gs://vngis-transfer-2024
#
# Goi do scripts/cloud_vm/dong_goi_tiles.sh tao ra, chi chua tiles/ va .vrt.
# Script kiem SHA-256 truoc khi giai nen va dem so tile sau khi giai nen.
# O E cua du an nay da rot ket noi giua chung ba lan, nen buoc kiem tra la bat buoc.

param(
  [string]$Nam = "",
  [Parameter(Mandatory=$true)][string]$Bucket,
  [string]$Root = 'E:\SatelliteData',
  [string]$TamThoi = 'C:\Users\AD\vngis_tam',
  [switch]$LietKe,
  [switch]$TatCa,           # tai lan luot moi nam dang co tren bucket
  [int]$SoLuong = 16,       # so manh tai song song cho moi goi
  [switch]$GiuGoi,          # giu file .tar sau khi giai nen
  [switch]$XoaTrenBucket    # xoa goi khoi bucket sau khi kiem tra xong
)

# 'Stop' khong dung duoc o day: gcloud va tar in tien trinh ra stderr, va voi 'Stop'
# PowerShell coi moi dong stderr cua lenh ngoai la loi nghiem trong roi dung script
# giua chung du lenh chay thanh cong. Thay vao do kiem $LASTEXITCODE sau tung lenh.
$ErrorActionPreference = 'Continue'

function Dung-Lai($thong_diep) {
  Write-Host ""
  Write-Host "LOI: $thong_diep" -ForegroundColor Red
  exit 1
}

# Tile da nen ZSTD muc 9 san nen khong nen them duoc nua; cach duy nhat de nhanh hon
# la dung nhieu luong hon tren duong truyen. gcloud chia mot file lon thanh nhieu manh
# tai song song - mac dinh 4 manh, nang len giup bao hoa duong truyen tot hon.
# Dat bang bien moi truong thay vi 'gcloud config set': khong sua cau hinh toan cuc
# cua may, va khong in gi ra stderr.
function Dat-SongSong($n) {
  $env:CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_MAX_COMPONENTS = "$n"
  $env:CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_THRESHOLD = "64MiB"
  $env:CLOUDSDK_STORAGE_PROCESS_COUNT = "8"
  $env:CLOUDSDK_STORAGE_THREAD_COUNT = "8"
}

function Doc-Manifest($path) {
  $d = @{}
  foreach ($line in Get-Content $path) {
    if ($line -match '^\s*([a-z0-9_]+)=(.*)$') { $d[$matches[1]] = $matches[2].Trim() }
  }
  return $d
}

if ($LietKe) {
  Write-Host "=== Cac goi dang co tren $Bucket ===" -ForegroundColor Cyan
  & gcloud storage ls -l "$Bucket/tiles_*.tar"
  exit 0
}

if ($TatCa) {
  # Lay danh sach nam tu chinh bucket, roi goi lai script nay cho tung nam.
  $ds = & gcloud storage ls "$Bucket/tiles_*.tar"
  $nams = $ds | ForEach-Object { if ($_ -match 'tiles_.+_(\d{4})\.tar$') { $matches[1] } } |
          Sort-Object -Unique
  if (-not $nams) { Dung-Lai "Khong thay goi nao tren $Bucket. Chay dong_goi_tiles.sh tren may ao truoc." }
  Write-Host "=== Se tai $($nams.Count) nam: $($nams -join ', ') ===" -ForegroundColor Cyan
  $batDau = Get-Date
  $hong = @()
  foreach ($y in $nams) {
    Write-Host ""
    Write-Host "########## $y ##########" -ForegroundColor Cyan
    $t = Get-Date
    & $PSCommandPath -Nam $y -Bucket $Bucket -Root $Root -TamThoi $TamThoi `
        -SoLuong $SoLuong @{$true=@('-GiuGoi')}[[bool]$GiuGoi] 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) { $hong += $y; Write-Host "    $y HONG" -ForegroundColor Red }
    else { Write-Host ("    $y xong sau {0:n0} phut" -f ((Get-Date)-$t).TotalMinutes) -ForegroundColor Green }
  }
  Write-Host ""
  Write-Host ("Tong thoi gian: {0:n0} phut" -f ((Get-Date)-$batDau).TotalMinutes) -ForegroundColor Cyan
  if ($hong.Count) { Write-Host "Nam bi loi: $($hong -join ', ') - chay lai rieng tung nam." -ForegroundColor Red }
  exit 0
}

if (-not $Nam) { Dung-Lai "Thieu -Nam. Vi du: -Nam 2016. Hoac -TatCa de tai het, -LietKe de xem co nhung goi nao." }
if (-not (Test-Path $Root)) {
  Write-Host "KHONG THAY $Root - o cung chua duoc cam?" -ForegroundColor Red
  Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{n='Trong(GB)';e={[math]::Round($_.Free/1GB,1)}} | Format-Table
  exit 1
}
New-Item -ItemType Directory -Force -Path $TamThoi | Out-Null

# Tai ve o C: truoc roi moi giai nen sang E:. Tai thang vao o USB de rot giua chung
# la mat ca goi; tai ve o trong may thi chi phai giai nen lai.
Write-Host "=== Tai goi nam $Nam ===" -ForegroundColor Cyan
Write-Host "    Trung chuyen qua: $TamThoi"
Dat-SongSong $SoLuong
$dongHo = Get-Date
& gcloud storage cp "$Bucket/tiles_*_$Nam.tar" "$Bucket/tiles_*_$Nam.tar.sha256" "$Bucket/tiles_*_$Nam.tar.manifest" $TamThoi
if ($LASTEXITCODE -ne 0) { Dung-Lai "Tai that bai. Chay lai lenh nay, gcloud se tiep tuc cho dang do." }

$goi = Get-ChildItem "$TamThoi\tiles_*_$Nam.tar"
if (-not $goi) { Dung-Lai "Khong thay goi nao cho nam $Nam trong $TamThoi" }

$tongByte = ($goi | Measure-Object Length -Sum).Sum
$giay = ((Get-Date) - $dongHo).TotalSeconds
if ($giay -gt 0) {
  Write-Host ("    Tai xong: {0:n2} GB trong {1:n0} giay = {2:n1} MB/s" -f `
    ($tongByte/1GB), $giay, ($tongByte/1MB/$giay)) -ForegroundColor Green
}

foreach ($tar in $goi) {
  Write-Host ""
  Write-Host "--- $($tar.Name) ---" -ForegroundColor Yellow
  $manifest = Doc-Manifest "$($tar.FullName).manifest"
  $mong_doi = $manifest['sha256']
  $so_tile_mong_doi = [int]$manifest['so_tile']
  $dich = Join-Path $Root $manifest['duong_dan_giai_nen']

  Write-Host "    Kiem SHA-256 ($([math]::Round($tar.Length/1GB,2)) GB)..."
  $that = (Get-FileHash $tar.FullName -Algorithm SHA256).Hash.ToLower()
  if ($that -ne $mong_doi) {
    Write-Host "    SAI MA BAM - goi hong tren duong truyen." -ForegroundColor Red
    Write-Host "      mong doi: $mong_doi"
    Write-Host "      nhan duoc: $that"
    Write-Host "    Xoa $($tar.Name) roi chay lai script." -ForegroundColor Red
    exit 1
  }
  Write-Host "    Ma bam khop." -ForegroundColor Green

  New-Item -ItemType Directory -Force -Path $dich | Out-Null
  Write-Host "    Giai nen vao $dich ..."
  & tar.exe -xf $tar.FullName -C $dich
  if ($LASTEXITCODE -ne 0) { Dung-Lai "Giai nen that bai. O E con du cho khong?" }

  $thu_muc = Join-Path $dich "VN_$($manifest['san_pham'])_$Nam"
  $so_that = (Get-ChildItem (Join-Path $thu_muc 'tiles') -Filter *.tif -File -ErrorAction SilentlyContinue | Measure-Object).Count
  if ($so_that -ne $so_tile_mong_doi) {
    Write-Host "    THIEU TILE: co $so_that, dang le $so_tile_mong_doi" -ForegroundColor Red
    exit 1
  }
  Write-Host "    $so_that tile - dung bang so tren may ao." -ForegroundColor Green

  $vrt = Join-Path $thu_muc "VN_$($manifest['san_pham'])_$Nam.vrt"
  if (Test-Path $vrt) {
    Write-Host "    Co san file ghep ao: $vrt" -ForegroundColor Green
    Write-Host "      Mo file nay trong QGIS la thay ca nam nhu mot anh duy nhat."
  }

  if (-not $GiuGoi) {
    Remove-Item $tar.FullName, "$($tar.FullName).sha256", "$($tar.FullName).manifest" -Force
    Write-Host "    Da xoa goi tam tren o C."
  }
  if ($XoaTrenBucket) {
    & gcloud storage rm "$Bucket/$($tar.Name)" "$Bucket/$($tar.Name).sha256" "$Bucket/$($tar.Name).manifest"
    Write-Host "    Da xoa goi tren bucket."
  }
}

Write-Host ""
Write-Host "XONG nam $Nam." -ForegroundColor Cyan
$free = (Get-PSDrive -Name $Root.Substring(0,1)).Free
Write-Host ("O {0}: con trong {1:n1} GB" -f $Root.Substring(0,1), ($free/1GB))
Write-Host "Lam nam tiep theo: doi -Nam 2017 roi chay lai."
