# Kiểm kê dữ liệu — cập nhật 04/11/2026

Bảng này là căn cứ cho báo cáo tiến độ. Ô nào ghi *(cần đo)* thì chạy lệnh ở mục cuối
trên máy ảo rồi điền số thật vào — **không điền số ước lượng**.

## 1. Ảnh đã thu thập

| Nguồn | Giai đoạn | Độ phân giải | Trạng thái | Nơi lưu |
|---|---|---|---|---|
| Sentinel-2 | 2016–2025 | 10 m | ✅ xong, 10 VRT | máy ảo `/data/SatelliteData` |
| Sentinel-2 | 2015 | 10 m | ⚠️ chỉ có trên ổ E, chưa đưa lên máy ảo | `E:\SatelliteData` |
| Landsat 5/7/8/9 | 2004–2014 | 30 m | ✅ xong | `E:\SatelliteData` |
| VIIRS DNB | 2014–2025 | 500 m | ✅ xong | *(cần đo nơi lưu)* |
| DMSP-OLS | 2004–2013 | 1 km | ✅ xong | *(cần đo nơi lưu)* |
| GADM 4.1 | trước 01/7/2025 | cấp tỉnh | ✅ 63 tỉnh, đã kiểm SHA-256 | `province_pipeline/` |

Riêng Sentinel-2 2024: đã ghép thành một GeoTIFF quốc gia 24 GB
(81.534 × 167.100 điểm ảnh, WGS 84, 6 băng Int16, khối 512×512, nén ZSTD).

## 2. Ảnh đã cắt theo ranh giới tỉnh

| Năm | Trạng thái | Số file | Dung lượng |
|---|---|---|---|
| 2016 | ✅ xong | 63 | 22 GB |
| 2017–2025 | ❌ chưa | — | — |
| 2004–2015 | ❌ chưa | — | — |

Thời gian đo được: 2016 mất **2.625 giây** cho 63 tỉnh (một tiến trình).
Suy ra mỗi năm ≈ 45 phút; 22 năm ≈ 16 giờ nếu chạy tuần tự, ≈ 6 giờ nếu chạy 3 năm song song.

**Quy tắc bắt buộc:** một tiến trình cho mỗi năm. Hai tiến trình cùng một năm sẽ tranh
cùng tên file tạm `.clipping.tif` và làm hỏng kết quả (đã xảy ra thật).

## 3. Chỉ số

| Bảng | Trạng thái |
|---|---|
| `ntl_annual` (độ sáng, mật độ, biến động) | ❌ **chưa tính** — code có sẵn ở `derive.py`, chưa chạy |
| `day_indices_annual` (NDVI, NDBI, MNDWI, BSI + 6 băng) | ❌ **chưa tính** |
| Lớp phủ 5 lớp | ⛔ bị chặn: chỉ có 50 điểm mẫu, không đủ huấn luyện và kiểm định |
| Dân số, GDP | ⏳ chờ giảng viên cung cấp |

Hai file `VN_*_Panel_2004_2025/data_processed/*.csv` hiện chỉ là **khung 4 dòng mẫu**,
không phải số liệu thật. Đây là việc ưu tiên của tuần 2.

## 4. Hạ tầng

| Thành phần | Thông số |
|---|---|
| Máy ảo | `vngis-vm`, `asia-southeast1-b`, 4 vCPU, 16 GB RAM |
| Ổ dữ liệu | `/dev/sdb` → `/data`, 492 GB; đã dùng 274 GB, còn 218 GB |
| Ổ ngoài | `E:\SatelliteData`, còn ~815 GB |
| Earth Engine | 10 tài khoản × 10 project, hạn mức phi thương mại |
| Thông lượng tải tối ưu | `WORKERS=2` → 72–94 ô/giờ (so với 43–49 khi `WORKERS=1`), 0 lỗi |

## 5. Ứng dụng

| Thành phần | Trạng thái |
|---|---|
| API FastAPI (`app/api/`) | ✅ chạy được, 10 test pass |
| Giao diện (`app/web/`) | ✅ bản đồ, chọn tỉnh, 3 biểu đồ, nút Export |
| Thư viện trình duyệt | ✅ đóng gói trong repo (`app/web/vendor/`), không phụ thuộc CDN |
| Ranh giới cho bản đồ | ❌ chưa sinh — chạy `build_boundaries.py` trên máy có GADM |
| COG ảnh nền | ❌ chưa sinh — chạy `build_cogs.py` trên máy có `gdal-bin` |
| Dữ liệu hiển thị | ⚠️ đang là **số giả lập có nhãn đỏ**, 5 tỉnh |
| Triển khai công khai | ❌ chưa |

## Lệnh để đo và điền số thật

Chạy trên máy ảo, dưới user `adt_wqiqc`:

```bash
# Ảnh đêm đã có những năm nào
ls -1 /data/SatelliteData/VN_NTL_Panel_2004_2025/raw_data/NTL/VIIRS/ | head -40
ls -1 /data/SatelliteData/VN_NTL_Panel_2004_2025/raw_data/NTL/DMSP/  | head -40

# Dung lượng từng gói
du -sh /data/SatelliteData/VN_*_Panel_2004_2025/raw_data/*

# Số ô ảnh ngày theo năm
for y in $(seq 2004 2025); do printf "%s " "$y"; \
  find /data/SatelliteData -name "*_${y}_*.tif" | wc -l; done

# Ảnh đã cắt theo tỉnh
du -sh /data/SatelliteData/*/data_intermediate/annual_province/* 2>/dev/null

# Dung lượng ổ
df -h /data
```

Sau khi tính chỉ số xong, kiểm kê bằng chính API:

```bash
python3 -m app.data.build_indices --root /data/SatelliteData
curl -s localhost:8000/api/coverage | python3 -m json.tool
```
