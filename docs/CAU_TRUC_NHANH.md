# Cấu trúc nhánh git

Lập ngày 16/11/2026, sau khi phạm vi dự án thu lại **chỉ còn kinh tế đêm**.

## Sơ đồ

```
main                          CẤP 1 · chỉ nhận merge từ du-an/tich-hop
│                                     mỗi lần merge là một mốc nghiệm thu
│
├── du-an/tich-hop            CẤP 1 · nhánh dự án — nơi mọi việc phát triển gộp lại
│   ├── du-an/chi-so          CẤP 2 · task_pipeline/, derive.py, hiệu chỉnh, kiểm định
│   ├── du-an/app             CẤP 2 · app/ — API, TiTiler, giao diện web
│   ├── du-an/tai-lieu        CẤP 2 · docs/, CLAUDE.md, đặc tả, báo cáo
│   └── du-an/don-dep         CẤP 2 · tái cấu trúc repo (xem docs/CAU_TRUC_REPO.md)
│
└── luong/tich-hop            CẤP 1 · nhánh luồng — vận hành tải và dựng dữ liệu đêm
    ├── luong/viirs-thang     CẤP 2 · VIIRS DNB theo tháng 2013–2025
    ├── luong/dmsp-nam        CẤP 2 · DMSP stable_lights theo năm 2004–2013
    └── luong/cog-dem         CẤP 2 · dựng COG nền đêm cho bản đồ
```

Cả 9 nhánh đều đã tạo và đẩy lên, cùng trỏ vào trạng thái hiện tại của
`inspriring-newton`.

## Vì sao cấp 1 lại có đuôi `/tich-hop`

Git **không cho** một nhánh tên `du-an` tồn tại cùng lúc với `du-an/app`: trong
`.git/refs/heads/`, `du-an` không thể vừa là tệp vừa là thư mục. Thử tạo là git từ
chối thẳng.

Nên nhánh cấp 1 phải mang tên hai phần. `du-an/tich-hop` vừa hợp lệ, vừa giữ đúng
thứ bậc nhìn thấy được, và GitHub tự gom chúng thành nhóm trong danh sách nhánh.

## Luật di chuyển

```
du-an/<việc>  --merge-->  du-an/tich-hop  --merge-->  main
luong/<việc>  --merge-->  luong/tich-hop  --merge-->  du-an/tich-hop
```

- Không commit thẳng vào `main` và hai nhánh `tich-hop`.
- `luong/tich-hop` đổ vào `du-an/tich-hop` chứ không đổ thẳng vào `main`: việc tải
  dữ liệu hay kéo theo thay đổi code trong `task_pipeline/`, phải đi qua chỗ có
  test chạy trước.
- Nhánh cấp 2 xong việc thì merge rồi **xoá**. Nhánh cấp 2 sống lâu không merge
  chính là thứ đã đẻ ra mớ `vngis-tinh-*` hiện nay.

## Vì sao luồng chia theo loại dữ liệu, không chia theo tài khoản

CLAUDE.md đã chốt: mười luồng Earth Engine **không cần nhánh git riêng**. Mười tài
khoản chạy từ cùng một checkout, chia việc bằng tham số `--shard i/n`. Nhánh riêng
cho mỗi tài khoản không giải quyết gì mà chỉ tạo mười bản sao phải đồng bộ.

Vì vậy `luong/` chia theo **loại dữ liệu đêm**, là thứ thật sự khác nhau về code
và về cách kiểm.

## Hiện trạng các nhánh cũ

| Nhánh | Tình trạng | Đề xuất |
|---|---|---|
| `inspriring-newton` | nhánh đang làm việc, **đi trước `main` 116 commit** | giữ tới khi `du-an/tich-hop` thay hẳn |
| `main` | **cũ 3 tuần**, lần merge cuối 24/10 | merge `du-an/tich-hop` vào sau demo |
| `vngis-tinh-001-011` | đã nằm trọn trong `inspriring-newton` | xoá được, không mất gì |
| `vngis-tinh-012-022` … `054-063` | 5 bản sao chỉ khác nhau ở khoảng tỉnh (13 tệp, 23 dòng) | xoá sau khi đối chiếu |
| `vngis-ee-07` | 5 commit riêng, chưa vào đâu | đối chiếu rồi xoá |
| `vngis-ee-districts-202407-202506` | đời cấp huyện, đã bỏ | xoá |
| `claude/inspiring-newton-uj5vub` | nhánh tạm sinh tự động | xoá |
| `boundary-check-results` | CI tự ghi kết quả vào đây | **giữ** — không phải nhánh code |

**Chưa xoá nhánh nào.** Xoá nhánh từ xa là việc không lùi lại được dễ dàng, nên
chờ anh gật từng dòng một.

### Điều phải kiểm trước khi xoá

5 nhánh `vngis-tinh-*` mỗi nhánh có 20 commit mà `inspriring-newton` không có. Phần
lớn gần như chắc chắn là code cũ đã bị thay, nhưng **chưa đối chiếu từng cái**.
Trước khi xoá phải chạy:

```bash
git log --oneline origin/inspriring-newton..origin/vngis-tinh-054-063
git diff --stat origin/inspriring-newton origin/vngis-tinh-054-063
```

Nếu chỉ khác ở khoảng tỉnh và code cũ thì xoá an toàn.

## Ảnh hưởng của việc thu phạm vi về chỉ kinh tế đêm

Phạm vi mới làm một số việc trong kế hoạch **mất hiệu lực**, phải xử lý chứ không
để lửng lơ:

1. **Chỉ số ngày (NDVI/NDBI/MNDWI/BSI) ra khỏi phạm vi.** Việc "21/11 chạy chỉ số
   ngày một năm" trong `docs/TIEN_DO_DEMO_23_11.md` nên bỏ. Đây là phần nặng nhất
   còn lại, bỏ được là tuần demo nhẹ hẳn.
2. **Landsat 2004–2014 không phải tải nữa.** Trước đây đây là rủi ro nhiều tuần.
3. **Lớp phủ 5 lớp chính thức hết hiệu lực**, không còn là "để sau" nữa.
4. **CLAUDE.md phải sửa**: các mục về ảnh ngày, Sentinel-2 TOA/L2A, cột lớp phủ
   hiện vẫn đang là quy tắc bắt buộc. Để nguyên là mâu thuẫn với phạm vi mới.
5. **Màn "Ảnh ngày" trong đặc tả** (`docs/DAC_TA_MAN_HINH.md`) cần quyết: bỏ hẳn,
   hay giữ dạng minh họa như cô đã dặn.

Mục 4 và 5 nên làm trên `du-an/tai-lieu`, nhưng **chờ anh xác nhận từng mục** —
đây là đổi phạm vi đã chốt với cô, không phải việc tôi tự quyết.
