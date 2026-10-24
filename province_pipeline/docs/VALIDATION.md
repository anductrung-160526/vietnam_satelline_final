# Validation và giới hạn bàn giao

## Đã kiểm tra trong Linux cloud

- Suite unittest gồm regression cũ và test mới cho quota/reservation, nhóm tỉnh, paths, resume submit, receipt ordering, checksum, local corruption, ổ đầy, mất nguồn sau delete và aggregate CSV/XLSX/DTA.
- Agent được kiểm tra bằng Drive giả lập; không dùng kết quả mock như bằng chứng Google API thật hoạt động.
- Kiểm tra TIFF synthetic đúng lưới/CRS/bands/nodata, đọc mọi block; không phải ảnh vệ tinh thật.
- Boundary fixture synthetic dùng trong test kiểm tra schema/hash/tile jobs, không được sử dụng như ranh giới sản xuất.

Lệnh tái hiện:

```bash
python -m pip install -r province_pipeline/requirements.txt
python -m pip check
python -m unittest discover -s tests -v
python -m province_pipeline --help
```

## Chưa được kiểm tra, không tuyên bố hoàn tất pilot thật

1. Earth Engine compute/export và việc Earth Engine phân giải đúng leaf folder đã tạo trên Drive.
2. Quota thực tế, quyền sở hữu file, refresh token lâu dài, HTTP ETag và conditional permanent delete trên tài khoản người dùng.
3. Bộ ranh giới 63 tỉnh chính xác về nguồn/crosswalk/diện tích.
4. Windows Task Scheduler, volume identity và tải/xóa trên ổ E thật.
5. Độ chính xác khoa học của NTL, bộ lọc transient light, phân loại đất và harmonization.

Cấu hình mặc định pause=true, allow_remote_delete=false, chỉ chọn Hà Nội 2024. Không tự tải toàn quốc hoặc xóa dữ liệu Drive trong lúc phát triển. Chạy pilot theo SETUP_VI.md trước khi bật xóa và mở rộng.
