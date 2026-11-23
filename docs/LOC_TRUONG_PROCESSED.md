# Lọc trường Processed: cái nào thừa trong dữ liệu, cái nào thừa khi hiển thị

Viết ngày 23/11/2026. Phạm vi: 108 trường `Processed` trong `NIGHT_DATA_DICTIONARY.md`
(73 Night Data + 35 Night Economy).

## Một ràng buộc phải nói trước, nếu không sẽ cắt nhầm

"Suy ra được từ cột khác" **không đồng nghĩa với "nên bỏ"**. CLAUDE.md cấm tính chỉ số
trong API:

> Không tính chỉ số trong API: mọi phép tính thuộc `backend/core/chi_so.py`.

Nghĩa là một cột dẫn xuất mà người dùng **thật sự đọc** thì **bắt buộc phải lưu**, chứ
không được để giao diện tự chia. `sol_density` suy được từ `sol / area_km2`, nhưng bỏ
nó đi thì hoặc màn hình phải tự tính (vi phạm quy tắc), hoặc người dùng mất một chỉ số
chính.

Nên phép lọc đúng không phải "bỏ mọi thứ suy ra được", mà là:

> **Dẫn xuất + có người đọc → giữ. Dẫn xuất + không ai đọc → bỏ.**

## Ba phép thử

1. **Trùng tên** — cùng một đại lượng mang hai tên ở hai nơi.
2. **Dẫn xuất một bước** — bằng đúng một phép chia/trừ giữa hai cột cùng dòng.
3. **Hằng số trên mọi dòng** — tham số phương pháp, không phải số đo. Một cột 1.386
   dòng giống hệt nhau là một cột nhiễu trong bộ chọn.

---

## Nhóm 1 · THỪA TRONG DỮ LIỆU — nên bỏ khỏi CSV/SQLite

### 1a. Trùng tên với một trường khác

| Trường | Trùng với | Căn cứ |
|---|---|---|
| `sol_unit` | `radiance_unit` | Hai định nghĩa giống hệt nhau: "DN với DMSP, nW/cm²/sr với VIIRS". Một cái Night Economy, một cái Night Data |
| `tnl` | `sol_raw` | Từ điển: "bằng sol_raw chỉ khi cùng ảnh, cùng mask và cùng mốc" — đúng điều kiện của dự án này. `field_contract` cũng ánh xạ `tnl → sol_raw` |
| `pixels_without_observations` | `area_without_observations_km2` | Cùng một tập pixel, đo hai cách (đếm và diện tích). Giữ bản diện tích vì so sánh được giữa tỉnh to nhỏ |

### 1b. Dẫn xuất một bước VÀ không ai đọc

| Trường | Công thức | Vì sao bỏ |
|---|---|---|
| `expected_i` | `−1/(n−1)` | Hàm thuần tuý của `moran.n`. Không mang một mẩu thông tin nào ngoài n |
| `lit_net_km2` | `lit_gain − lit_loss` | Hai vế đã hiển thị cạnh nhau. Trị ròng che mất chính cái hay: tăng và giảm cùng lúc |
| `lit_net_pct` | `lit_net / area × 100` | Dẫn xuất của dẫn xuất |
| `common_area_pct` | `common_area_km2 / area_km2` | Chỉ cần một trong hai |
| `upper_bound` | cận dưới của lớp kế tiếp | Năm lớp liền kề nhau; biết `lower_bound` là biết hết |
| `breaks` | tập hợp các `lower_bound` | Lặp lại y nguyên bộ cận dưới |
| `class_index` | thứ tự của chính dòng lớp | Suy từ `lower_bound` |
| `is_simulated` | `economy_source` chứa GIA_LAP | Suy từ nguồn |
| `paired` | `sol > 0` và hai GRDP > 0 | Suy từ chính ba cột đó |
| `predicted_gdp` | `exp(α + β·ln sol)` | Hàm thuần tuý của `alpha`, `beta`, `sol` — cả ba đã có |
| `light_gdp_elasticity` | `%Δsol / %Δgdp` | Thương của `sol_change_pct` và `gdp_change_pct`, đều đã có |

### 1c. Phân hoạch thừa một mảnh

`common_area_km2 + start_only + end_only + neither + outside_target_grid = area_km2`.
Năm mảnh chỉ cần bốn. Bỏ **`neither_area_km2`** — mảnh ít ý nghĩa nhất, vì nó gộp
chung "mây cả hai năm" với "ngoài vùng ảnh".

### 1d. Ba thành một

`valid_month_min`, `valid_month_max`, `valid_month_mean` là ba tóm tắt của cùng một
raster. Trong một bảng tỉnh × năm, **`valid_month_mean` là đủ**; min và max là cực trị
của phân bố pixel, hầu như không ai dùng để phân tích.

**Tổng nhóm 1: 17 trường Processed.**

> Bốn trường dẫn xuất nữa — `name_1`, `frequency`, `price_base_year`, `grdp_frequency` —
> cũng thừa đúng theo ba phép thử, nhưng từ điển đánh dấu chúng là **Raw** nên nằm
> ngoài phạm vi anh hỏi. `frequency` và `grdp_frequency` suy từ `month`, `price_base_year`
> suy từ `grdp_price_basis`, `name_1` trùng `province_name`. Nêu để biết, không tính vào
> con số dưới đây.

---

## Nhóm 2 · GIỮ TRONG DỮ LIỆU, BỎ KHỎI BỘ CHỌN

Những trường này phải có để kiểm toán và tái lập, nhưng đưa vào bộ chọn chỉ số thì chỉ
làm dài danh sách.

### 2a. Tham số phương pháp — hằng số trên mọi dòng

`background_threshold` · `lit_threshold` · `reference_year` · `permutations` · `seed` ·
`tolerance_m` · `weight_method` · `method_version` · `stats_version` ·
`demo_schema_version` · `spatial.version` · `area_method` · `mask_rule`

> **Đính chính đề xuất hôm qua.** Trong `DE_XUAT_CHI_SO_BO_LOC.md` tôi xếp
> `lit_threshold` và `background_threshold` vào mức A "nên thêm vào bộ lọc". Sai: cả
> hai là hằng số theo nguồn ảnh, nên cột của chúng sẽ lặp đúng một giá trị suốt 1.386
> dòng. Chỗ đúng của chúng là **chú thích đầu bảng**, không phải một chỉ số chọn được.
> `background_pixels` thì vẫn đúng là mức A — nó thay đổi theo từng dòng.

### 2b. Xuất xứ và kiểm chứng

`dataset_id` · `source_image_path` · `source_image_sha256` · `export_sha256` ·
`verification_status` · `provenance_consistent` · `run_id` · `validation_status` ·
`area_balance_error_km2` · `repaired` · `area_source`

Chúng trả lời "số này từ đâu ra", không trả lời "tỉnh này sáng bao nhiêu". Chỗ đúng:
khối metadata của màn và cột trong CSV tải về.

### 2c. Cờ văn bản — thuộc về tooltip, không phải cột

`quality_flags` · `image_quality_flags` · `comparison_note` · `missing_reason` ·
`provenance_reason` · `canh_bao` · `diagnosis`

Một cột văn bản dài trong bảng tỉnh × thời gian phá vỡ bố cục và không so sánh được.
Hiện `missing_reason` đã dùng đúng cách: làm tooltip của ô trống.

### 2d. Dễ bị đọc nhầm

`nodata_pixels` — từ điển phải tự cảnh báo "**không phải diện tích mây**", vì nó gộp cả
vùng ngoài tỉnh bị mask. Một cột mà định nghĩa phải bắt đầu bằng lời cảnh báo hiểu nhầm
thì không nên bày ra cho người đọc nhanh. Giữ để kiểm chứng.

**Tổng nhóm 2: 32 trường.**

---

## Nhóm 3 · GIỮ CẢ HAI — lõi thật sự

**59 trường** còn lại. Trong đó nhóm dẫn xuất nhưng **có người đọc**, nên theo
nguyên tắc ở đầu tài liệu thì **phải giữ cả trong dữ liệu**:

| Trường | Dẫn xuất từ | Vì sao vẫn giữ |
|---|---|---|
| `sol_density` | `sol / area_km2` | Chỉ số chính, so sánh được giữa tỉnh to nhỏ |
| `lit_area_pct` | `A_lit / A` | Cách đọc tự nhiên nhất của diện tích sáng |
| `valid_area_pct` | `A_valid / A` | Biến kiểm soát bắt buộc — xem phần độ phủ |
| `electrification_ratio_pct` | `L / N` | Mẫu số khác `lit_area_pct`, không thay nhau được |
| `spatial_cv` | `σ / μ` | Quy ước sẵn có của Task 3 |
| `class_area_pct` | `A_k / A` | Năm lớp đọc theo % mới so sánh được giữa tỉnh |
| `sol_per_capita` | `sol / population` | Chỉ số cô yêu cầu đích danh |
| `sol_change_pct`, `gdp_change_pct`, `sol_change_mom_pct`, `sol_change_yoy_pct`, `sol_ma3`, `tnl_ma3`, `tnl_mom_growth_pct` | chuỗi thời gian | Cần cửa sổ nhiều dòng, không phải một phép tính trong dòng |

---

## Tóm tắt

| Nhóm | Số trường | Xử lý |
|---|---|---|
| Thừa trong dữ liệu | 17 | Bỏ khỏi CSV/SQLite |
| Giữ dữ liệu, bỏ hiển thị | 32 | Chuyển sang metadata / tooltip / CSV tải về |
| Lõi | 59 | Giữ cả hai |

Bỏ được **17/108 trường Processed** khỏi bộ dữ liệu, và **49/108 không nên xuất hiện
trong bộ chọn chỉ số**. Cộng thêm 4 trường Raw dẫn xuất nêu ở nhóm 1 thì tổng cắt
được là 21 trường.

Chưa sửa gì. Bỏ trường khỏi `calculate_ntl` và `schema.sql` là đổi hợp đồng dữ liệu,
phải tăng `SCHEMA_VERSION` và nạp lại — cần anh duyệt từng dòng trước.

Hai chỗ nên cân nhắc kỹ hơn phần còn lại:

- **`tnl` và `sol_raw`**: từ điển cố ý giữ hai tên để đánh dấu hai mạch tính (Task 3 và
  mạch kinh tế). Gộp là mất dấu vết đối chiếu với notebook gốc của cô. Nếu phần đối
  chiếu đó còn phải trình bày thì giữ cả hai, chấp nhận trùng.
- **`light_gdp_elasticity`**: tuy là thương của hai cột đã có, nó lại là chỉ số trung
  tâm trong tài liệu Henderson–Storeygard–Weil. Bỏ cột nhưng vẫn phải hiển thị thì rơi
  vào đúng cái bẫy "tính trong API" mà CLAUDE.md cấm. Đề nghị **giữ**.
