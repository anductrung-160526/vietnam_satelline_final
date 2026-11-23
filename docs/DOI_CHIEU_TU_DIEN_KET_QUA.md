# Kết quả đối chiếu hai màn chỉ số đêm với Night Data Dictionary

Chạy ngày 23/11/2026 bằng `scripts/doi_chieu_tu_dien.py`, chuẩn tham chiếu là
`docs/NIGHT_DATA_DICTIONARY.md` (121 trường).

Công cụ hỏi thẳng API đang chạy chứ không đọc mã, vì màn Kinh tế đêm đã chuyển sang
`/api/demo/economy` trong khi `store.kinh_te_dem` vẫn còn trong mã nguồn và **không
ai gọi** — đọc mã thì đối chiếu nhầm đúng cái nhánh chết đó.

## Phải đọc trước: hai loại phát hiện, đừng trộn

| Loại | Phụ thuộc gì | Giá trị |
|---|---|---|
| **A. Lệch ở mã nguồn** | không phụ thuộc dữ liệu | đúng ở mọi máy, sửa được ngay |
| **B. Cột rỗng** | phụ thuộc chính cơ sở dữ liệu đang có | **chưa kết luận được** |

Cơ sở dữ liệu trên máy chạy kiểm này là **bộ giả lập tôi dựng hồi 16/11** (756 dòng
`ntl_annual`, `ntl_monthly` rỗng, `economy` toàn số `GIA_LAP`). Mọi dòng "TOÀN NULL"
ở mục B **không nói gì về dữ liệu thật của anh**. Phải chạy lại trên máy có
`E:\SatelliteData` mới kết luận được.

---

## A. Lệch ở mã nguồn — bốn điểm

### A1. `sol_density_cal` — từ điển CẤM, app vẫn bày ra

Dòng `sol_density` trong từ điển, cột storage ghi nguyên văn:

> CSV/SQLite/API; **không thêm field sol_density_cal vào dictionary**

Nhưng `/api/indicators` vẫn trả `sol_density_cal` ("Mật độ sáng (đã hiệu chỉnh)") và
nó nằm trong bộ chọn chỉ số của màn Chỉ số đêm. Đây là điểm **mâu thuẫn trực tiếp**
với chuẩn, không phải chuyện đặt tên.

Từ điển giải quyết bằng `light_basis`: chỉ có **một** tên `sol_density`, còn mẫu số
dùng `sol` hay `sol_cal` thì ghi ở `light_basis`. Hai cột riêng là cách làm cũ.

### A2. `sol_change_cal_pct` — không có trong từ điển

Không xuất hiện dưới bất kỳ dạng nào trong 121 trường. Cùng nhóm vấn đề với A1:
chuỗi đã hiệu chỉnh nên là một chế độ xem, không phải một bộ cột song song.

### A3. Bốn chỉ số ảnh ngày còn nằm trong màn Chỉ số đêm

`NDVI_mean`, `NDBI_mean`, `MNDWI_mean`, `BSI_mean` — không có trong từ điển đêm, và
**không có cột nào trong cơ sở dữ liệu**. Người dùng tick vào là nhận bảng trắng.

Đây chính là thứ tôi đã nêu hôm 16/11 và chờ anh quyết. Nay có thêm căn cứ: phạm vi
đã thu về chỉ còn kinh tế đêm, và từ điển đêm không định nghĩa chúng.

### A4. Cùng một đại lượng, hai tên trên cùng một màn hình

Hai khung của màn Chỉ số đêm gọi khác nhau:

| Khung "Bảng" | Khung "Chi tiết" | Từ điển |
|---|---|---|
| `rad_mean` | `mean_rad` | `mean_rad` (ghi rõ "SQLite rad_mean") |
| `rad_std` | `std_rad` | `std_rad` |
| `rad_max` | `max_rad` | `max_rad` |
| `rad_cv` | `spatial_cv` | `spatial_cv` |
| `lit_sol` | `lit_pop_proxy` | `lit_pop_proxy` |
| `valid_pixels` | `total_pixels` | `total_pixels` |
| `lit_pixel_pct` | `electrification_ratio_pct` | `electrification_ratio_pct` |

**Không phải lỗi hợp đồng** — từ điển có khai các tên SQLite này là bí danh hợp lệ,
và `demo_view.FIELD_ALIASES` ánh xạ đúng. Nhưng người dùng bấm qua lại hai khung của
**cùng một tab** sẽ thấy hai bộ tên cho cùng một đại lượng. Nên chọn một bộ để hiển
thị, giữ bộ kia ở tầng lưu trữ.

### A5. Trường API không có trong từ điển (nhẹ)

Màn Kinh tế đêm trả thêm `is_simulated`, `missing_reason`, `provenance_reason`,
`sol_unit`, và khối hồi quy có `canh_bao`, `theo_tinh`. Đây là trường kỹ thuật của
API, không phải chỉ số. Hai cái **có hiện lên màn hình** là `is_simulated` (nhãn
"SỐ GIẢ LẬP") và `missing_reason` (tooltip ô trống), nên đáng bổ sung vào từ điển.
`theo_tinh` là β riêng từng tỉnh — từ điển chỉ định nghĩa `beta` của mô hình chung,
và ghi rõ `light_gdp_elasticity` là **thứ khác** với β hồi quy.

---

## B. Cột rỗng trên cơ sở dữ liệu đang có

Nhắc lại: bộ dữ liệu này là số giả lập, nên danh sách dưới đây **chỉ là cách chạy
kiểm**, không phải kết luận về dữ liệu thật.

Màn Chỉ số đêm, khung Bảng: `sol_cal`, `sol_raw`, `rad_max`, `rad_std`, `lit_pixels`,
`lit_sol`, `lit_pixel_pct`, `cloud_free_obs`, `gdp` — toàn NULL.
Khung Chi tiết thêm: `background_threshold`, `background_pixels`, `lit_threshold`.
`sol_ma3`, `sol_change_mom_pct`, `sol_change_yoy_pct` — bảng `ntl_monthly` rỗng.

Chạy trên máy anh:

```
python -m uvicorn backend.api.main:app --port 8000
python scripts\doi_chieu_tu_dien.py --nam 2024
```

Cột nào vẫn TOÀN NULL ở đó mới là việc phải xử lý.

---

## Một điểm về phương pháp, cần chú ý

Từ điển phân biệt rõ hai thứ mà tên gọi dễ làm lẫn:

- `light_gdp_elasticity` = **tỷ số % tăng trưởng** ánh sáng trên GRDP giữa hai năm
  liền nhau. Từ điển ghi thẳng: *"khác β hồi quy"*.
- `beta` = độ co giãn trong mô hình **log–log** `ln(GRDP) = α + β·ln(SOL)`.

Màn Kinh tế đêm hiện **cả hai**: ô hồi quy hiện `beta`, cột "Δ sáng / Δ GRDP" hiện
`light_gdp_elasticity`. Đúng chuẩn. Nhưng khi viết báo cáo cho cô thì tuyệt đối
không được gọi chung là "độ co giãn" rồi trích lẫn số của nhau.

---

## Việc cần quyết

1. **A1 + A2** — gỡ `sol_density_cal` và `sol_change_cal_pct` khỏi bộ chọn, chuyển
   sang cơ chế `light_basis` như từ điển quy định? Hay sửa từ điển?
2. **A3** — gỡ bốn chỉ số ảnh ngày khỏi màn Chỉ số đêm?
3. **A4** — chọn một bộ tên để hiển thị. Đề xuất: dùng tên từ điển ở cả hai khung,
   vì từ điển là thứ cô cầm khi đọc bảng.
4. **A5** — bổ sung `is_simulated` và `missing_reason` vào từ điển.
5. Dọn `store.kinh_te_dem` và `/api/kinh-te-dem` nếu đã chắc không còn ai gọi.

Tôi chưa sửa gì. Năm việc trên đều đụng vào hợp đồng dữ liệu hoặc phạm vi đã chốt
với cô, không phải việc tự quyết.
