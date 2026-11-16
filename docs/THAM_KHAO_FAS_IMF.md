# Học quy ước lập danh mục chỉ số từ FAS của IMF

Nguồn đọc trực tiếp (16/11/2026):
[Financial Access Survey Guidelines and Manual](https://www.imf.org/-/media/files/data/home/financial-access-survey-guidelines-and-manual-english.pdf)
· [Trang bộ dữ liệu FAS](https://data.imf.org/en/datasets/IMF.STA:FAS)

FAS là bộ chỉ số tiếp cận tài chính của IMF, thu thập từ ngân hàng trung ương các nước rồi
công bố thành bảng quốc gia × năm. Cấu trúc bài toán giống hệt bộ dữ liệu đêm của ta:
nhiều đơn vị hành chính, nhiều năm, chỉ số thô và chỉ số dẫn xuất, dữ liệu thiếu rải rác.
Tài liệu này ghi lại **cái gì đáng chép** và **chép thế nào**.

---

## 1. Ba trạng thái của một ô trống — cái ta đang làm sai

FAS phân biệt dứt khoát ba thứ mà ta đang gộp làm một. Nguyên văn:

> “NA” indicates that the financial institution or service either **does not exist** in the
> reporting jurisdiction or **falls outside the coverage** of the reporting authority.
> Provide an explanation in the metadata in either case.
>
> A **missing data point** indicates that data for the financial institution or service is
> either **not collected by or is not available** with the reporting authority.
>
> A data point reported as zero ‘0’ is **a data value of zero**.

Bộ dữ liệu của ta hiện ghi **cùng một ô trống** cho hai tình huống hoàn toàn khác nhau:

| Tình huống | FAS gọi là | Ta đang ghi |
|---|---|---|
| `cloud_free_obs` ở dòng DMSP — cảm biến **không có** băng `cf_cvg` | **NA** (không tồn tại) | trống |
| Tháng cả tỉnh không có lượt quan sát sạch mây — ảnh **có** nhưng không dùng được | **missing** (không có số liệu) | trống |
| Tỉnh thật sự không có pixel nào vượt ngưỡng sáng | **0** | 0 |

Hai dòng đầu khác nhau về bản chất: một cái là "câu hỏi không áp dụng cho nguồn ảnh này",
cái kia là "câu hỏi áp dụng nhưng tháng đó mây che". Người đọc bảng không có cách nào phân
biệt, và script kiểm định của ta cũng phải đoán bằng `valid_pixels = 0`.

**Đề xuất:** thêm cột `status` cho từng dòng theo ba mã, hoặc thêm cột cờ `flag` mang
`NA` / `MISSING` / rỗng, theo đúng cách FAS làm. Đây là thay đổi nội dung bảng nên cần chốt
trước khi chạy lại chỉ số.

---

## 2. Cách viết định nghĩa một chỉ số

FAS đánh số từng mục và viết theo khuôn **“X refers to …”**, rồi tách riêng phần bao gồm,
phần loại trừ và quy tắc đếm. Nguyên văn hai ví dụ:

> **18. Number of branches:** all units in the country physically separated from main
> offices, not incorporated as separate subsidiaries; **exclude main offices**. Branches
> include units with or without human staff that provide a range of services and automated
> units offering cash withdrawal/deposit or online banking terminals and check depositing
> machines.

> **27. Number of debit cards** refers to the total number of debit cards of all financial
> institutions **in circulation (excluding expired and withdrawn cards)** in the reporting
> jurisdiction.

Ba điểm đáng chép:

1. **Nói rõ cái gì bị loại trừ**, không chỉ cái gì được tính. "exclude main offices",
   "excluding expired and withdrawn cards".
2. **Quy tắc đếm tách thành mục riêng.** Ví dụ mục 21 có hẳn khối *Counting rules*:
   tài khoản chung thì đếm từng người sở hữu; một doanh nghiệp có nhiều tài khoản vẫn
   tính là một người gửi tiền.
3. **Đơn vị nằm trong chính câu định nghĩa**: "the total amount (in millions of domestic
   currency) of …".

Áp vào bộ của ta, định nghĩa `lit_area_km2` hiện là *"Diện tích các pixel vượt ngưỡng sáng"*.
Theo khuôn FAS nó phải thành:

> `lit_area_km2` là tổng diện tích các pixel có giá trị **lớn hơn hoặc bằng** ngưỡng sáng
> (`lit_threshold`), tính bằng km². **Pixel chạm ranh giới tỉnh được tính trọn**, nên tổng
> này là **cận trên** và có thể vượt `area_km2`. Không trừ phần pixel nằm ngoài ranh giới.

Câu "pixel chạm ranh giới được tính trọn" chính là thứ giải thích hiện tượng
`lit_area_pct` ra 111,79% mà ta đã gặp. FAS sẽ viết nó vào định nghĩa, không để người đọc
tự phát hiện.

---

## 3. Ký hiệu nhóm con: “o/w”

FAS đánh số chỉ số con bằng số thập phân và dùng chữ **o/w** (*of which*):

> 21. Number of depositors
> 21.1. Number of depositors **o/w SME**
> 21.2. Number of depositors **o/w household sector**

Và nói thẳng khi tổng các nhóm con **không** bằng tổng:

> It is therefore possible that the sum of men-owned and women-owned deposits may not
> necessarily be equal to the number of household sector deposits.

Bộ của ta có đúng quan hệ này mà chưa đánh dấu: `lit_sol` là nhóm con của `sol` (chỉ tính
trên pixel vượt ngưỡng sáng). Nên ghi là `sol` và `sol o/w vùng sáng`, kèm câu
`lit_sol ≤ sol` để người đọc biết đây không phải hai chỉ số độc lập.

---

## 4. Ghi chú phương pháp đi kèm dữ liệu

FAS bắt nước báo cáo nộp **country notes** cùng số liệu, với hai mục bắt buộc:

> **42.1. Existing deviations from the definitions** set out in the FAS guidelines: if any
> of the data series are defined differently in your jurisdiction, provide details.
>
> **42.2. Any additional information deemed useful to the data users**: if there are any
> **changes in methodology**, or any other change that affects the data, provide details.

Mục 42.2 chính là chỗ của hai mốc đổi vệ tinh. Ta đang ghi chúng trong `CLAUDE.md` và trong
cảnh báo của API, nhưng **chưa đi kèm chính bộ dữ liệu**. Ai nhận tệp CSV rời sẽ không thấy.

**Đề xuất:** sinh một tệp `metadata/ghi_chu_phuong_phap.md` cùng lúc với bảng, và kèm nó vào
mọi gói tải xuống. Nội dung tối thiểu: mốc F16→F18 năm 2010 chưa hiệu chỉnh, mốc DMSP→VIIRS
năm 2013 đã hiệu chỉnh và tham số mô hình, hai ngưỡng khác nhau giữa hai cảm biến,
`lit_area_km2` là cận trên.

---

## 5. Kiểm tra tính nhất quán nằm trong chính tệp thu thập

> **43. Data Validation:** At the bottom of the FAS survey questionnaire, there are a few
> data consistency checks. Prior to uploading the questionnaire, check the consistency and
> accuracy of the reported data using the consistency checks. If a data point fails this
> consistency check, the corresponding validation cell will be **highlighted in red**.

Ta đã có `scripts/kiem_dinh_chat_luong.py` làm đúng việc này. Khác biệt: FAS chạy kiểm tra
**trước khi** dữ liệu được nộp, ta chạy **sau khi** tính xong. Nên giữ nguyên cách của ta vì
dữ liệu do máy sinh chứ không do người nhập, nhưng nên đưa kết quả kiểm định vào gói tải
xuống để người nhận biết bảng đã qua kiểm tra nào.

---

## 6. Bố cục bộ lọc: FAS tách "đo cái gì" khỏi "biểu diễn thế nào"

Đọc trực tiếp định nghĩa cấu trúc dữ liệu của FAS
(`https://api.imf.org/external/sdmx/3.0/structure/dataflow/IMF.STA/FAS?references=all`).
Bộ lọc của FAS có **bảy chiều**, đúng theo thứ tự này:

| # | Chiều | Vai trò |
|---|---|---|
| 0 | `COUNTRY` | Đơn vị địa lý |
| 1 | `INDICATOR` | **Đo cái gì** |
| 2 | `SECTOR` | Loại tổ chức tài chính |
| 3 | `COUNTERPARTY_SECTOR` | Loại khách hàng (hộ gia đình, SME) |
| 4 | `SEX` | Giới tính |
| 5 | `TYPE_OF_TRANSFORMATION` | **Biểu diễn thế nào** |
| 6 | `FREQUENCY` | Tần suất |
| 7 | `TIME_PERIOD` | Thời gian |

Điểm quan trọng nhất của cả tài liệu này: **`INDICATOR` và `TYPE_OF_TRANSFORMATION` là
hai chiều riêng biệt.** FAS không tạo ra một chỉ số mới tên "số máy ATM trên 100.000 người
trưởng thành". Nó giữ `INDICATOR = số máy ATM` rồi đặt
`TYPE_OF_TRANSFORMATION = PHTADLT_NUM`.

Bảy mã của `CL_FAS_TYPE_OF_TRANSFORMATION`:

| Mã | Nghĩa |
|---|---|
| `NUM` | Số đếm thô |
| `XDC` | Tính bằng nội tệ |
| `POGDP` | Phần trăm GDP |
| `PTADLT_NUM` | Trên 1.000 người trưởng thành |
| `PHTADLT_NUM` | Trên 100.000 người trưởng thành |
| `PTKM2_NUM` | **Trên 1.000 km²** |
| `PONFC` | Phần trăm tài khoản của doanh nghiệp phi tài chính |

### Áp vào bộ của ta

Ta đang làm ngược lại: mỗi cách biểu diễn là **một cột riêng**. `sol`, `sol_density`,
và sắp tới là `sol_per_capita` — ba cột cho **cùng một đại lượng đo**, khác nhau ở mẫu số.

Theo mô hình FAS thì đó là **một chỉ số `SOL`** với ba cách biểu diễn:

| Cách của ta | Theo mô hình FAS |
|---|---|
| `sol` | `SOL` × `NUM` |
| `sol_density` | `SOL` × trên km² (FAS dùng `PTKM2_NUM`, trên 1.000 km²) |
| `sol_per_capita` | `SOL` × trên đầu người |
| `lit_sol` | `SOL` × `NUM`, lọc theo vùng sáng |

Lợi ích cụ thể, không phải lý thuyết: khi cô gửi dân số, ta sẽ muốn **ánh sáng bình quân
đầu người** cho cả `sol` lẫn `lit_sol`, và có thể cả mật độ theo diện tích vùng sáng. Theo
cách hiện tại là thêm bốn cột nữa; theo cách FAS là thêm **một mã** vào chiều biểu diễn.

Bộ lọc trên màn 2 cũng gọn hơn: thay vì một danh sách thả xuống dài dần mãi, có **hai**
danh sách — *Đo cái gì* và *Tính theo đơn vị nào* — và cái thứ hai chỉ hiện những lựa chọn
hợp lệ với chỉ số đang chọn.

Đây là thay đổi kiến trúc, không bắt buộc làm ngay. Nhưng nên quyết **trước khi** thêm
nhóm chỉ số kinh tế, vì sau đó sửa sẽ phải đổi cả bảng lẫn giao diện.

---

## 7. Mã trạng thái quan sát: `CL_OBS_STATUS`

FAS gắn cờ cho **từng ô dữ liệu**, không phải cho cả bảng. 25 mã, trong đó những mã trực
tiếp giải quyết vấn đề của ta:

| Mã | Nghĩa | Dùng ở đâu trong bộ của ta |
|---|---|---|
| `A` | Giá trị bình thường (mặc định) | hầu hết các dòng |
| `B` | **Đứt gãy chuỗi thời gian** — nội dung hoặc phương pháp khác với kỳ trước | **năm 2010 và năm 2014** |
| `M` | Thiếu — **dữ liệu không thể tồn tại** | `cloud_free_obs` ở dòng DMSP |
| `L` | Thiếu — dữ liệu có tồn tại nhưng không thu thập được | tháng cả tỉnh mây che |
| `O` | Thiếu, không nói rõ lý do | khi chưa phân loại được |
| `E` | Giá trị ước lượng | giá trị suy ra từ mô hình |
| `DV` | **Giá trị dẫn xuất** | cột `sol_cal` sau hiệu chỉnh |
| `N` | **Không đáng kể** — không phải số 0 thật, chỉ là làm tròn xuống 0 | tỉnh gần như tối hẳn |
| `U` | Độ tin cậy thấp | tháng rất ít pixel hợp lệ |

Mã `B` đáng chú ý nhất. Nguyên văn định nghĩa:

> **B — Time series break:** Observations are characterised as such when different content
> exists or a **different methodology has been applied** to this observation as compared
> with the preceding one.

Ta đang ghi hai mốc đổi vệ tinh vào `CLAUDE.md`, vào cảnh báo của API và vào tài liệu.
FAS ghi nó **vào chính ô dữ liệu**. Ai mở tệp CSV rời cũng thấy ngay dòng 2010 và dòng
2014 mang cờ `B`, không cần đọc tài liệu nào.

Mã `U` cũng dùng được ngay cho vấn đề `sol_change_mom_pct` ra 343.328%: thay vì để trống
hay để nguyên con số vô nghĩa, gắn cờ `U` cho những tháng có quá ít pixel hợp lệ và giữ
nguyên giá trị. Người dùng lọc bỏ được, mà ta không mất dữ liệu.

---

## 8. Thuộc tính đi kèm mỗi chuỗi

Ngoài giá trị `OBS_VALUE`, FAS gắn các thuộc tính sau cho từng chuỗi:

`SCALE` · `PRECISION` · `DECIMALS_DISPLAYED` · `UNIT` · `DERIVATION_TYPE` · `TRANSFORMATION` ·
`STATUS` · `OVERLAP` · `METADATA_QUESTIONNAIRE_1` · `METADATA_QUESTIONNAIRE_2`

Hai cái ta chưa có và nên có:

- **`DECIMALS_DISPLAYED`** — số chữ số thập phân khi hiển thị, ghi trong **dữ liệu** chứ
  không nằm rải rác trong mã giao diện. Hiện ta để trong `store.INDICATORS: chu_so`.
  Ở đúng chỗ hơn là nằm cạnh định nghĩa chỉ số.
- **`DERIVATION_TYPE`** — nguồn gốc con số. 12 mã, trong đó đáng dùng:
  `R` dữ liệu thô không biến đổi · `SC` tính toán dẫn xuất · `SE` ước lượng khi thiếu
  thông tin · `M` hỗn hợp thô và dẫn xuất.

  Bộ của ta: `sol` là `R`, `sol_density` là `SC`, `sol_cal` là `SE` (có mô hình, có sai số
  R² = 0,81), và `ntl_panel` là `M` vì gộp hai nửa khác tần suất.

---

## 9. Việc nên làm, xếp theo giá trị

| # | Việc | Ảnh hưởng |
|---|---|---|
| 1 | Cột cờ `obs_status` theo `CL_OBS_STATUS`: `B` ở 2010 và 2014, `M` / `L` cho hai loại ô trống, `U` cho tháng ít pixel | Đổi nội dung bảng, phải chạy lại chỉ số |
| 2 | Viết lại định nghĩa theo khuôn FAS: nêu rõ phần loại trừ và quy tắc đếm | Chỉ sửa `CODEBOOK` |
| 3 | Đánh dấu `lit_sol` là nhóm con `o/w` của `sol` | Chỉ sửa `CODEBOOK` |
| 4 | Sinh `metadata/ghi_chu_phuong_phap.md` kèm vào mọi gói tải xuống | Thêm mã, không đổi số |
| 5 | Thêm `derivation_type` cho từng cột trong `CODEBOOK` | Chỉ sửa `CODEBOOK` |
| 6 | Tách `INDICATOR` khỏi `TYPE_OF_TRANSFORMATION` | Đổi kiến trúc bảng và bộ lọc |

Mục 2, 3, 4, 5 làm được ngay, không đụng vào số liệu. Mục 1 phải chốt trước vì bảng phải
tính lại. Mục 6 nên quyết **trước khi** thêm nhóm chỉ số kinh tế.

---

## 10. Nguồn đã đọc

- [FAS Guidelines and Manual](https://www.imf.org/-/media/files/data/home/financial-access-survey-guidelines-and-manual-english.pdf) — định nghĩa, quy tắc đếm, quy ước ô trống
- `https://api.imf.org/external/sdmx/3.0/structure/dataflow/IMF.STA/FAS?references=all` — bảy chiều lọc, 50 danh mục mã, thuộc tính chuỗi
- [Trang bộ dữ liệu FAS](https://data.imf.org/en/datasets/IMF.STA:FAS) — không xem được giao diện vì trang dựng bằng JavaScript và một script của bên thứ ba bị chặn
