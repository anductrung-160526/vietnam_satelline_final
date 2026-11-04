# Thư viện phía trình duyệt (bản cố định, lưu trong repo)

| Tệp | Gói npm | Phiên bản | Giấy phép |
|---|---|---|---|
| `maplibre-gl.js`, `maplibre-gl.css` | `maplibre-gl` | 4.7.1 | BSD-3-Clause |
| `echarts.min.js` | `echarts` | 5.5.1 | Apache-2.0 |

Để trong repo thay vì gọi CDN vì:
- app chạy được khi mạng phòng thí nghiệm chặn CDN (đã gặp thật khi kiểm thử);
- phiên bản cố định, không bị CDN đổi dưới chân;
- không có yêu cầu ra miền ngoài khi cô mở trang.

Cập nhật:

    npm pack maplibre-gl@<phiên bản> echarts@<phiên bản>
    tar -xzf <tệp>.tgz && cp package/dist/... app/web/vendor/

Rồi sửa bảng trên. Không chỉnh sửa nội dung các tệp này.
