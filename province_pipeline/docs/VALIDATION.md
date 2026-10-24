# Validation và giới hạn bàn giao

## Đã kiểm tra trong Linux cloud

- Suite unittest gồm regression cũ và test mới cho quota/reservation, nhóm tỉnh, paths, resume submit, receipt ordering, checksum, local corruption, ổ đầy, mất nguồn sau delete và aggregate CSV/XLSX/DTA.
- Agent được kiểm tra bằng Drive giả lập; không dùng kết quả mock như bằng chứng Google API thật hoạt động.
- Kiểm tra TIFF synthetic đúng lưới/CRS/bands/nodata, đọc mọi block; không phải ảnh vệ tinh thật.
- Boundary fixture synthetic dùng trong test kiểm tra schema/hash/tile jobs, không được sử dụng như ranh giới sản xuất.

Lệnh tái hiện:

```bash
python -m pip install -r province_pipeline/requirements.txt
python -m pip check
python -m unittest discover -s tests -v
python -m province_pipeline --help
```

## Chưa được kiểm tra, không tuyên bố hoàn tất pilot thật

1. Earth Engine compute/download thực tế, rclone refresh token và upload bằng tài khoản Drive từ hai secret hiện có. Backend batch nâng cao cũng chưa có pilot thật.
2. Quota thực tế, quyền sở hữu file, refresh token lâu dài, HTTP ETag và conditional permanent delete trên tài khoản người dùng.
3. Chứng nhận pháp lý/diện tích của bộ ranh giới 2024. Bộ GADM 4.1 thật đã tải từ nguồn, xác nhận hash, đủ 63 tỉnh và mã, hình học hợp lệ; không coi đó là xác nhận pháp lý.
4. Windows Task Scheduler, volume identity và tải/xóa trên ổ E thật.
5. Độ chính xác khoa học của NTL, bộ lọc transient light, phân loại đất và harmonization.

Cấu hình mặc định pause=true, allow_remote_delete=false, chỉ chọn Hà Nội 2024. Không tự tải toàn quốc hoặc xóa dữ liệu Drive trong lúc phát triển. Chạy pilot theo SETUP_VI.md trước khi bật xóa và mở rộng.

Split auth, CI materialization, direct recovery và BOM config được kiểm thử offline. Không có quyền đọc giá trị GitHub Secrets để chạy probe trong môi trường cloud chat. Người dùng chạy workflow check_only bằng chính GitHub runner để xác minh quyền thật.

## Regression: Earth Engine download parameter combination

Direct TIFF download uses `crs + crs_transform + dimensions`, without `region` or
`scale`. The affine origin and pixel dimensions define the exact tile rectangle.
The actual Earth Engine Python SDK validator is exercised offline: the corrected
combination is accepted and the previous combination with region is rejected.
The TIFF payload test still checks its transform, dimensions, bands and NoData.
This validates request construction, not a completed live satellite download.

## Projection parsing diagnostic

EE requests now spell out EPSG:6933 as OGC WKT1_GDAL at download, reduction, and
batch-export boundaries. The raster grid, transform, statistical CRS label and job
identity remain unchanged. Local tests verify the WKT round-trip equals EPSG:6933
and accept equivalent WKT in received TIFFs; they do not prove live EE support.
Preflight additionally calls the live projection nominalScale and constructs a
4×4 constant-image exact-grid download request. It does not print the signed URL,
retrieve satellite pixels, upload to Drive, or delete files. Require this probe
PASS before retrying the satellite workflow after a projection parsing error.

## Layout 2

Tests kiểm tra tỉnh nằm đúng cấp, không đổi job IDs khi đổi đường dẫn, nhiều output dùng chung thư mục không nhầm lô, migration giữ nguyên file ID và khôi phục sau mất phản hồi, nhận lại dữ liệu local cũ không tải trùng, và aggregate bảng riêng từng tỉnh. Drive relocation thật cần chạy mode organize_only trên GitHub bằng secret hiện có; không tuyên bố đã di chuyển dữ liệu từ môi trường cloud chat.

## Flat TIFF layout 3

Ảnh nguồn và trung gian đều có thư mục cha trực tiếp là tỉnh. Tests xác nhận nhiều năm/tháng dùng chung thư mục nhưng không trùng tên, giữ nguyên job ID, chuyển lô layout 2 đã hoàn tất hoặc đang chuyển dở, và di chuyển TIFF local khỏi thư mục năm mà giữ nguyên MD5/SHA-256. Đây là kiểm thử offline; Drive chỉ thay đổi khi người dùng chạy organize_only bằng credentials thật.

## Worker finalization

Regression tests kiểm tra RESERVED + report UPLOADED chỉ thành REMOTE_READY khi file ID/checksum khớp, manifest được lưu trước state READY, thiếu report/output không bị coi là hoàn tất, không cấp job mới khi reconcile_only, và không ghi đè state đang MIGRATING hoặc state chưa tồn tại. Finalizer chạy sau matrix trong cùng concurrency group. Live handoff cần chạy trên GitHub với credentials thực tế.

## Windows task launch

Task registration now persists absolute paths including rclone.exe; receiver logs each invocation to a per-user transcript and preserves the Python exit code. Windows Task Scheduler and PowerShell transcript execution cannot be validated on this Linux machine. Python receiver diagnostics are covered by tests ensuring only constant error codes are logged, with no raw API/credential response content.

## Conditional Drive delete fallback

Tests cover the Drive v2 File ETag fallback when v3 omits the header, exact-ID
conditional delete through the same API version, mismatched content/version/name/
parents, a race between metadata reads, absence of both validators, and no retry
without If-Match after precondition failure. The installed official discovery
schema confirms the v2 fields used exist. Live deletion with the user's Drive
credentials remains to be checked on Windows; no source was deleted by these tests.

## V2: fixed-source panels and two sample profiles (2026-10-24)

- Offline regression suite plus V2 tests verify priority barriers, round-robin dispatch, bounded inventory, retries, source selection, nulls, expected row counts, same-source growth, full-year completeness, verified mutable CSV snapshots and safe local replacement.
- Real EE SDK algorithm signatures serialize the LANDSAT, SENTINEL2, DMSP and VIIRS processing graphs, including Cloud Score+ joins, fire masks and reducers. This checks client graph construction, **not** live asset availability, EE permissions, server execution or scientific accuracy.
- Actual pinned GADM geometry dry-plan: Hanoi 2025 → 24 night-image jobs, 24 statistics jobs, 52 annual-day-image tile jobs. Full empty panels → 9,702 night rows and 16,632 day rows, built in about 1.4 seconds in this environment.
- No EE or Drive runtime credentials are injected here. GitHub Actions API read returned Forbidden. Therefore no live Hanoi 2025 run, dispatch or Windows scheduling is claimed by this change. User must start the provided test profile and inspect DATA_STATUS/QA.
- No validated DMSP–VIIRS calibration, complete ship-light removal or land-cover classification is claimed. Their limitations are explicitly recorded in delivered metadata and the run guide.

## Raw diagnostic mode (2026-10-25)

- 177 offline tests passed. New tests build actual EE SDK raw graphs for four sources and check that QA_PIXEL/QA_RADSAT, Cloud Score+, fire and observation-threshold filters do not occur. Verify low-coverage numeric retention, per-band denominators, no strict-mask reprocessing in raw mode, no filtered duplicate jobs, empty-image terminal status, CSV backups/recovery and readable PNG diagnostics without editing TIFF bytes.
- Default workflow processing is `raw_source`; explicit `quality_filtered` remains available. Actual GADM dry-plan for Hanoi 2025: 12 source night TIFF jobs, 24 table jobs, 52 unfiltered annual day composite TIFF jobs. Counts are plans, not evidence that every tile has valid pixels.
- CSV screenshot PENDING means statistics not computed yet. Existing >=80% coverage gate can suppress filtered-mode indices; that gate does not apply in raw mode. No conclusion is drawn about the supplied screenshot TIFF's actual pixels because its binary was not provided/accessed.
- GitHub Actions API again returned Forbidden; live EE/Drive run and user-specific TIFF diagnostics remain unverified. PNG/JSON artifacts and `inspect-tiff` provide the next concrete checks. Processing preserves native catalog masks, physical scaling, clipping/grid and required composites; it is not a download of untouched sensor scenes.

## Six fixed province branches / Task123 (2026-10-25)

- Offline suite: 193 tests pass. Tests cover all 63 ordinal numbers exactly once, six non-overlapping ranges, first-province pilot, fixed project `vngis-ee-2`, pilot/full scientific identity reuse, monthly image generation, source/year selection, explicit notebook exclusive-end dates, window/collection provenance, Task3 formulas and long-run multiple batches without workflow redispatch.
- EE SDK graph comparison verifies Task1 notebook QA60 mask/band scaling and four index expressions against the supplied cell sources, not a hand-written mock implementation. Four source graphs serialize with the intended reducers; no live EE credentials are available here.
- Exact WGS84 tiled grids are validated independently from nominal metre scale. Float64 preservation and lossless DEFLATE round-trip preserve exact pixels, band descriptions, NoData and grid. Receiver continues other branch roots when one fails, under the existing external-volume and checksum/conditional-delete guards.
- Shared project quota and six fixed staging budget shares are retained. New branch workflows loop within one runner; continuation occurs only near the 315-minute runner budget. API access remains Forbidden, so no claim is made that workflows were dispatched, old active runs canceled or scientific completeness validated remotely.
- Uploaded notebooks are stored without outputs. Province-level adaptation and historical Landsat/DMSP extension are documented explicitly. DN/VIIRS radiance and TOA/SR remain unharmonized; missing inputs remain null, not synthetic zero.
