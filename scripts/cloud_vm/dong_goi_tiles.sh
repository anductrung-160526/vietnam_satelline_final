#!/usr/bin/env bash
# Đóng gói TILES trên máy ảo rồi đẩy lên Cloud Storage, để tải về ổ E.
#
#   bash scripts/cloud_vm/dong_goi_tiles.sh --kiem-ke
#   bash scripts/cloud_vm/dong_goi_tiles.sh --nam 2016 --bucket gs://vngis-transfer-2024
#
# CHỈ lấy thư mục tiles/ và file .vrt. KHÔNG lấy ảnh ghép VN_<SẢN PHẨM>_<năm>.tif
# (mỗi file 24 GB, và ghép lại được từ chính các tile này bất cứ lúc nào).
#
# Gửi kèm .sha256 và .manifest để máy Windows kiểm tra được gói có nguyên vẹn không —
# ổ E của dự án này đã rớt kết nối giữa chừng ba lần.
set -euo pipefail

ROOT=${ROOT:-/data/SatelliteData}
BUCKET=""
NAM=""
SAN_PHAM=${SAN_PHAM:-}
KIEM_KE=0
GIU_LAI=0
TAT_CA=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root)     ROOT=$2; shift 2 ;;
    --nam)      NAM=$2; shift 2 ;;
    --bucket)   BUCKET=$2; shift 2 ;;
    --san-pham) SAN_PHAM=$2; shift 2 ;;
    --kiem-ke)  KIEM_KE=1; shift ;;
    --tat-ca)   TAT_CA=1; shift ;;
    --giu-lai)  GIU_LAI=1; shift ;;   # giữ file .tar trên máy ảo sau khi đẩy lên
    *) echo "Tham số lạ: $1" >&2; exit 2 ;;
  esac
done

# Tìm mọi thư mục năm có tiles, dạng .../<SẢN PHẨM>/VN_<SẢN PHẨM>_<năm>/tiles
thu_muc_nam() {
  find "$ROOT" -type d -name 'tiles' -path '*/raw_data/*' 2>/dev/null | sort | while read -r t; do
    dirname "$t"
  done
}

# Làm lần lượt mọi năm trong một lượt chạy. Dùng trong tmux để không phải ngồi canh:
# tile đã nén ZSTD sẵn nên bước tar chỉ là gộp file, phần lâu là đẩy lên bucket.
if [ "$TAT_CA" = 1 ]; then
  [ -n "$BUCKET" ] || { echo "Thiếu --bucket" >&2; exit 2; }
  mapfile -t cac_nam < <(thu_muc_nam | grep -oE '[0-9]{4}$' | sort -u)
  echo "=== Đóng gói ${#cac_nam[@]} năm: ${cac_nam[*]} ==="
  bat_dau=$(date +%s)
  for y in "${cac_nam[@]}"; do
    echo
    echo "########## $y ##########"
    # Chuyển tiếp mọi cờ: thiếu --giu-lai ở đây thì cờ đó im lặng không có tác dụng.
    if ! bash "$0" --root "$ROOT" --nam "$y" --bucket "$BUCKET" \
         ${SAN_PHAM:+--san-pham "$SAN_PHAM"} $([ "$GIU_LAI" = 1 ] && echo --giu-lai); then
      echo "  $y HỎNG — bỏ qua, làm tiếp năm sau." >&2
    fi
  done
  echo
  echo "Tổng thời gian: $(( ($(date +%s) - bat_dau) / 60 )) phút"
  echo "Các gói đang nằm ở $BUCKET. Trên máy Windows chạy:"
  echo "  powershell -ExecutionPolicy Bypass -File scripts\\windows\\tai_tiles_ve_o_E.ps1 -TatCa -Bucket $BUCKET"
  exit 0
fi

if [ "$KIEM_KE" = 1 ] || [ -z "$NAM" ]; then
  echo "=== Kiểm kê tiles trong $ROOT ==="
  printf '%-14s %-6s %10s %10s  %s\n' "SẢN PHẨM" "NĂM" "SỐ TILE" "DUNG LƯỢNG" "ẢNH GHÉP .tif"
  tong=0
  while read -r folder; do
    [ -z "$folder" ] && continue
    ten=$(basename "$folder")                 # VN_SENTINEL2_2016
    sp=$(echo "$ten" | sed -E 's/^VN_(.+)_[0-9]{4}$/\1/')
    nam=$(echo "$ten" | grep -oE '[0-9]{4}$')
    so=$(find "$folder/tiles" -type f -name '*.tif' | wc -l)
    dl=$(du -sb "$folder/tiles" 2>/dev/null | cut -f1)
    ghep="-"
    [ -f "$folder/VN_${sp}_${nam}.tif" ] && ghep=$(du -h "$folder/VN_${sp}_${nam}.tif" | cut -f1)
    printf '%-14s %-6s %10s %10s  %s\n' "$sp" "$nam" "$so" "$(numfmt --to=iec "$dl")" "$ghep"
    tong=$((tong + dl))
  done < <(thu_muc_nam)
  echo
  echo "Tổng dung lượng tiles: $(numfmt --to=iec "$tong")"
  echo "Còn trống trên $ROOT: $(df -h "$ROOT" | awk 'NR==2{print $4}')"
  echo
  echo "Đóng gói một năm:   bash $0 --nam 2016 --bucket gs://<tên bucket>"
  echo "Đóng gói mọi năm:   bash $0 --tat-ca --bucket gs://<tên bucket>"
  exit 0
fi

[ -n "$BUCKET" ] || { echo "Thiếu --bucket gs://<tên bucket>" >&2; exit 2; }

# Chọn đúng thư mục của năm được yêu cầu
mapfile -t ung_vien < <(thu_muc_nam | grep -E "_${NAM}$" || true)
if [ -n "$SAN_PHAM" ]; then
  mapfile -t ung_vien < <(printf '%s\n' "${ung_vien[@]}" | grep -E "/VN_${SAN_PHAM}_${NAM}$" || true)
fi
[ "${#ung_vien[@]}" -gt 0 ] || { echo "Không thấy tiles của năm $NAM dưới $ROOT" >&2; exit 1; }

for folder in "${ung_vien[@]}"; do
  ten=$(basename "$folder")
  sp=$(echo "$ten" | sed -E 's/^VN_(.+)_[0-9]{4}$/\1/')
  tuong_doi=${folder#"$ROOT"/}              # VN_..._Panel.../raw_data/DAY/SENTINEL2/VN_SENTINEL2_2016
  cha=$(dirname "$folder")
  so_tile=$(find "$folder/tiles" -type f -name '*.tif' | wc -l)
  can=$(du -sb "$folder/tiles" | cut -f1)
  trong=$(df -B1 --output=avail "$ROOT" | tail -1)

  echo "=== $ten ==="
  echo "  $so_tile tile · $(numfmt --to=iec "$can")"
  if [ "$trong" -lt "$((can + 1073741824))" ]; then
    echo "  KHÔNG ĐỦ CHỖ: cần $(numfmt --to=iec "$can") + 1 GB, còn $(numfmt --to=iec "$trong")." >&2
    echo "  Xoá bớt ảnh ghép .tif rồi chạy lại, hoặc làm từng năm một." >&2
    exit 1
  fi

  tar_path="$ROOT/tiles_${sp}_${NAM}.tar"
  echo "  Đóng gói (chỉ tiles/ và .vrt, không lấy ảnh ghép)…"
  tar -cf "$tar_path" -C "$cha" "$ten/tiles" \
      $([ -f "$folder/VN_${sp}_${NAM}.vrt" ] && echo "$ten/VN_${sp}_${NAM}.vrt")

  echo "  Tính SHA-256…"
  sha=$(sha256sum "$tar_path" | cut -d' ' -f1)
  printf '%s  %s\n' "$sha" "$(basename "$tar_path")" > "$tar_path.sha256"
  {
    echo "goi=$(basename "$tar_path")"
    echo "san_pham=$sp"
    echo "nam=$NAM"
    echo "so_tile=$so_tile"
    echo "duong_dan_giai_nen=$(dirname "$tuong_doi")"
    echo "sha256=$sha"
  } > "$tar_path.manifest"

  echo "  Đẩy lên $BUCKET …"
  gcloud storage cp "$tar_path" "$tar_path.sha256" "$tar_path.manifest" "$BUCKET/"

  if [ "$GIU_LAI" = 0 ]; then
    rm -f "$tar_path" "$tar_path.sha256" "$tar_path.manifest"
    echo "  Đã xoá bản tạm trên máy ảo."
  fi
  echo "  XONG: $(basename "$tar_path") · $so_tile tile · sha256 ${sha:0:12}…"
done

echo
echo "Trên máy Windows, cắm ổ E rồi chạy:"
echo "  powershell -ExecutionPolicy Bypass -File scripts\\windows\\tai_tiles_ve_o_E.ps1 -Nam $NAM -Bucket $BUCKET"
