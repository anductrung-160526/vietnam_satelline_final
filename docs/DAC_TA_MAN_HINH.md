# Đặc tả màn hình VNGISDash — ba tầng theo yêu cầu của giảng viên

Nguồn yêu cầu: bản vẽ tay của cô (16/11/2026) và phần ghi âm hướng dẫn kèm theo.
Tài liệu này mô tả **làm gì** và **màn hình trông ra sao**, đủ chi tiết để code mà không
phải đoán. Mọi quyết định đã chốt ở `CLAUDE.md` vẫn có hiệu lực và không nhắc lại ở đây.

---

## 1. Cô muốn gì

Cô vẽ app thành **ba tầng, mỗi tầng một nút tải xuống**:

| Tầng | Nhãn cô ghi | Người dùng lấy được gì |
|---|---|---|
| 1 | Ảnh đêm | Xem ảnh, thấy SOL / Area / Density, **tải `.tif`** |
| 2 | Chỉ số đêm năm/tháng | Bảng chỉ số, **tải CSV** |
| 3 | Chỉ số kinh tế đêm | Bảng chỉ số kinh tế + hệ số β, **tải CSV** |

Dặn thêm trong ghi âm:

- Dùng **GRDP** (theo tỉnh), cô cung cấp cùng **dân số**.
- Cấp phân tích: **63 tỉnh**, không xuống cấp huyện.
- Ánh sáng bình quân đầu người: tự tính từ dân số cô gửi.
- Độ co giãn: hồi quy `ln(GRDP) = β·ln(ánh sáng) + …`, **chỉ cần ra β**, không cần phần
  phức tạp khác.
- Liệt kê đầy đủ mọi chỉ số ra bảng theo mẫu tham khảo.
- Mục đích: đánh giá tổng quan từng tỉnh và theo dõi **dịch chuyển kinh tế qua các giai đoạn**.
- Nhóm chỉ số đặc thù (nhóm D, chỉ số mới): cô kiểm tra độ chính xác trước, bổ sung sau.

---

## 2. Nguyên tắc thiết kế

1. **Bản đồ đêm là chủ đạo.** Màn 1 mở mặc định. Giao diện lùi lại phía sau ảnh.
2. **Nhẹ và dễ dùng.** Không thêm biểu đồ, số liệu hay ghi chú nào ngoài đặc tả này.
3. **Không tính chỉ số trong API.** Mọi công thức thuộc `task_pipeline/derive.py`.
   Ngoại lệ duy nhất được phép: **phép cộng** trên các chỉ số đã tính sẵn (tổng toàn quốc),
   vì đó không phải công thức mới. Thấy cần một phép tính khác thì thêm vào `derive.py`.
4. **Ô trống là một trạng thái hợp lệ**, phải hiển thị rõ chứ không được tô 0.
5. Mọi bảng và tệp tải xuống bắc qua **năm 2010** hoặc **mốc 2013** đều phải mang cảnh báo
   tương ứng (`store.MOC_2010`, cảnh báo DMSP→VIIRS).

---

## 3. Cấu trúc tổng thể

```
┌──────────────────────────────────────────────────────────────┐
│  VNGISDash                                    [63 tỉnh]      │  thanh đầu
├──────────────────────────────────────────────────────────────┤
│  [ Ảnh đêm ]  [ Chỉ số đêm ]  [ Chỉ số kinh tế đêm ]         │  thanh chuyển màn
├──────────────┬───────────────────────────────────────────────┤
│  cột lọc     │                                               │
│  (kéo rộng   │          vùng nội dung của màn                │
│   hẹp tuỳ ý) │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

Ba màn dùng **chung một bộ chọn phạm vi và thời gian** ở cột trái. Đổi tỉnh ở màn 1 rồi
sang màn 2 thì màn 2 giữ nguyên tỉnh đó — không bắt chọn lại.

Thanh chuyển màn là ba nút, không phải menu thả xuống: cô cần thấy ngay app có ba phần.

---

## 4. Thành phần dùng chung (cột lọc)

### 4.1. Bộ chọn phạm vi — ĐÃ XONG

Ô tìm kiếm bỏ dấu + danh sách 63 tỉnh xếp A–Z theo đối chiếu tiếng Việt (`a < ă < â`),
kèm nút *Xem toàn quốc*. Gõ còn đúng một tỉnh thì chọn luôn; Enter chọn tỉnh đầu tiên.

### 4.2. Bộ chọn thời gian

| Thành phần | Hành vi |
|---|---|
| Hai nút `Theo năm` / `Theo tháng` | Nút nào không có ảnh/dữ liệu thì bị vô hiệu hoá, không ẩn đi |
| Ô chọn mốc | 2004–2025 (năm) hoặc 01/2014–12/2025 (tháng) |
| Thanh trượt | Đồng bộ hai chiều với ô chọn |

Theo tháng chỉ có từ **2014**: DMSP là sản phẩm tổng hợp năm, NOAA không phát hành theo
tháng. Phải ghi câu này dưới bộ chọn, không để người dùng tự đoán.

### 4.3. Dải cảnh báo

Hiện ngay dưới bộ chọn, mỗi cảnh báo một dòng, nền vàng nhạt:

- khoảng năm bắc qua **2010** → cảnh báo mốc đổi vệ tinh F16→F18 chưa hiệu chỉnh;
- khoảng năm bắc qua **2013** → nhắc dùng cột `_cal`;
- bảng chỉ số ngày có năm 2015–2018 → cảnh báo TOA.

---

## 5. Màn 1 — Ảnh đêm

### 5.1. Mục đích

Xem ảnh đêm thật, cắt theo ranh giới, chọn mốc thời gian, tải ảnh xuống.

### 5.2. Giao diện

```
cột lọc                        vùng ảnh
┌────────────────────┐  ┌──────────────────────────────────┐
│ Phạm vi            │  │                                  │
│  [tìm tỉnh…]       │  │     ảnh đêm, cắt theo ranh giới  │
│  [Bắc Ninh      ▾] │  │     ranh giới sáng lên khi chọn  │
│  [↩ Toàn quốc]     │  │                                  │
│                    │  │                                  │
│ Thời điểm          │  │                                  │
│  [Năm][Tháng]      │  │                                  │
│  [2024          ▾] │  │                                  │
│  ───────●────────  │  │                                  │
│                    │  │                                  │
│ SỐ LIỆU            │  │                                  │
│  SOL      63.280   │  │                                  │
│  Diện tích  4.494  │  │                                  │
│  Mật độ     14,09  │  │                                  │
│                    │  │                                  │
│ [ Tải ảnh (.tif) ] │  │                                  │
└────────────────────┘  └──────────────────────────────────┘
```

### 5.3. Ba số liệu

Đặt trong **cột lọc**, không chồng lên ảnh: cô muốn ảnh chiếm tối đa diện tích.

| Nhãn | Cột | Đơn vị | Làm tròn |
|---|---|---|---|
| SOL | `sol` | nW/cm²/sr (VIIRS) hoặc DN (DMSP) | 0 chữ số |
| Diện tích | `area_km2` | **km²** (đã chốt, không dùng m²) | 0 chữ số |
| Mật độ | `sol_density` | đơn vị bức xạ / km² | 2 chữ số |

Dưới ba số ghi nguồn ảnh và mốc: `VIIRS · 2024` hoặc `DMSP · 2010`, để không ai nhầm
thang đo giữa hai vệ tinh.

**Toàn quốc**: `SOL` = tổng 63 tỉnh, `Diện tích` = tổng diện tích, `Mật độ` =
tổng SOL ÷ tổng diện tích. Đây là phép cộng trên chỉ số đã có, không phải công thức mới.

**Không có số**: hiện `—` kèm lý do ngắn (`chưa có ảnh`, `tháng này không có lượt quan
sát sạch mây`). Tuyệt đối không hiện `0`.

### 5.4. Tải ảnh

Nút `Tải ảnh đêm (.tif)`:

- **Toàn quốc** → ảnh ghép toàn quốc của mốc đang chọn.
- **Một tỉnh** → ảnh đã cắt theo ranh giới tỉnh đó.

Tên tệp **chỉ dùng ASCII**: `VN_NTL_27_bac_ninh_2024-07.tif`. Tên có dấu sẽ làm hỏng
header HTTP (đã gặp lỗi `latin-1` này một lần rồi).

### 5.5. API

```
GET /api/anh-dem.tif?nam=2024&thang=7&province_code=27
```

| Tham số | Bắt buộc | Ghi chú |
|---|---|---|
| `nam` | có | 1990–2100 |
| `thang` | không | 0 = ảnh cả năm (mặc định) |
| `province_code` | không | bỏ trống = toàn quốc |

Trả về: `image/tiff`. Mã lỗi: `404` chưa có ảnh mốc đó (kèm lệnh cần chạy), `410` sổ có
ghi nhưng tệp không còn trên đĩa, `404` mã tỉnh không tồn tại.

Cách cắt: ưu tiên **đọc thẳng ảnh tỉnh có sẵn** trên ổ E (`data_intermediate/`), nhanh hơn
cắt lại. Không có thì cắt COG toàn quốc bằng `rasterio.mask` theo polygon GADM.

```
GET /api/tong-hop?nam=2024&thang=7          → {sol, area_km2, sol_density, source, so_tinh}
```
Dùng cho ba số ở chế độ Toàn quốc. Chỉ `SUM()` trong SQL, không có công thức mới.

### 5.6. Nghiệm thu

- Chọn Bắc Ninh, mốc 07/2024 → ảnh chỉ hiện trong ranh giới Bắc Ninh, ba số đổi theo.
- Bấm tải → mở bằng QGIS thấy đúng phạm vi tỉnh, đúng mốc.
- Chuyển sang mốc không có ảnh → ba số hiện `—`, nút tải bị vô hiệu hoá, có lời giải thích.
- Chọn năm 2008 → dải cảnh báo mốc 2010 **không** hiện; chọn khoảng bắc qua 2010 ở màn 2 → hiện.

---

## 6. Màn 2 — Chỉ số đêm

### 6.1. Mục đích

Bảng chỉ số theo năm hoặc theo tháng, cho cả 63 tỉnh, tải được ra CSV.

### 6.2. Giao diện

```
cột lọc                   bảng
┌──────────────────┐  ┌───────────────────────────────────────────┐
│ Chỉ số           │  │ Tỉnh          2020    2021    2022   2023 │
│  [Tổng SOL    ▾] │  │ An Giang    12.431  13.009  13.880 14.102 │
│                  │  │ Bà Rịa…     28.004  29.117  31.002 32.455 │
│ Bước thời gian   │  │ Bạc Liêu     9.220   9.515   9.903 10.221 │
│  [Năm][Tháng]    │  │ …                                         │
│                  │  │ 63 tỉnh · nguồn VIIRS                     │
│ Từ [2020] đến    │  └───────────────────────────────────────────┘
│    [2025]        │  [ Tải CSV ]
│                  │
│ ⚠ cảnh báo…      │
└──────────────────┘
```

- Hàng = 63 tỉnh (xếp A–Z, giống bộ chọn phạm vi).
- Cột = mốc thời gian trong khoảng đã chọn.
- Ô không có số để **trống**, không tô 0.
- Cột `source` hiện ở chân bảng, không chen vào từng ô.
- Chọn một tỉnh ở cột lọc → bảng vẫn hiện đủ 63 tỉnh nhưng **tô sáng hàng của tỉnh đó**.
  Cô cần so sánh giữa các tỉnh, lọc còn một hàng là mất mục đích.

### 6.3. Danh mục chỉ số

Lấy từ `store.INDICATORS`. Thêm chỉ số mới ở đó là nó tự xuất hiện trong ô chọn và trong
tệp CSV — không sửa giao diện.

Theo **tháng** chỉ hiện những chỉ số có ở bảng `ntl_monthly`; chọn một chỉ số chỉ có theo
năm rồi bấm `Theo tháng` thì nút đó bị vô hiệu hoá kèm lời giải thích.

### 6.4. API

```
GET /api/panel?chi_so=sol&buoc=nam&tu=2020&den=2025
GET /api/panel.csv?chi_so=sol&buoc=thang&tu=2020&den=2025
```

`buoc` nhận `nam` hoặc `thang`; mặc định `nam`. Trả về `{chi_so, moc[], dong[], canh_bao[]}`
trong đó `dong[i] = {province_code, province_name, gia_tri[]}` dài đúng bằng `moc`.

CSV: `Content-Disposition` dùng tên ASCII, ví dụ `chi_so_dem_sol_thang_2020_2025.csv`.
Dòng đầu là tiêu đề cột; **cảnh báo đi vào một cột `canh_bao` ở cuối**, không chen dòng
chữ vào giữa bảng số — Excel sẽ hỏng.

### 6.5. Việc phải làm trước

Hiện `build_indices` chỉ nạp `ntl_annual`. Cần:

1. Thêm bảng `ntl_monthly` vào `app/data/schema.sql` (khoá `province_code + year + month`).
2. Nạp `ntl_monthly.csv` trong `build_indices`, tăng `SCHEMA_VERSION`.
3. `store.panel()` nhận thêm tham số bước thời gian.

### 6.6. Nghiệm thu

- Chọn `Tổng SOL`, bước `Tháng`, 2020–2021 → bảng 63 hàng × 24 cột.
- Tải CSV, mở bằng Excel → mã tỉnh giữ số 0 đầu (`01` chứ không phải `1`).
- Chọn khoảng 2008–2015 → hiện **cả hai** cảnh báo (mốc 2010 và mốc 2013).
- Chọn chỉ số chỉ có theo năm → nút `Theo tháng` mờ đi, có lời giải thích.

---

## 7. Màn 3 — Chỉ số kinh tế đêm

### 7.1. Mục đích

Ghép ánh sáng với GRDP và dân số của cô, ra hai thứ cô cần: **ánh sáng bình quân đầu
người** và **hệ số co giãn β**.

### 7.2. Dữ liệu đầu vào — chờ cô

Bảng `economy`, khoá `province_code + year`:

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `population` | Dân số trung bình năm | cô cung cấp |
| `grdp` | GRDP theo tỉnh | cô cung cấp |
| `grdp_price_basis` | `so_sanh` hoặc `hien_hanh` | **phải hỏi cô** |
| `source` | Ghi nguồn số liệu | cô cung cấp |

> **`grdp_price_basis` là trường quan trọng nhất của bảng này.** Nếu GRDP ở giá hiện hành
> thì β bị lạm phát thổi lên: GRDP danh nghĩa tăng một phần chỉ vì giá, trong khi ánh sáng
> không phản ứng với giá. App phải hiện cảnh báo đỏ khi giá trị là `hien_hanh`, và tài liệu
> báo cáo phải ghi rõ.

Chuẩn bị sẵn tệp mẫu `app/data/kinh_te_mau.csv` đúng cột, để khi cô gửi là nạp được ngay.

### 7.3. Chỉ số

**Làm ngay** (cô nói rõ chỉ cần những thứ này):

| Chỉ số | Công thức | Đơn vị |
|---|---|---|
| `sol_per_capita` | `sol ÷ population` | đơn vị bức xạ/người |
| `elasticity_beta` | β trong `ln(GRDP) = α + β·ln(SOL)` | không thứ nguyên |

**Để sau** (nhóm cô sẽ kiểm tra độ chính xác trước): GDP dự báo từ ảnh, chênh lệch GDP
thật và dự báo, SOL trên một đồng GRDP, cường độ vùng sáng, tỷ trọng SOL quốc gia.
Mô tả đầy đủ ở `docs/CHI_SO_KINH_TE_DEM.md`.

### 7.4. Hồi quy

Hàm mới trong `task_pipeline/derive.py` (không đặt trong API):

```
ln(GRDP) = α + β · ln(SOL)
```

| Quyết định | Chọn | Vì sao |
|---|---|---|
| Phạm vi mặc định | **2014–2025** | Giai đoạn VIIRS, một cảm biến, không mốc nối nào |
| Cột ánh sáng | `sol` | Trong giai đoạn VIIRS, `sol` và `sol_cal` bằng nhau |
| Mô hình chính | Gộp toàn bộ tỉnh-năm → **một β cho cả nước** | Đúng công thức cô viết |
| Mô hình phụ | β riêng từng tỉnh, chỉ khi tỉnh đó có ≥ 8 quan sát | Để thấy tỉnh nào lệch |
| Loại bỏ | Dòng có `sol ≤ 0` hoặc `grdp ≤ 0` | log của số không dương không tồn tại |

Trả về và lưu ở `metadata/do_co_gian_sol_grdp.json`: `beta`, `alpha`, `r2`, `n`,
`nam_tu`, `nam_den`, `price_basis`, `so_tinh`.

Mở rộng phạm vi về trước 2014 thì phải dùng `sol_cal` **và** ghi rõ chuỗi bắc qua mốc
2010 chưa hiệu chỉnh — app hiện cảnh báo, không tự chặn.

### 7.5. Giao diện

```
┌──────────────────────────────────────────────────────────────┐
│  ĐỘ CO GIÃN ÁNH SÁNG – GRDP                                  │
│                                                               │
│     β = 0,78        R² = 0,84      n = 756      2014–2025    │
│                                                               │
│  ln(GRDP) = α + β·ln(SOL) · gộp 63 tỉnh · GRDP giá so sánh   │
│  Ánh sáng tăng 10% ứng với GRDP tăng khoảng 7,8%.             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Tỉnh        Dân số     GRDP      SOL    SOL/người   β tỉnh   │
│ An Giang   1.904.532   …         …         …         0,71    │
│ …                                                             │
└──────────────────────────────────────────────────────────────┘
[ Tải CSV ]
```

Một câu diễn giải β bằng tiếng Việt dưới công thức. Cô sẽ đưa con số này vào báo cáo, và
"β = 0,78" tự nó không nói gì với người đọc không làm kinh tế lượng.

### 7.6. API

```
GET /api/kinh-te-dem?nam_tu=2014&nam_den=2025      → bảng + kết quả hồi quy
GET /api/kinh-te-dem.csv?nam_tu=&nam_den=
```

Bảng `economy` rỗng → trả `200` với mảng rỗng và một câu giải thích đang chờ số liệu,
**không trả lỗi**. App phải chạy được khi chưa có dữ liệu kinh tế.

### 7.7. Nghiệm thu

- Bảng `economy` rỗng → màn hiện lời giải thích, không vỡ, không hiện số giả.
- Nạp dữ liệu giả có β biết trước (ví dụ 0,8) → hồi quy trả về β trong khoảng 0,78–0,82.
- `grdp_price_basis = hien_hanh` → cảnh báo đỏ hiện ở cả màn hình lẫn trong CSV.
- Mở rộng khoảng về 2004 → hiện cảnh báo mốc 2010.

---

## 8. Trạng thái rỗng và lỗi

| Tình huống | Hiển thị |
|---|---|
| Chưa có ảnh mốc đã chọn | `—` + lệnh cần chạy để sinh ảnh |
| Tháng không có lượt quan sát sạch mây | `—` + "tháng này không có ảnh sạch mây" |
| Bảng `economy` rỗng | Lời giải thích đang chờ số liệu của cô |
| Chưa có ranh giới GADM | Lệnh `python -m app.data.build_boundaries --tai-gadm` |
| TiTiler chưa chạy | Ảnh nền không hiện, bản đồ vẫn dùng được, có lời giải thích |

Nguyên tắc chung: mỗi trạng thái rỗng phải nói **vì sao** và **cần chạy gì**.

---

## 9. Không làm trong phạm vi này

- Cấp huyện, cấp xã. Cô xác nhận lại là **63 tỉnh**.
- Hiệu chỉnh mốc 2010 (đã chốt giữ nguyên).
- Năm nhóm chỉ số kinh tế bổ sung — chờ cô kiểm tra độ chính xác.
- Ảnh ngày: chỉ số NDVI/NDBI/MNDWI/BSI chưa tính xong, màn riêng để sau.
- Phân loại lớp phủ 5 lớp — thiếu điểm mẫu.

---

## 10. Thứ tự triển khai

| # | Việc | Phụ thuộc |
|---|---|---|
| 1 | Nạp `ntl_monthly` vào SQLite, tăng `SCHEMA_VERSION` | không |
| 2 | `store.panel()` nhận bước thời gian; `/api/panel` + `.csv` | 1 |
| 3 | Màn 2 — bảng + nút tải CSV | 2 |
| 4 | `/api/anh-dem.tif` nhận `province_code` | không |
| 5 | `/api/tong-hop` + ba số SOL / Area / Density trên màn 1 | 1 |
| 6 | Thanh chuyển ba màn | không |
| 7 | Bảng `economy`, tệp mẫu, hàm hồi quy β + test dữ liệu giả | không |
| 8 | Màn 3 | 7 + số liệu của cô |

Mục 1–6 làm được ngay. Mục 7 viết và kiểm chứng được bằng dữ liệu giả trước khi cô gửi số;
chỉ mục 8 là thật sự phải chờ.
