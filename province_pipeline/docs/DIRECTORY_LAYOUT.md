# Cấu trúc package theo đề bài — layout 3

Cùng một cây dữ liệu áp dụng cho Drive staging và ổ E. Package đứng trước; thư mục
mã+tên tỉnh là con trực tiếp của DMSP, VIIRS, LANDSAT, SENTINEL2,
data_intermediate và data_processed. Không có thư mục tỉnh bọc ngoài package,
không có thư mục theo job ID trong layout direct mới.

```text
SatelliteStaging/                      # Hoặc E:\SatelliteData\
├── VN_NTL_Panel_2004_2025/
│   ├── README.md                      # Sinh khi aggregate local
│   ├── raw_data/NTL/
│   │   ├── DMSP/01_ha_noi/*.tif
│   │   └── VIIRS/01_ha_noi/*.tif
│   ├── data_intermediate/01_ha_noi/*.tif
│   ├── data_processed/
│   │   ├── 01_ha_noi/
│   │   │   ├── source/VIIRS_MONTHLY/*.csv
│   │   │   └── panels/*.{csv,xlsx,dta}
│   │   └── <bảng toàn quốc theo nguồn và recipe>.{csv,xlsx,dta}
│   ├── metadata/
│   ├── code/
│   ├── dashboard/                     # Dành chỗ, chưa triển khai
│   ├── docs/
│   └── logs/
├── VN_LandCover_Panel_2004_2025/
│   ├── README.md
│   ├── raw_data/DAY/
│   │   ├── LANDSAT/01_ha_noi/*.tif
│   │   └── SENTINEL2/01_ha_noi/*.tif
│   ├── data_intermediate/01_ha_noi/    # Khi có sản phẩm trung gian
│   ├── data_processed/
│   │   ├── 01_ha_noi/
│   │   │   ├── source/LANDSAT/*.csv
│   │   │   └── panels/*.{csv,xlsx,dta}
│   │   └── <bảng toàn quốc theo nguồn và recipe>.{csv,xlsx,dta}
│   ├── metadata/
│   ├── samples/
│   ├── code/
│   ├── dashboard/                     # Dành chỗ, chưa triển khai
│   ├── docs/
│   └── logs/
└── _control/                          # Chỉ Drive: trạng thái vận hành
```

Trên E có thêm .manifests/.receipts để kiểm tra dữ liệu, không phải dữ liệu khoa học.
Ảnh TIFF nằm trực tiếp trong thư mục tỉnh, không có thư mục năm/tháng hoặc nguồn ở dưới tỉnh. Năm/tháng, nguồn, biến thể xử lý và ô ảnh được phân biệt trong tên tệp. Thư mục dữ liệu bảng không đổi trong lần chỉnh này. Tên tỉnh còn xuất hiện trong tên TIFF/CSV để vẫn nhận diện được khi tách file.
Bảng toàn quốc là FILE ở gốc data_processed; các FOLDER tỉnh nằm trực tiếp dưới nó.

Đây là thay đổi tổ chức lưu trữ, không thay thuật toán/lưới/nguồn ảnh. Job ID và tên
file cũ được giữ để không tải lại dữ liệu chỉ vì thay cấu trúc. Code/docs/logs có vị
trí theo PDF; việc hoàn thiện nội dung tài liệu/đóng gói code/log không được suy ra
chỉ từ sự tồn tại của các thư mục. Phân loại đất và dashboard vẫn hoãn.

## Áp dụng trên Drive đã có dữ liệu

1. Đặt `pause=true` trong PROVINCE_CONFIG_JSON. Đợi mọi lượt run đang chạy kết thúc;
   dừng Windows receiver nếu đã cài.
2. Merge PR từ inspriring-newton vào main trước khi bật lại lịch. Không để code main
   cũ và code layout 3 cùng vận hành trên một staging root.
3. Actions → Province satellite staging → Run workflow → branch main (sau merge),
   mode **organize_only**. Chế độ này yêu cầu pause=true.
4. Controller chỉ sắp xếp output đã có manifest kiểm tra, được state nhận diện bằng
   đúng file ID. Giữ nguyên bytes, MD5 và file ID, cập nhật parent/version/manifest.
   Job chưa chạy và chưa có output chỉ được đổi folder đích, không tải lại ảnh.
5. Khi hoàn tất, tìm `layout_organized`: changed_jobs, skipped_jobs, deleted_files=0.
   Nếu còn lỗi migration, giữ pause và chạy lại organize_only; ý định chuyển file
   đã lưu trước khi move nên có thể tiếp tục sau khi mất phản hồi.
6. Kiểm tra hai package trên Drive, sau đó đặt pause=false và chạy mode run.

Không xóa file, folder rỗng cũ hoặc dữ liệu ngoài manifest. Nếu folder tỉnh cũ còn
rỗng ở gốc Drive, giữ lại để người dùng tự kiểm tra/dọn; chúng không được dùng cho
output mới. Lô FAILED/BLOCKED_OUTPUT hoặc upload chưa xác minh được bỏ qua và báo
skipped_jobs, không di chuyển bừa. Chuyển parent là thao tác Drive API, không tải
TIFF về runner rồi upload lại; quota dữ liệu không bị nhân đôi.

## Tương thích với dữ liệu đã có trên E

Receiver mới ánh xạ cả manifest cũ sang layout mới. Nếu bản đã tải theo đường dẫn
cũ còn đúng checksum/receipt, nó được đổi đường dẫn trong cùng volume rồi cập
nhật receipt, không tải lại. Nếu đường dẫn đích có dữ liệu khác, thao tác bị chặn.
Không ghi đè tệp không khớp. Local paths vẫn phải qua kiểm tra chống traversal.

Với các lô đã nhận xong và thậm chí đã xóa nguồn Drive trước khi nâng cấp:

```powershell
python -m province_pipeline --config province_pipeline/config/local.json organize-local
python -m province_pipeline --config province_pipeline/config/local.json aggregate
```

Hai lệnh cần đúng marker/serial ổ ngoài và khóa receiver độc quyền. Khi có đủ
manifest/receipt, dữ liệu local được kiểm tra và chuyển sang vị trí chuẩn ngay cả
khi nguồn Drive không còn. Nếu thiếu/sai checksum, dừng và giữ nguyên nguồn local.
Bảng tổng hợp mới được ghi ở vị trí mới; bảng tổng hợp cũ ở data_processed/panels
không bị tự xóa.

## Bỏ thư mục năm/tháng (layout 3)

Ví dụ ảnh Landsat: `raw_data/DAY/LANDSAT/01_ha_noi/01_ha_noi_LANDSAT_2024_composite_664_171_v001.tif`.
VIIRS tháng 01 và 02 cùng ở `raw_data/NTL/VIIRS/01_ha_noi/`, có `2024-01` hoặc `2024-02` trong tên tệp. Ảnh trung gian cũng nằm trực tiếp tại `data_intermediate/01_ha_noi/`.

Mode organize_only xử lý được cả lô cũ trước layout 2 và lô đã có thư mục năm/tháng của layout 2. Nếu một lần chuyển layout 2 bị ngắt trước khi nâng cấp mã, chương trình hoàn tất đúng đích cũ rồi chuyển tiếp sang layout 3; không gắn nhãn mới cho dữ liệu chưa chuyển đúng nơi. Giữ nguyên file ID, checksum, job ID và tên tệp; không tải lại ảnh chỉ vì bỏ thư mục thời gian. Các thư mục năm/tháng cũ rỗng không bị tự xóa.
