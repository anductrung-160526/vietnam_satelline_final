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

## 6. Chưa đọc được

Cách FAS đặt tên **chỉ số dẫn xuất** (dạng *"… per 100,000 adults"*, *"… per 1,000 km²"*)
và tên cột của tệp tải xuống nằm sau API ở `portal.api.imf.org`, host chưa được mở trong
môi trường này. Hai câu hỏi còn treo:

1. FAS có công bố **mẫu số** (dân số trưởng thành, diện tích) thành một chuỗi riêng trong
   cùng bộ dữ liệu không? Nếu có thì ta cũng nên để `population` và `area_km2` thành cột
   riêng chứ không chỉ dùng để chia — hiện `area_km2` đã là cột riêng, `population` thì chưa.
2. Có mã cờ (flag code) chuẩn cho dòng bị gãy chuỗi không?

---

## 7. Việc nên làm, xếp theo giá trị

| # | Việc | Ảnh hưởng |
|---|---|---|
| 1 | Phân biệt **NA / MISSING / 0** trong bảng | Đổi nội dung bảng, phải chạy lại chỉ số |
| 2 | Viết lại định nghĩa theo khuôn FAS: nêu rõ phần loại trừ và quy tắc đếm | Chỉ sửa `CODEBOOK`, không chạy lại |
| 3 | Đánh dấu `lit_sol` là nhóm con **o/w** của `sol` | Chỉ sửa `CODEBOOK` |
| 4 | Sinh `metadata/ghi_chu_phuong_phap.md` và kèm vào mọi gói tải xuống | Thêm mã, không đổi số |
| 5 | Đưa `population` thành cột của bảng kinh tế, không chỉ là mẫu số | Khi cô gửi dân số |

Mục 2, 3, 4 làm được ngay và không đụng đến số liệu. Mục 1 phải chốt trước vì nó làm bảng
phải tính lại từ đầu.
