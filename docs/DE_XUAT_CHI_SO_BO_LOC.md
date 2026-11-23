# Đề xuất chỉ số Night Data thêm vào bộ lọc màn Chỉ số đêm

Viết ngày 23/11/2026. Căn cứ: `docs/NIGHT_DATA_DICTIONARY.md` (127 trường, trong đó
82 thuộc bảng Night Data) và hiện trạng 22 chỉ số đang có trong bộ lọc.

## Trước hết: một điều dễ hiểu nhầm khi đọc bảng hiện tại

Phần lớn những gì màn Chỉ số đêm đang bày ra **không thuộc Night Data**. Từ điển xếp
`sol`, `sol_density`, `sol_change_pct`, `sol_cal`, `sol_raw`, `sol_ma3`,
`lit_area_km2`, `lit_area_pct` vào bảng **Night Economy**. Night Data giữ `tnl` —
tổng bức xạ thô trên ảnh, trước khi trừ nền.

Nên "thêm chỉ số Night Data" thực chất là **thêm tầng mô tả ảnh và chất lượng quan
sát** bên cạnh tầng kinh tế đang có.

## Vì sao ưu tiên nhóm chất lượng quan sát trước

Điều tra ngày 17/11 đã đo được: trên 1.036 dòng có độ phủ dưới 80%, **độ co giãn của
`sol` theo độ phủ là 1,07** — mất một nửa pixel thì mất đúng một nửa `sol`, dù tỉnh
không hề tối đi. Chính bảng trong ảnh chụp cũng cho một ví dụ: Bình Thuận
2024-08 có *"Biến động so với tháng liền trước" = +817%*, ngay sau tháng 07 chỉ có
**1,63 lượt quan sát sạch mây** và diện tích sáng tụt còn 729 km² so với ~3.300 km²
các tháng khác. Con số 817% đó là mây tan, không phải kinh tế.

Người đọc bảng hiện **không có cột nào để tự thấy điều đó**. Đó là lỗ hổng lớn nhất,
không phải chuyện thiếu chỉ số mới lạ.

---

## Bảng đề xuất

Cột "Công" = công sức thêm vào:

- **A** — cột đã có sẵn trong `ntl_annual`/`ntl_monthly`, chỉ cần khai thêm một mục
  trong `store.INDICATORS`. Vài dòng mã, không chạy lại gì.
- **B** — `calculate_ntl` đã tính ra nhưng chưa đổ vào hai bảng đó: phải thêm cột vào
  `schema.sql`, tăng `SCHEMA_VERSION`, nạp lại.
- **C** — nằm ở các bảng của bộ demo/P1 (`demo_result`, `light_class_summary`,
  `annual_observation_support`, kết quả không gian). Phải chạy bộ đó và nối vào truy
  vấn `panel`. Hiện trên máy anh **chưa có bảng nào trong số đó**.

### Nhóm 1 · Chất lượng quan sát — nên làm trước

| Trường | Ý nghĩa | Vì sao nhà nghiên cứu cần | Công |
|---|---|---|---|
| `obs_status` | Cờ A/B/L/O/U theo CL_OBS_STATUS của IMF | Hiện chỉ nằm trong tooltip. Thành cột thì lọc bỏ dòng kém tin cậy được ngay, và bảng xuất ra CSV mang theo cờ | **A** |
| `valid_area_pct` | % diện tích tỉnh thật sự quan sát được | **Quan trọng nhất.** Không có nó thì không thể phân biệt "tỉnh tối đi" với "vệ tinh không nhìn thấy". Dùng làm biến kiểm soát hoặc ngưỡng loại dòng | **C** |
| `valid_area_km2` | Diện tích có quan sát | Mẫu số đúng khi muốn tính mật độ trên phần quan sát được thay vì trên cả tỉnh | **C** |
| `valid_month_count` | Số tháng có dữ liệu sau lưng một dòng năm | Dòng năm dựng từ 3 tháng và từ 12 tháng không cùng độ tin cậy; hiện không phân biệt được | **C** |
| `nodata_pixels` | Số ô không có bức xạ hợp lệ | Đối chứng với `total_pixels` để thấy phần bị che | **C** |

### Nhóm 2 · Tham số đã dùng để ra con số

| Trường | Ý nghĩa | Vì sao cần | Công |
|---|---|---|---|
| `lit_threshold` | Ngưỡng xác định pixel sáng (VIIRS 1,5; DMSP DN 5) | Mọi chỉ số `lit_*` phụ thuộc ngưỡng này. Bày ra để người đọc biết con số đến từ đâu, và để thấy ngay khi chuỗi đổi ngưỡng giữa chừng | **A** |
| `background_threshold` | Ngưỡng trừ nền (VIIRS 0,5; DMSP 0) | Giải thích chênh lệch giữa `sol` và `sol_raw` đang hiển thị cạnh nhau | **A** |
| `background_pixels` | Số pixel dưới ngưỡng nền | Đo trực tiếp bước lọc nền lấy đi bao nhiêu | **A** |

### Nhóm 3 · Phân bố bức xạ trong tỉnh

| Trường | Ý nghĩa | Vì sao cần | Công |
|---|---|---|---|
| `min_rad` | Bức xạ nhỏ nhất trong tỉnh | Bộ bốn `min/mean/max/std` đang thiếu đúng `min`. Có đủ bốn mới mô tả được phân bố | **A** |

### Nhóm 4 · Chuỗi Night Data gốc

| Trường | Ý nghĩa | Vì sao cần | Công |
|---|---|---|---|
| `tnl` | Tổng bức xạ **trước** trừ nền, theo mạch Task 3 | Night Data có chuỗi riêng; đối chiếu với `sol` cho thấy tác động của lọc nền | **B** |
| `tnl_ma3` | Trung bình 3 **dòng quan sát** gần nhất | **Khác `sol_ma3`** vốn tính theo 3 tháng lịch. Tháng thiếu thì hai số lệch nhau — từ điển ghi rõ không thay cho nhau | **B** |
| `tnl_mom_growth_pct` | Tăng trưởng so với dòng quan sát liền trước | Cùng lý do: bỏ qua tháng trống thay vì để trống | **B** |

### Nhóm 5 · Động thái không gian — hiện chỉ có ở màn Phân tích không gian

| Trường | Ý nghĩa | Vì sao cần | Công |
|---|---|---|---|
| `lit_gain_km2` / `lit_loss_km2` | Diện tích sáng thêm / mất đi giữa hai mốc | Tách **mở rộng vùng sáng** khỏi **sáng đậm thêm tại chỗ** — hai cơ chế kinh tế khác hẳn nhau, và `sol` gộp cả hai | **C** |
| `lit_net_pct` | Thay đổi ròng, tính theo điểm % diện tích tỉnh | So sánh được giữa tỉnh to và tỉnh nhỏ | **C** |
| `mean_radiance_change` | Thay đổi bức xạ trung bình **trên miền chung** | Vế còn lại của phép tách trên: sáng đậm thêm mà không mở rộng. Hiện **không hiển thị ở đâu cả**, kể cả màn không gian | **C** |
| `centroid_shift_km` / `centroid_bearing_deg` | Trọng tâm sáng dịch bao xa, theo hướng nào | Đo dịch chuyển nội tỉnh — đúng thứ cô dặn: "theo dõi độ dịch chuyển kinh tế" | **C** |

---

## Thứ tự nên làm

1. **Nhóm 2 + `min_rad` + `obs_status`** (toàn mức A) — vài dòng mã, không chạy lại
   gì, và lấp đúng chỗ người đọc đang phải tin suông vào con số.
2. **`valid_area_pct` và `valid_area_km2`** (mức C) — đáng công nhất trong nhóm C, vì
   nó là biến kiểm soát mà toàn bộ phần điều tra tháng 11 cho thấy là bắt buộc.
3. **Nhóm 4** (mức B) — khi muốn đối chiếu mạch Night Data với mạch kinh tế.
4. **Nhóm 5** (mức C) — khi màn Phân tích không gian đã chạy được trên dữ liệu thật.

Chưa làm gì cả: đây là đề xuất, và nhóm B với C đều đụng `SCHEMA_VERSION` hoặc bộ
tính P1 nên cần anh quyết trước.

---

## Hai thứ đáng có mà từ điển CHƯA định nghĩa

Nêu riêng để không lẫn với phần trên — thêm chúng là mở rộng từ điển, không phải
bày ra cái đã có.

| Đề xuất | Ý nghĩa | Vì sao |
|---|---|---|
| Hệ số Gini của bức xạ trong tỉnh | Mức bất bình đẳng ánh sáng giữa các pixel | `spatial_cv` đang có chỉ là độ lệch chuẩn trên trung bình, rất nhạy với vài pixel cực sáng. Gini bền hơn và là thước đo quen thuộc trong tài liệu kinh tế |
| Tỷ trọng SOL của 1% pixel sáng nhất | Mức độ tập trung ánh sáng | Phân biệt tỉnh có một đô thị lớn với tỉnh sáng đều — hai câu chuyện kinh tế khác nhau mà `sol` và `sol_density` không tách được |

Cả hai tính được từ chính ảnh tỉnh đã lọc mà `calculate_ntl` đang đọc, không cần
tải thêm gì.
