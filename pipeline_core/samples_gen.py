# -*- coding: utf-8 -*-
"""
Bộ điểm mẫu kiểm chứng mặt đất (Ground Truth Samples) phân loại 5 lớp phủ tại Việt Nam
Đại diện cho 5 vùng sinh thái chính: ĐBSH, ĐBSCL, Tây Nguyên, Miền núi phía Bắc, Duyên hải miền Trung.
"""
import sys
import json
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SAMPLE_POINTS = [
    # --- LỚP 1: ĐẤT NÔNG NGHIỆP (Cropland / Agriculture) ---
    {"lon": 105.820, "lat": 20.450, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Hồng (Hà Nam)"},
    {"lon": 106.120, "lat": 20.350, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Hồng (Nam Định)"},
    {"lon": 106.350, "lat": 20.520, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Hồng (Thái Bình)"},
    {"lon": 105.450, "lat": 10.350, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Cửu Long (An Giang)"},
    {"lon": 105.750, "lat": 10.050, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Cửu Long (Cần Thơ)"},
    {"lon": 105.650, "lat": 10.550, "class": 1, "class_name": "Đất nông nghiệp", "region": "Đồng bằng sông Cửu Long (Đồng Tháp)"},
    {"lon": 107.980, "lat": 12.650, "class": 1, "class_name": "Đất nông nghiệp", "region": "Tây Nguyên (Cà phê Đắk Lắk)"},
    {"lon": 108.020, "lat": 13.980, "class": 1, "class_name": "Đất nông nghiệp", "region": "Tây Nguyên (Hồ tiêu Gia Lai)"},
    {"lon": 105.780, "lat": 19.820, "class": 1, "class_name": "Đất nông nghiệp", "region": "Bắc Trung Bộ (Thanh Hóa)"},
    {"lon": 108.850, "lat": 15.250, "class": 1, "class_name": "Đất nông nghiệp", "region": "Duyên hải miền Trung (Quảng Ngãi)"},

    # --- LỚP 2: ĐÔ THỊ VÀ DỊCH VỤ (Urban / Built-up) ---
    {"lon": 105.850, "lat": 21.030, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Hà Nội (Khu vực trung tâm)"},
    {"lon": 105.780, "lat": 21.010, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Hà Nội (Khu vực Cầu Giấy/Nam Từ Liêm)"},
    {"lon": 106.680, "lat": 10.770, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "TP. Hồ Chí Minh (Quận 1)"},
    {"lon": 106.720, "lat": 10.820, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "TP. Hồ Chí Minh (TP. Thủ Đức)"},
    {"lon": 108.220, "lat": 16.060, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Đà Nẵng (Hải Châu)"},
    {"lon": 106.680, "lat": 20.860, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Hải Phòng (Hồng Bàng)"},
    {"lon": 106.750, "lat": 10.950, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Bình Dương (Khu công nghiệp VSIP)"},
    {"lon": 106.900, "lat": 10.950, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Đồng Nai (Khu công nghiệp Biên Hòa)"},
    {"lon": 107.080, "lat": 20.950, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Quảng Ninh (Hạ Long)"},
    {"lon": 105.780, "lat": 10.030, "class": 2, "class_name": "Đô thị và dịch vụ", "region": "Cần Thơ (Ninh Kiều)"},

    # --- LỚP 3: RỪNG (Forest) ---
    {"lon": 103.850, "lat": 22.350, "class": 3, "class_name": "Rừng", "region": "Tây Bắc (Vườn quốc gia Hoàng Liên Sơn)"},
    {"lon": 104.950, "lat": 21.950, "class": 3, "class_name": "Rừng", "region": "Đông Bắc (Rừng Yên Bái)"},
    {"lon": 105.710, "lat": 20.320, "class": 3, "class_name": "Rừng", "region": "Rừng Cúc Phương (Ninh Bình)"},
    {"lon": 106.250, "lat": 17.520, "class": 3, "class_name": "Rừng", "region": "Vườn quốc gia Phong Nha - Kẻ Bàng"},
    {"lon": 107.850, "lat": 16.200, "class": 3, "class_name": "Rừng", "region": "Vườn quốc gia Bạch Mã (Thừa Thiên Huế)"},
    {"lon": 108.350, "lat": 14.500, "class": 3, "class_name": "Rừng", "region": "Tây Nguyên (Vườn quốc gia Kon Ka Kinh)"},
    {"lon": 108.450, "lat": 12.150, "class": 3, "class_name": "Rừng", "region": "Tây Nguyên (Vườn quốc gia Bidoup Núi Bà)"},
    {"lon": 107.420, "lat": 11.450, "class": 3, "class_name": "Rừng", "region": "Đông Nam Bộ (Vườn quốc gia Cát Tiên)"},
    {"lon": 104.980, "lat": 19.350, "class": 3, "class_name": "Rừng", "region": "Bắc Trung Bộ (Vườn quốc gia Pù Mát, Nghệ An)"},
    {"lon": 105.020, "lat": 8.650, "class": 3, "class_name": "Rừng", "region": "Đồng bằng sông Cửu Long (Vườn quốc gia Mũi Cà Mau)"},

    # --- LỚP 4: MẶT NƯỚC (Water Bodies) ---
    {"lon": 105.150, "lat": 21.800, "class": 4, "class_name": "Mặt nước", "region": "Hồ Thác Bà (Yên Bái)"},
    {"lon": 105.250, "lat": 20.850, "class": 4, "class_name": "Mặt nước", "region": "Hồ Hòa Bình"},
    {"lon": 105.720, "lat": 19.650, "class": 4, "class_name": "Mặt nước", "region": "Hồ Cửa Đạt (Thanh Hóa)"},
    {"lon": 107.020, "lat": 11.350, "class": 4, "class_name": "Mặt nước", "region": "Hồ Trị An (Đồng Nai)"},
    {"lon": 106.180, "lat": 11.350, "class": 4, "class_name": "Mặt nước", "region": "Hồ Dầu Tiếng (Tây Ninh)"},
    {"lon": 105.900, "lat": 21.050, "class": 4, "class_name": "Mặt nước", "region": "Sông Hồng (Đoạn qua Hà Nội)"},
    {"lon": 105.950, "lat": 10.250, "class": 4, "class_name": "Mặt nước", "region": "Sông Tiền (Vĩnh Long)"},
    {"lon": 105.520, "lat": 9.950, "class": 4, "class_name": "Mặt nước", "region": "Sông Hậu (Cần Thơ)"},
    {"lon": 107.600, "lat": 16.550, "class": 4, "class_name": "Mặt nước", "region": "Đầm phá Tam Giang - Cầu Hai (Huế)"},
    {"lon": 107.050, "lat": 20.850, "class": 4, "class_name": "Mặt nước", "region": "Vịnh Hạ Long (Quảng Ninh)"},

    # --- LỚP 5: ĐẤT KHÁC (Barren / Other) ---
    {"lon": 108.550, "lat": 11.600, "class": 5, "class_name": "Đất khác", "region": "Đồi cát ven biển Ninh Thuận"},
    {"lon": 108.350, "lat": 11.050, "class": 5, "class_name": "Đất khác", "region": "Đồi cát Mũi Né (Bình Thuận)"},
    {"lon": 106.650, "lat": 17.550, "class": 5, "class_name": "Đất khác", "region": "Bãi cát ven biển Quảng Bình"},
    {"lon": 103.550, "lat": 22.450, "class": 5, "class_name": "Đất khác", "region": "Núi đá trơ trọi vùng cao Lai Châu"},
    {"lon": 105.250, "lat": 23.250, "class": 5, "class_name": "Đất khác", "region": "Cao nguyên đá Đồng Văn (Hà Giang)"},
    {"lon": 107.350, "lat": 21.450, "class": 5, "class_name": "Đất khác", "region": "Bãi bồi cửa sông Quảng Ninh"},
    {"lon": 106.850, "lat": 10.450, "class": 5, "class_name": "Đất khác", "region": "Bãi cát biển Cần Giờ"},
    {"lon": 109.150, "lat": 12.350, "class": 5, "class_name": "Đất khác", "region": "Bán đảo Cam Ranh (Khánh Hòa)"},
    {"lon": 108.750, "lat": 14.150, "class": 5, "class_name": "Đất khác", "region": "Đất trống sau khai thác mỏ Gia Lai"},
    {"lon": 105.950, "lat": 20.250, "class": 5, "class_name": "Đất khác", "region": "Vùng mỏ đá Tam Điệp (Ninh Bình)"}
]

def generate_sample_dataset(samples_dir):
    """
    Tạo tệp GeoJSON và CSV chứa bộ điểm mẫu kiểm chứng mặt đất
    """
    samples_dir = Path(samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)

    # 1. Xuất CSV
    df = pd.DataFrame(SAMPLE_POINTS)
    csv_file = samples_dir / "ground_truth_samples.csv"
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")

    # 2. Xuất GeoJSON
    features = []
    for pt in SAMPLE_POINTS:
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [pt["lon"], pt["lat"]]
            },
            "properties": {
                "class": pt["class"],
                "class_name": pt["class_name"],
                "region": pt["region"]
            }
        }
        features.append(feat)

    geojson_data = {
        "type": "FeatureCollection",
        "name": "Vietnam_LandCover_GroundTruth_5Classes",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": features
    }

    geojson_file = samples_dir / "ground_truth_samples.geojson"
    with open(geojson_file, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    print(f"[*] Đã khởi tạo {len(SAMPLE_POINTS)} điểm mẫu kiểm chứng 5 lớp phủ tại: {samples_dir}")
    return geojson_file
