"""Số liệu GIẢ LẬP để demo giao diện khi chỉ số thật chưa tính xong.

    python3 -m app.data.demo_seed --db app/data/vngis.db

Mọi dòng ghi ra đều có status='GIA_LAP' và nguon_anh kết thúc bằng '_GIA_LAP'; giao diện
dựa vào đó để treo biển báo đỏ. Khi chỉ số thật có rồi, chạy lại build_indices.py là các
dòng này bị xoá sạch (build_indices DELETE toàn bảng trước khi nạp).

KHÔNG dùng số từ đây cho báo cáo, slide hay bất cứ kết luận nào.
"""
import argparse
import math
import random
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
TINH = ['01', '27', '48', '79', '92']            # Hà Nội, Bắc Ninh, Đà Nẵng, TP.HCM, Cần Thơ
YEARS = range(2004, 2026)


def seed(db, seed_value=20261104):
    random.seed(seed_value)
    connection = sqlite3.connect(db)
    connection.executescript((HERE / 'schema.sql').read_text(encoding='utf-8'))
    night, day, economy = [], [], []
    for index, code in enumerate(TINH):
        area = 1000 + index * 700
        base = 40 + index * 55
        previous = None
        for year in YEARS:
            source = 'DMSP_GIA_LAP' if year <= 2013 else 'VIIRS_GIA_LAP'
            scale = 1.0 if year <= 2013 else 2.3        # bậc nhảy đổi vệ tinh, cố ý để thấy
            sol = base * scale * (1 + 0.045 * (year - 2004)) * random.uniform(0.95, 1.05)
            lit = area * min(0.9, 0.08 + 0.011 * (year - 2004)) * random.uniform(0.96, 1.04)
            night.append((code, year, source, round(sol, 2), round(sol / area, 4),
                          None if previous is None else round((sol - previous) / previous * 100, 2),
                          round(sol / area, 4), round(sol / area * 0.3, 4), 0.0,
                          round(sol / 50, 3), round(sol * 0.8, 2), round(lit, 0), 1.5,
                          float(area), 'GIA_LAP', 'CHUA_HIEU_CHINH', 'GIA_LAP'))
            previous = sol
            if year >= 2016:
                phase = (year - 2016) / 9
                day.append((code, year, 'SENTINEL2_GIA_LAP',
                            round(0.52 - 0.07 * phase + random.uniform(-.01, .01), 4), 0.11,
                            round(-0.12 + 0.09 * phase + random.uniform(-.01, .01), 4), 0.09,
                            round(-0.31 + random.uniform(-.02, .02), 4), 0.14,
                            round(0.04 + 0.03 * phase, 4), 0.08,
                            round(random.uniform(0.9, 0.99), 3), float(area), 10.0,
                            'GIA_LAP', 'GIA_LAP'))
            economy.append((code, year,
                            round(900_000 * (index + 1) * math.pow(1.013, year - 2004), 0),
                            round(50_000 * (index + 1) * math.pow(1.065, year - 2004), 0),
                            None, 'GIA_LAP'))

    connection.executemany(
        'INSERT OR REPLACE INTO ntl_annual(ma_tinh,nam,nguon_anh,sol_ntl,mat_do_ntl,thay_doi_ntl,'
        'rad_mean,rad_stdDev,rad_min,rad_max,lit_sol,lit_pixels,lit_threshold,dien_tich_km2,'
        'phuong_phap,hieu_chinh,status) VALUES(' + ','.join('?' * 17) + ')', night)
    connection.executemany(
        'INSERT OR REPLACE INTO day_annual(ma_tinh,nam,nguon_anh,NDVI_mean,NDVI_stdDev,'
        'NDBI_mean,NDBI_stdDev,MNDWI_mean,MNDWI_stdDev,BSI_mean,BSI_stdDev,'
        'ty_le_pixel_hop_le,dien_tich_km2,scale_m,phuong_phap,status) VALUES('
        + ','.join('?' * 16) + ')', day)
    connection.executemany(
        'INSERT OR REPLACE INTO kinh_te(ma_tinh,nam,dan_so,gdp,grdp_bq_dau_nguoi,nguon) '
        'VALUES(?,?,?,?,?,?)', economy)
    connection.commit()
    connection.close()
    return {'ntl_annual': len(night), 'day_annual': len(day), 'kinh_te': len(economy),
            'tinh': TINH}


def main():
    parser = argparse.ArgumentParser(description='Nạp số liệu GIẢ LẬP để demo giao diện')
    parser.add_argument('--db', default=str(HERE / 'vngis.db'))
    report = seed(parser.parse_args().db)
    print('ĐÃ NẠP SỐ LIỆU GIẢ LẬP (status=GIA_LAP) cho các tỉnh', ', '.join(report['tinh']))
    print('  ntl_annual %(ntl_annual)d dòng · day_annual %(day_annual)d · kinh_te %(kinh_te)d' % report)
    print('  Không dùng cho báo cáo. Chạy build_indices.py để thay bằng số liệu thật.')


if __name__ == '__main__':
    main()
