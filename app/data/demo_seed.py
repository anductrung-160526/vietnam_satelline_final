"""Số liệu GIẢ LẬP để demo giao diện khi chỉ số thật chưa tính xong.

    python3 -m app.data.demo_seed --db app/data/vngis.db

Mọi dòng ghi ra đều có trang_thai='GIA_LAP' và nguon_anh kết thúc bằng '_GIA_LAP'; giao diện
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
    from .build_indices import load_provinces, mo
    connection = mo(db)
    # Chạy demo_seed một mình cũng phải ra app dùng được: nạp luôn danh mục 63 tỉnh,
    # nếu không thì mọi truy vấn theo tỉnh trả None và giao diện trắng.
    load_provinces(connection)
    night, day, economy = [], [], []
    for index, code in enumerate(TINH):
        area = 1000 + index * 700
        base = 40 + index * 55
        previous = None; previous_hc = None
        for year in YEARS:
            viirs = year >= 2014
            source = 'VIIRS_GIA_LAP' if viirs else 'DMSP_GIA_LAP'
            # hc là chuỗi "thật" liền mạch, đã ở thang VIIRS: hiệu chỉnh xong thì không
            # được còn bước nhảy nào ở mốc 2013-2014.
            hc = round(base * 2.3 * (1 + 0.045 * (year - 2004))
                       * random.uniform(0.97, 1.03), 2)
            # sol là giá trị thô từng vệ tinh ghi được: DMSP đo trên thang DN khác hẳn,
            # nên chuỗi thô CÓ bước nhảy — đúng thứ mà hiệu chỉnh phải xoá.
            sol = hc if viirs else round((hc / 2.5) ** (1 / 1.3), 2)
            lit = area * min(0.9, 0.08 + 0.011 * (year - 2004)) * random.uniform(0.96, 1.04)
            sang = viirs
            nen = 0.5 if viirs else 0.0
            night.append((code, year, source, round(sol, 2), round(sol / area, 6),
                          None if previous is None or year == 2014
                          else round((sol - previous) / previous * 100, 2),
                          hc, round(hc / area, 6), None if previous is None
                          else round((hc - (previous_hc or hc)) / (previous_hc or hc) * 100, 2),
                          round(sol * 1.04, 2), nen, int(area * 0.3),
                          round(sol / area, 6), round(sol / area * 0.6, 6), 0.0,
                          round(sol / 9, 4), 0.6,
                          int(area * 4), int(lit) if sang else None,
                          round(lit * 0.25, 2) if sang else None,
                          round(100 * lit * 0.25 / area, 2) if sang else None,
                          round(sol * 0.8, 2) if sang else None,
                          1.5 if sang else None,
                          float(area), 'GIA_LAP',
                          'DMSP_TO_VIIRS_POWER_OVERLAP2013_v1', 'GIA_LAP'))
            previous = sol; previous_hc = hc
            if year >= 2016:
                phase = (year - 2016) / 9
                day.append((code, year, 'SENTINEL2_GIA_LAP', 'TOA' if year < 2019 else 'SR',
                            round(0.52 - 0.07 * phase + random.uniform(-.01, .01), 4), 0.11,
                            round(-0.12 + 0.09 * phase + random.uniform(-.01, .01), 4), 0.09,
                            round(-0.31 + random.uniform(-.02, .02), 4), 0.14,
                            round(0.04 + 0.03 * phase, 4), 0.08,
                            round(random.uniform(90, 99), 2), float(area) * 0.96,
                            float(area), 12, 'GIA_LAP'))
            economy.append((code, year,
                            round(900_000 * (index + 1) * math.pow(1.013, year - 2004), 0),
                            round(50_000 * (index + 1) * math.pow(1.065, year - 2004), 0),
                            None, 'GIA_LAP'))

    connection.executemany(
        'INSERT OR REPLACE INTO ntl_annual(ma_tinh,nam,nguon_anh,sol_ntl,mat_do_ntl,'
        'thay_doi_ntl,sol_ntl_hc,mat_do_ntl_hc,thay_doi_ntl_hc,'
        'sol_ntl_tho,nguong_nen,so_pixel_nen,'
        'mean_ntl,std_ntl,min_ntl,max_ntl,cv_ntl,so_pixel_hop_le,'
        'so_pixel_sang,dt_sang_km2,ty_le_sang_pct,sol_vung_sang,nguong_sang,'
        'dt_tu_nhien_km2,ghi_chu,hieu_chinh,trang_thai) VALUES('
        + ','.join('?' * 27) + ')', night)
    connection.executemany(
        'INSERT OR REPLACE INTO day_annual(ma_tinh,nam,nguon_anh,loai_phan_xa,'
        'NDVI_mean,NDVI_std,NDBI_mean,NDBI_std,MNDWI_mean,MNDWI_std,BSI_mean,BSI_std,'
        'ty_le_hop_le_pct,dt_hop_le_km2,dt_tu_nhien_km2,so_thang,trang_thai) VALUES('
        + ','.join('?' * 17) + ')', day)
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
