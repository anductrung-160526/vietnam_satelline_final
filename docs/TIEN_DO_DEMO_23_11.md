# Tiến độ và việc phải làm trước buổi demo 23/11/2026

Viết ngày 16/11/2026. Còn **7 ngày**.

Theo kế hoạch tháng 12, mốc này rơi vào cuối tuần 3 (17–23/11: bản đồ nền đêm +
ảnh ngày minh họa). Thực tế đi **nhanh hơn kế hoạch ở phần app** và **chậm hơn ở
phần ảnh ngày**.

---

## 1. Hiện trạng

Ba dấu: ✅ xong và đã kiểm · 🔶 chạy được nhưng chưa đủ · ❌ chưa có.

| Phần | Trạng thái | Ghi chú |
|---|---|---|
| Ảnh đêm DMSP 2004–2013 | ✅ | |
| Ảnh đêm VIIRS 2013–2025 theo tháng | ✅ | 9.828 dòng, 63 tỉnh, 156 mốc |
| Chỉ số đêm (`ntl_annual`, `ntl_monthly`, `ntl_panel`) | ✅ | đã qua kiểm định chất lượng |
| Hiệu chỉnh DMSP→VIIRS | ✅ | β = 1,3558 · R² = 0,8119 · 63 tỉnh |
| Cột tiếng Anh + bảng mô tả trường trong CLAUDE.md | ✅ | |
| App — màn Ảnh đêm (bản đồ, chọn tỉnh, trượt thời gian) | ✅ | đã sửa lỗi cắt ranh giới |
| App — màn Chỉ số đêm (bộ lọc, bảng, biểu đồ, CSV) | ✅ | đã tách mốc năm/tháng |
| App — màn Chỉ số kinh tế đêm (β) | 🔶 | **chạy bằng số giả lập** |
| Ảnh COG nền đêm | 🔶 | **chưa rõ đã dựng tới đâu — xem mục 2** |
| Ảnh ngày Sentinel-2 2016–2025 | 🔶 | có ảnh, **chưa tính chỉ số** |
| Chỉ số ngày (NDVI/NDBI/MNDWI/BSI) | ❌ | chưa chạy |
| Ảnh ngày Landsat 2004–2014 | ❌ | chưa tải |
| Dân số, GRDP thật | ❌ | **chờ cô cung cấp** |
| Phân loại lớp phủ 5 lớp | ❌ | chờ điểm mẫu, đã chốt ngoài phạm vi tháng 12 |
| Triển khai Cloud Run (URL công khai) | ❌ | chưa làm |
| Đo hiệu năng, chi phí (Chương 3) | ❌ | tuần 7 theo kế hoạch |

---

## 2. Rủi ro demo, xếp theo mức nguy hiểm

### 🔴 R1 — Chưa biết đã dựng được bao nhiêu ảnh COG nền đêm

Đây là **rủi ro lớn nhất**, vì bản đồ đêm là thứ cô muốn nhất và là màn đầu tiên
cô nhìn thấy. Thanh trượt thời gian lấy danh sách mốc từ bảng `cog_image`; mốc
nào không có COG thì bản đồ trống trơn ở mốc đó.

Lần gần nhất chỉ thấy dựng 12 ảnh tháng của năm 2024. Nếu đúng vậy thì demo kéo
thanh trượt sang năm khác sẽ ra bản đồ trắng.

**Kiểm ngay, trước mọi việc khác:**
```
python -m app.data.build_monthly_cogs --root E:\SatelliteData --kiem-ke
```

### 🟠 R2 — Màn thứ ba đang chạy bằng số bịa

β = 0,49 trên màn hình là con số tôi cấy vào lúc sinh dữ liệu, không có ý nghĩa
kinh tế. App có cảnh báo đỏ nên không thể nhầm, nhưng **phải chủ động nói trước
với cô** chứ đừng để cô hỏi.

### 🟠 R3 — Không có chỉ số ngày nào

Đề cương và lời cô dặn đều có phần ảnh ngày. Hiện chưa có một con số ngày nào.
Không kịp làm đủ trước thứ 2 — xem mục 3 để biết nên làm tới đâu.

### 🟡 R4 — Chuỗi tháng có tháng không quan sát được

Đã điều tra xong tuần này, kết luận: **không phải lỗi của ta**.
- 2022-07: NOAA có ảnh nhưng `cf_cvg = 0` trên toàn Hà Nội và TP.HCM — cả tháng
  vệ tinh không nhìn thấy mặt đất. Tải lại vô ích.
- 1.036 dòng (10,6%) có độ phủ dưới 80%; độ co giãn của `sol` theo độ phủ là
  **1,07**, tức mất một nửa pixel thì mất đúng một nửa `sol`.
- `cf_cvg` trung bình chỉ 1,1–1,6 lượt ngay cả tháng tốt.

Đây là chuyện phải **nói ra trong buổi demo như một phát hiện**, không phải giấu
đi như một lỗi. Chuỗi theo **năm** không bị ảnh hưởng vì lấy trung vị 12 tháng.

### 🟡 R5 — Chưa có URL công khai

Demo trên `localhost` ở máy anh. Chấp nhận được cho mốc này (kế hoạch để Cloud Run
ở tuần 6), nhưng nếu cô muốn tự mở thì chưa có.

---

## 3. Việc phải làm, theo thứ tự

Thứ tự này có chủ ý: làm từ thứ chắc chắn ảnh hưởng tới demo xuống dần.

### Hôm nay (16/11)

1. **Kiểm kê COG** — lệnh ở R1. Kết quả quyết định toàn bộ phần còn lại của tuần.
2. **Chạy lại derive để cập nhật nhãn trạng thái** (sửa lỗi `O` → `L` tuần này):
   ```
   python -m task_pipeline.local run --only night
   python -m app.data.build_indices --root E:\SatelliteData
   ```
   Không phải tăng `STATS_VERSION`, nên dùng lại kết quả cũ, chạy nhanh.

### 17–18/11 — bịt lỗ hổng bản đồ

3. **Dựng COG cho mọi năm 2004–2025.** Nếu R1 cho thấy thiếu, đây là việc nặng
   nhất tuần và phải bắt đầu ngay. Ảnh đêm nhẹ (500 m–1 km) nên dựng nhanh hơn
   ảnh ngày nhiều.
4. Mở app kiểm tay: kéo thanh trượt từ 2004 đến 2025, **mỗi mốc phải có ảnh**.
   Mốc nào trống thì hoặc dựng tiếp, hoặc ẩn khỏi thanh trượt — **đừng để bản đồ
   trắng trong lúc demo**.

### 19–20/11 — có số thật cho màn thứ ba (nếu kịp)

5. **Nhắc cô gửi dân số và GRDP.** Hỏi rõ: GRDP **giá so sánh** hay **giá hiện
   hành**? Giá hiện hành làm β bị lạm phát thổi lên — đây là thứ duy nhất có thể
   làm sai toàn bộ con số.
6. Có số thì: điền `app/data/economy_mau.csv` → lưu thành
   `data_processed/economy.csv` (ghi đè tệp giả lập) → chạy lại `build_indices`.
   Cảnh báo đỏ tự biến mất vì nó dò nhãn `GIA_LAP` trên chính cột `source`.
7. **Không có số thì giữ nguyên bản giả lập** và nói thẳng trong demo. Đừng bịa
   số không nhãn.

### 21/11 — chỉ số ngày, bản tối thiểu

8. Chạy `day_rows` cho **một năm duy nhất** (gợi ý 2024) trên cả 63 tỉnh, để có
   NDVI/NDBI/MNDWI/BSI thật mà trình bày. Làm đủ 2016–2025 **không kịp** và cũng
   không cần cho buổi này.

### 22/11 — tổng duyệt

9. Chạy toàn bộ test: `python -m pytest tests/ -q` (hiện 492 pass).
10. **Diễn thử từ đầu đến cuối trên máy sẽ dùng hôm demo**, đúng đường truyền đó,
    đúng trình duyệt đó. Tắt app, mở lại từ đầu, bấm hết mọi nút.
11. Chuẩn bị sẵn ảnh chụp màn hình của cả ba màn, phòng khi app hỏng tại chỗ.

---

## 4. Kịch bản demo đề xuất (12–15 phút)

1. **Bản đồ đêm toàn quốc** — kéo thanh trượt 2004 → 2025, cho thấy cả nước sáng
   dần. Đây là thứ cô muốn thấy nhất, để đầu tiên.
2. **Chọn một tỉnh** — gõ "Hà Nội", bản đồ cắt theo ranh giới, ba thẻ số hiện ra.
3. **Màn Chỉ số đêm** — chọn vài tỉnh, vài chỉ số, xem bảng rồi chuyển sang biểu
   đồ, bấm Tải CSV.
4. **Màn Chỉ số kinh tế đêm** — chỉ thẳng vào cảnh báo đỏ, nói rõ đang chờ số của
   cô, rồi giải thích mô hình `ln(GRDP) = α + β·ln(SOL)` đã sẵn sàng.
5. **Phát hiện về chất lượng dữ liệu** (mục R4) — trình bày như một kết quả điều
   tra, kèm con số 1,07. Đây là phần cho thấy mình hiểu dữ liệu chứ không chỉ vẽ
   được giao diện.

---

## 5. Ba câu phải hỏi cô

1. **Dân số và GRDP** — bao giờ có, và giá so sánh hay giá hiện hành?
2. **Chỉ số nhóm D** — cô đã dặn sẽ tự kiểm tra độ chính xác trước. Xin ý kiến.
3. **Phạm vi** — đề cương viết cấp xã (Bắc Ninh), đang làm cấp tỉnh toàn quốc như
   bước 1. Chốt lại để còn sửa đề cương.

---

## 6. Những việc KHÔNG làm trước thứ 2

Ghi ra để khỏi bị cuốn vào:

- **Triển khai Cloud Run.** Kế hoạch để tuần 6. Demo localhost là đủ cho mốc này.
- **Tải Landsat 2004–2014.** Mất nhiều tuần, phải chốt với cô trước khi bắt đầu.
- **Phân loại lớp phủ 5 lớp.** Chỉ có 50 điểm mẫu, không đủ huấn luyện. Đã chốt
  ngoài phạm vi.
- **Sửa điều kiện dự phòng VCMSLCFG → VCMCFG.** Mới phát hiện tuần này, có thể
  vớt lại tháng 2022-07, nhưng nó đổi nguồn ảnh của **mọi** tháng chứ không riêng
  tháng hỏng. Phải đo tác động trước. Không đụng vào trước demo.
- **Thêm cột độ phủ vào bảng.** Phải tăng `STATS_VERSION` và chạy lại toàn bộ
  derive. Để sau.
