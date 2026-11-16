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
   Hơn thế: mỗi ô mang một **cờ trạng thái** nói rõ *vì sao* trống, theo `CL_OBS_STATUS`
   của IMF (xem `docs/THAM_KHAO_FAS_IMF.md`).
5. **Tách "đo cái gì" khỏi "biểu diễn thế nào".** `sol`, `sol_density`, `sol_per_capita`
   không phải ba chỉ số: chúng là **một** chỉ số với ba mẫu số. Bộ lọc vì thế có hai ô
   chọn chứ không phải một danh sách dài dần mãi.
6. Mọi bảng và tệp tải xuống bắc qua **năm 2010** hoặc **mốc 2013** đều phải mang cảnh báo
   tương ứng (`store.MOC_2010`, cảnh báo DMSP→VIIRS) **và** cờ `B` trên chính những dòng đó.

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

### 4.3. Bảng điều khiển lọc — màn 2 và màn 3

Theo mẫu **World Bank DataBank** (ảnh chụp cô gửi 16/11). Màn 1 **không** dùng kiểu này:
nó là trình xem ảnh, mỗi lúc một phạm vi một mốc, nên giữ ô chọn đơn và thanh trượt.

Cột lọc rộng 320 px (kéo được), gồm bốn nhóm gập mở. Mỗi tiêu đề nhóm hiện **số có sẵn**
và **số đã chọn**, như DataBank:

```
┌────────────────────────────────┐
│ ▾ Phạm vi      Có 63 · Chọn 63 │
│   [✓][✕][⇅]   [tìm tỉnh…  🔍] │
│   A B C D Đ G H K L M N …      │
│   ┌──────────────────────────┐ │
│   │ ☑ An Giang               │ │
│   │ ☑ Bà Rịa - Vũng Tàu      │ │
│   │ ☑ Bạc Liêu               │ │
│   └──────────────────────────┘ │
│ ▾ Chỉ số        Có 14 · Chọn 1 │
│   [tìm chỉ số…           🔍]   │
│   ☑ Tổng độ sáng — SOL         │
│       (nW/cm²/sr · DN)         │
│   ☐ Tổng độ sáng, mật độ       │
│       (nW/cm²/sr trên km²)     │
│ ▾ Thời gian    Có 286 · Chọn 8 │
│   Khoảng có sẵn: 2004–2025     │
│   XEM GẦN ĐÂY  5  10  15  20   │
│   ☐ 2025 ▸                     │
│   ☐ 2024 ▾                     │
│       ☐01 ☐02 ☐03 ☐04         │
│   ☐ 2013                       │
│ ▸ Hàm thời gian                │
└────────────────────────────────┘
```

**Thanh công cụ mỗi nhóm**: chọn tất cả · bỏ chọn tất cả · đảo thứ tự · ô tìm kiếm.
Ô tìm bỏ dấu, giống bộ chọn phạm vi ở mục 4.1.

#### Nhóm *Chỉ số* — tên kèm đơn vị

Đúng như DataBank viết *"Access to electricity (% of population)"*. Nhãn của ta:

| Nhãn hiển thị | Cột |
|---|---|
| Tổng độ sáng — SOL (nW/cm²/sr · DN) | `sol` |
| *Đơn vị in cùng dòng với tên, cỡ chữ nhỏ hơn và màu mờ — không xuống dòng.* | |
| Tổng độ sáng, mật độ (nW/cm²/sr trên km²) | `sol_density` |
| Tổng độ sáng, bình quân đầu người (nW/cm²/sr trên người) | `sol_per_capita` |
| Tổng độ sáng **o/w** vùng sáng (nW/cm²/sr · DN) | `lit_sol` |
| Tổng độ sáng, đã hiệu chỉnh liên vệ tinh (nW/cm²/sr) | `sol_cal` |
| Diện tích vùng sáng (km²) | `lit_area_km2` |
| Diện tích vùng sáng (% diện tích tỉnh) | `lit_area_pct` |
| Số pixel sáng (pixel) | `lit_pixels` |
| Số pixel sáng (% pixel hợp lệ) | `lit_pixel_pct` |
| Bức xạ trung bình (nW/cm²/sr · DN) | `rad_mean` |
| Độ lệch chuẩn bức xạ (nW/cm²/sr · DN) | `rad_std` |
| Hệ số biến thiên (không thứ nguyên) | `rad_cv` |
| Số lượt quan sát sạch mây (lượt) | `cloud_free_obs` |

> **Quan hệ với mô hình hai chiều ở mục 6.3.** Bên trong vẫn là `chỉ số × cách biểu diễn`:
> thêm "bình quân đầu người" vẫn chỉ là **một dòng** trong bảng ánh xạ. Danh sách phẳng
> này được **sinh ra** từ bảng ánh xạ đó, nhãn ghép từ tên chỉ số và đơn vị của cách biểu
> diễn. Hai thứ không mâu thuẫn: một cái là mô hình dữ liệu, một cái là cách bày ra.

#### Nhóm *Thời gian* — hai cấp, năm rồi tháng

- Danh sách năm 2004–2025, xếp mới nhất trước, ô tick, chia cột như DataBank.
- `Khoảng có sẵn: 2004–2025` ở đầu nhóm.
- `XEM GẦN ĐÂY  5 · 10 · 15 · 20` — bấm là tick nhanh N năm gần nhất.
- **Năm từ 2014 trở đi có mũi tên `▸` mở ra 12 tháng.** Chỉ mũi tên, không kèm chữ.
  Tick năm = tick cả 12 tháng;
  tick vài tháng thì ô của năm thành trạng thái nửa chọn (`indeterminate`).
- Năm 2004–2013 **không** có mũi tên: DMSP là ảnh tổng hợp năm, NOAA không phát hành
  theo tháng. Không bày ra rồi báo lỗi.
- Bỏ hẳn hai nút `Theo năm` / `Theo tháng` của bản trước: cây thời gian đã nói rõ hơn.

#### Nhóm *Hàm thời gian*

Theo *Create Time Function* của DataBank.

| Trường | Giá trị |
|---|---|
| Loại | Tốc độ tăng trưởng bình quân năm · Trung bình trượt 3 kỳ · Tổng trong khoảng · Trung bình trong khoảng · Chỉ số gốc (năm gốc = 100) |
| Khoảng | Từ … đến … |
| Tên hàm | người dùng tự đặt, thành tên cột trong bảng và trong CSV |
| Nút | Thêm · Xoá |

Hàm đã thêm hiện thành **một cột phụ** bên phải bảng, không thay thế các cột mốc thời gian.

> **Công thức vẫn thuộc `derive.py`.** Hàm thời gian tính trên khoảng do người dùng chọn
> nên không tiền tính được, nhưng công thức đặt ở `task_pipeline/derive.py: ham_thoi_gian`
> và API chỉ gọi. Nguyên tắc là "không viết công thức trong API", không phải "không tính
> lúc có yêu cầu".
>
> Tốc độ tăng trưởng bình quân năm **từ chối chạy** khi khoảng bắc qua 2010 hoặc 2013 trên
> cột gốc: hai mốc đó làm con số vô nghĩa. Dùng cột `_cal` thì qua được mốc 2013.

### 4.4. Dải cảnh báo

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

**Không có số**: hiện `—` kèm lý do ngắn. Lý do lấy thẳng từ cờ trạng thái của dòng:

| Cờ | Hiển thị |
|---|---|
| `L` | "tháng này không có lượt quan sát sạch mây" |
| `M` | "nguồn ảnh này không có số liệu đó" |
| `B` | số vẫn hiện, kèm chấm vàng và chú giải "mốc đổi vệ tinh" |
| `U` | số vẫn hiện, kèm chấm xám và chú giải "ít pixel hợp lệ" |

Tuyệt đối không hiện `0` thay cho ô trống.

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
┌─────────────────────┐  ┌────────────────────────────────────────┐
│ ▾ Phạm vi   63 · 63 │  │ Tỉnh      2009   2010   2011 …  2014    │
│ ▾ Chỉ số    14 · 1  │  │ An Giang 12.431 38.9ᴮ 40.112 …  9.902ᴮ │
│ ▾ Thời gian 286 · 8 │  │ Bắc Kạn   —ᴸ     9.515  9.903 …  2.221  │
│ ▸ Hàm thời gian     │  │ …                                      │
│                     │  │ ᴮ đứt gãy chuỗi · ᴸ không có ảnh sạch  │
│ ⚠ cảnh báo…         │  └────────────────────────────────────────┘
└─────────────────────┘  [ Tải CSV ]
```

- Hàng = tỉnh đã tick (mặc định cả 63, xếp A–Z).
- Cột = mốc thời gian đã tick, cộng một cột cho mỗi **hàm thời gian** đã thêm.
- Tick **nhiều chỉ số** thì bảng thêm một cột `Chỉ số` và mỗi tỉnh chiếm nhiều hàng.
- Ô không có số để **trống**, không tô 0, kèm chữ nhỏ trên cao là **cờ trạng thái**.
- Nghĩa của cờ nằm ở **tooltip** khi rê chuột, không in thành chú giải dưới bảng.
  Chú giải đầy đủ đi kèm tệp tải xuống trong `ghi_chu_phuong_phap.md`.
- Dưới bảng **chỉ có nút Tải CSV**, không có dòng ghi chú nào.
- Chọn một tỉnh ở cột lọc → bảng vẫn hiện đủ 63 tỉnh nhưng **tô sáng hàng của tỉnh đó**.
  Cô cần so sánh giữa các tỉnh, lọc còn một hàng là mất mục đích.

### 6.3. Mô hình bên trong: chỉ số × cách biểu diễn

Người dùng thấy một danh sách phẳng có ô tick (mục 4.3). Bên trong, danh sách đó **sinh ra
từ** bảng ánh xạ hai chiều theo mô hình của FAS. Mỗi cặp hợp lệ là một dòng:

| Đo cái gì | Tính theo | Cột |
|---|---|---|
| Tổng độ sáng (SOL) | Số thô | `sol` |
| Tổng độ sáng (SOL) | Trên km² | `sol_density` |
| Tổng độ sáng (SOL) | Trên đầu người | `sol_per_capita` *(chờ dân số)* |
| Tổng độ sáng **o/w vùng sáng** | Số thô | `lit_sol` |
| Diện tích vùng sáng | km² | `lit_area_km2` |
| Diện tích vùng sáng | % diện tích tỉnh | `lit_area_pct` |
| Số pixel sáng | Số đếm | `lit_pixels` |
| Số pixel sáng | % pixel hợp lệ | `lit_pixel_pct` |
| Bức xạ trung bình | Số thô | `rad_mean` |
| Hệ số biến thiên | Không thứ nguyên | `rad_cv` |

Cặp không tồn tại thì **không sinh ra mục nào** trong danh sách; không bày ra rồi báo lỗi.

Ánh xạ khai báo một chỗ duy nhất trong `store.INDICATORS`. Lợi ích cụ thể: khi cô gửi dân
số, thêm "trên đầu người" là **một dòng** trong bảng ánh xạ, và nó tự xuất hiện thành một
mục có ô tick, một cột trong bảng và một cột trong CSV.

Theo **tháng** chỉ hiện những chỉ số có ở bảng `ntl_monthly`; chọn một chỉ số chỉ có theo
năm rồi bấm `Theo tháng` thì nút đó bị vô hiệu hoá kèm lời giải thích.

### 6.4. API

```
GET /api/panel?chi_so=sol,rad_cv&tinh=01,27&moc=2020,2021,2024-07&ham=cagr:2014:2025
GET /api/panel.csv?chi_so=sol&moc=2024-01,2024-02,2024-03
```

| Tham số | Ý nghĩa |
|---|---|
| `chi_so` | một hoặc nhiều mã, cách nhau bởi dấu phẩy |
| `tinh` | mã tỉnh đã tick; bỏ trống = cả 63 |
| `moc` | mốc đã tick: `2010` (năm) hoặc `2024-07` (tháng), trộn được |
| `ham` | `<loại>:<từ>:<đến>`, lặp lại được cho nhiều hàm |

Trả về `{chi_so[], moc[], ham[], dong[], canh_bao[], chu_giai_co{}}` trong đó
`dong[i] = {province_code, province_name, chi_so, gia_tri[], co[], ham{}}`; `gia_tri` và
`co` dài đúng bằng `moc`.

Mã lỗi `400` cho: mã chỉ số không có trong danh mục; mốc tháng của năm trước 2014;
hàm `cagr` trên khoảng bắc qua 2010 hoặc 2013 với cột gốc.

CSV: `Content-Disposition` dùng tên ASCII, ví dụ `chi_so_dem_sol_thang_2020_2025.csv`.
Dòng đầu là tiêu đề cột. **Mỗi cột giá trị đi kèm một cột cờ** `<mốc>_co`, giống cách SDMX
ghép `OBS_VALUE` với `OBS_STATUS`. **Cảnh báo đi vào một cột `canh_bao` ở cuối**, không chen
dòng chữ vào giữa bảng số — Excel sẽ hỏng.

Gói tải xuống kèm `ghi_chu_phuong_phap.md`: hai mốc đổi vệ tinh, tham số mô hình hiệu chỉnh,
hai ngưỡng khác nhau giữa hai cảm biến, và câu `lit_area_km2` là cận trên. FAS bắt nộp
*country notes* cùng số liệu vì đúng lý do này — tệp CSV rời không mang theo tài liệu nào.

### 6.5. Việc phải làm trước

Hiện `build_indices` chỉ nạp `ntl_annual`. Cần:

1. Thêm bảng `ntl_monthly` vào `app/data/schema.sql` (khoá `province_code + year + month`).
2. Nạp `ntl_monthly.csv` trong `build_indices`, tăng `SCHEMA_VERSION`.
3. `store.panel()` nhận thêm tham số bước thời gian và cách biểu diễn.
4. Cột `obs_status` trong `derive.py` — xem mục 11.

### 6.6. Nghiệm thu

- Chọn `Tổng SOL`, bước `Tháng`, 2020–2021 → bảng 63 hàng × 24 cột.
- Tải CSV, mở bằng Excel → mã tỉnh giữ số 0 đầu (`01` chứ không phải `1`).
- Chọn khoảng 2008–2015 → hiện **cả hai** cảnh báo, và mọi ô của **2010** và **2014**
  mang cờ `B`.
- Chọn chỉ số chỉ có theo năm → nút `Theo tháng` mờ đi, có lời giải thích.
- Chọn `Tổng SOL` + `Trên đầu người` khi chưa có dân số → ô thứ hai không bày lựa chọn đó.

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

| Chỉ số | Công thức | Đơn vị | `derivation_type` |
|---|---|---|---|
| `sol_per_capita` | `sol ÷ population` | đơn vị bức xạ/người | `SC` tính toán dẫn xuất |
| `elasticity_beta` | β trong `ln(GRDP) = α + β·ln(SOL)` | không thứ nguyên | `SE` ước lượng |

`sol_per_capita` không phải chỉ số mới trong danh mục: nó là **`SOL` biểu diễn theo đầu
người**, thêm một dòng vào bảng ánh xạ ở mục 6.3.

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

| Tình huống | Cờ | Hiển thị |
|---|---|---|
| Chưa có ảnh mốc đã chọn | `O` | `—` + lệnh cần chạy để sinh ảnh |
| Tháng không có lượt quan sát sạch mây | `L` | `—` + "tháng này không có ảnh sạch mây" |
| Cột không áp dụng cho nguồn ảnh này | `M` | `—` + "nguồn ảnh này không có số liệu đó" |
| Mốc đổi vệ tinh (2010, 2014) | `B` | số vẫn hiện, chấm vàng |
| Tháng quá ít pixel hợp lệ | `U` | số vẫn hiện, chấm xám |
| Bảng `economy` rỗng | — | Lời giải thích đang chờ số liệu của cô |
| Chưa có ranh giới GADM | — | Lệnh `python -m app.data.build_boundaries --tai-gadm` |
| TiTiler chưa chạy | — | Ảnh nền không hiện, bản đồ vẫn dùng được, có lời giải thích |

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
| 0 | Cột `obs_status` trong `derive.py` + chạy lại chỉ số | **chốt trước** |
| 1 | Nạp `ntl_monthly` vào SQLite, tăng `SCHEMA_VERSION` | không |
| 2 | Bảng ánh xạ chỉ số × cách biểu diễn trong `store.INDICATORS` | không |
| 3 | `store.panel()` nhận bước thời gian và cách biểu diễn; `/api/panel` + `.csv` | 1, 2 |
| 4 | Bảng điều khiển lọc kiểu DataBank: bốn nhóm gập mở, ô tick, cây thời gian năm→tháng | 2 |
| 5 | `derive.ham_thoi_gian` — năm hàm thời gian + test | không |
| 6 | Màn 2 — bảng có cờ, cột hàm thời gian, nút tải CSV | 3, 4, 5 |
| 7 | `/api/anh-dem.tif` nhận `province_code` | không |
| 8 | `/api/tong-hop` + ba số SOL / Area / Density trên màn 1 | 1 |
| 9 | Thanh chuyển ba màn | không |
| 10 | `metadata/ghi_chu_phuong_phap.md` kèm vào mọi gói tải | không |
| 11 | Bảng `economy`, tệp mẫu, hàm hồi quy β + test dữ liệu giả | không |
| 12 | Màn 3 — dùng lại bảng điều khiển lọc của màn 2 | 4, 11 + số liệu của cô |

Mục 1–10 làm được ngay. Mục 11 viết và kiểm chứng được bằng dữ liệu giả trước khi cô gửi số;
chỉ mục 12 là thật sự phải chờ.

**Mục 0 phải chốt trước mọi thứ khác.** Nó đổi nội dung bảng nên phải chạy lại chỉ số
(lần trước mất 40 phút), và màn 2 được thiết kế quanh cột cờ đó. Làm màn 2 trước rồi mới
thêm cờ là phải sửa lại cả giao diện lẫn API.

---

## 11. Cột `obs_status` — thiết kế

Một ký tự mỗi dòng, theo `CL_OBS_STATUS` của IMF (chi tiết ở `docs/THAM_KHAO_FAS_IMF.md`).
Chỉ dùng bảy mã trong số 25 mã của IMF, vì bảy mã đó là tất cả những gì bộ dữ liệu này
phân biệt được:

| Mã | Nghĩa | Gán khi nào |
|---|---|---|
| `A` | Giá trị bình thường | mặc định |
| `B` | Đứt gãy chuỗi do đổi phương pháp | `year` = 2010 (F16→F18) hoặc 2014 (DMSP→VIIRS) |
| `L` | Thiếu — có tồn tại nhưng không thu được | `valid_pixels` = 0 |
| `M` | Thiếu — không thể tồn tại | cột không áp dụng cho nguồn ảnh (DMSP và `cloud_free_obs`) |
| `O` | Thiếu, không rõ lý do | `status` = `CHUA_CO_ANH` |
| `U` | Độ tin cậy thấp | `cloud_free_obs` < 2 |
| `E` | Giá trị ước lượng | dòng DMSP của các cột `_cal` |

Một dòng chỉ mang **một** mã. Khi nhiều điều kiện cùng đúng, ưu tiên theo thứ tự
`M` > `L` > `O` > `B` > `U` > `E` > `A`: thiếu dữ liệu quan trọng hơn mọi ghi chú khác.

Mã `U` giải quyết chuyện `sol_change_mom_pct` ra 343.328%: **giữ nguyên con số**, gắn cờ,
để người dùng tự lọc. Xoá số là mất dữ liệu; để trần là mời người ta vẽ nhầm biểu đồ.
