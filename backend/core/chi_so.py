"""Chỉ số và công thức mà lớp web dùng — trích từ backend/core/chi_so.py.

Nhánh night-app chỉ chạy ứng dụng, không chạy luồng tải ảnh. derive.py gốc dài 875
dòng, trong đó 718 dòng là việc lọc ảnh VIIRS, dựng ảnh năm, tính thống kê raster —
nhánh này không dùng tới. Tệp này giữ đúng phần lớp web gọi:

  do_co_gian      hệ số co giãn ánh sáng-GRDP, màn "Chỉ số kinh tế đêm"
  ham_thoi_gian   bốn hàm thời gian của bộ lọc, theo lối World Bank DataBank
  CODEBOOK        nguồn duy nhất sinh ra bảng mô tả trường trong CLAUDE.md

CÔNG THỨC KHÔNG ĐƯỢC SỬA RỜI Ở ĐÂY. Bảng số liệu do nhánh pipeline sinh ra; đổi
công thức một bên mà không đổi bên kia thì cột trong bảng và con số trên màn hình
nói hai chuyện khác nhau mà không có gì báo lỗi.
"""
import math


# ---------------------------------------------------------------- kinh tế đêm
# Cô dặn: dùng GRDP theo tỉnh, hồi quy logarit để tìm beta, KHÔNG cần phần phức tạp khác.
#
#     ln(GRDP) = alpha + beta * ln(SOL)
#
# beta là độ co giãn: ánh sáng tăng 1% thì GRDP tăng beta phần trăm.
TOI_THIEU_QUAN_SAT = 10      # dưới mức này thì hệ số không nói lên điều gì


TOI_THIEU_QUAN_SAT_TINH = 8  # beta riêng từng tỉnh cần ít nhất ngần này năm


def _ols_log(cap):
    """Bình phương nhỏ nhất trên log–log. cap: [(sol, grdp)], chỉ nhận cả hai đều dương."""
    diem=[(math.log(x),math.log(y)) for x,y in cap
          if x is not None and y is not None and x>0 and y>0]
    n=len(diem)
    if n<2:return None
    mx=sum(a for a,_ in diem)/n
    my=sum(b for _,b in diem)/n
    sxx=sum((a-mx)**2 for a,_ in diem)
    if sxx==0:return None
    beta=sum((a-mx)*(b-my) for a,b in diem)/sxx
    alpha=my-beta*mx
    du=sum((b-(alpha+beta*a))**2 for a,b in diem)
    tong=sum((b-my)**2 for _,b in diem)
    return {'beta':round(beta,6),'alpha':round(alpha,6),
            'r2':round(1-du/tong,6) if tong else None,'n':n}


def do_co_gian(rows,gia_so_sanh=None):
    """Độ co giãn ánh sáng–GRDP, gộp mọi tỉnh-năm, kèm beta riêng từng tỉnh.

    rows: mỗi phần tử có province_code, sol, grdp. Dòng thiếu hoặc không dương bị bỏ:
    log của số không dương không tồn tại, và một tỉnh tối om không nói gì về quan hệ này.

    gia_so_sanh=False -> vẫn tính nhưng gắn cảnh báo: GRDP giá hiện hành làm beta bị lạm
    phát thổi lên, vì GRDP danh nghĩa tăng một phần chỉ vì giá còn ánh sáng không phản
    ứng với giá. Đây là thứ duy nhất có thể làm sai toàn bộ con số beta.
    """
    cap=[(r.get('sol'),r.get('grdp')) for r in rows]
    chung=_ols_log(cap)
    if chung is None or chung['n']<TOI_THIEU_QUAN_SAT:
        return {'beta':None,'alpha':None,'r2':None,'n':chung['n'] if chung else 0,
                'theo_tinh':{},'canh_bao':[
                    f'Dưới {TOI_THIEU_QUAN_SAT} quan sát hợp lệ, không ước lượng được.']}
    theo_tinh={}
    nhom={}
    for r in rows:
        nhom.setdefault(r.get('province_code'),[]).append((r.get('sol'),r.get('grdp')))
    for ma,cua in nhom.items():
        mot=_ols_log(cua)
        if mot and mot['n']>=TOI_THIEU_QUAN_SAT_TINH:
            theo_tinh[ma]={'beta':mot['beta'],'r2':mot['r2'],'n':mot['n']}
    canh=[]
    if gia_so_sanh is False:
        canh.append('GRDP đang ở GIÁ HIỆN HÀNH: beta bị lạm phát thổi lên. '
                    'Phải khử lạm phát trước khi trích con số này vào báo cáo.')
    elif gia_so_sanh is None:
        canh.append('Chưa biết GRDP ở giá so sánh hay giá hiện hành. '
                    'Giá hiện hành làm beta sai lệch — xác nhận trước khi dùng.')
    if chung['r2'] is not None and chung['r2']<0.5:
        canh.append(f"R² = {chung['r2']:.2f} thấp: quan hệ ánh sáng–GRDP yếu trên bộ dữ "
                    'liệu này, không nên rút kết luận định lượng.')
    return dict(chung,theo_tinh=theo_tinh,canh_bao=canh)


# ---------------------------------------------------------------- hàm thời gian
# Theo "Create Time Function" của World Bank DataBank: rút một chuỗi thành MỘT con số
# cho khoảng người dùng chọn, hiện thành một cột phụ bên phải bảng.
#
# Đặc tả ban đầu liệt kê năm hàm, trong đó "trung bình trượt 3 kỳ" và "chỉ số gốc = 100"
# là phép biến đổi CHUỖI chứ không rút về một số, nên không phải hàm thời gian theo nghĩa
# này. Trung bình trượt đã có sẵn thành cột riêng (sol_ma3); chỉ số gốc nằm ngoài phạm vi.
HAM_THOI_GIAN = {
    'tong':       'Tổng trong khoảng',
    'trung_binh': 'Trung bình trong khoảng',
    'thay_doi':   'Thay đổi toàn kỳ (%)',
    'cagr':       'Tốc độ tăng trưởng bình quân năm (%)',
}


def nam_thap_phan(moc):
    """'2010' -> 2010.0 · '2024-07' -> 2024.5 (giữa tháng 7). Sai định dạng -> None."""
    text=str(moc or '').strip()
    if len(text)==4 and text.isdigit():return float(text)
    if len(text)==7 and text[4]=='-' and text[:4].isdigit() and text[5:].isdigit():
        thang=int(text[5:])
        if 1<=thang<=12:return int(text[:4])+(thang-0.5)/12
    return None


def ham_thoi_gian(ten,moc,gia_tri):
    """Một con số cho cả khoảng, hoặc None khi không tính được.

    Trả None chứ không trả 0: 0 là một kết quả hợp lệ, dùng nó cho "không tính được"
    là nói sai. Các trường hợp không tính được:
      - dưới hai điểm có số liệu (thay_doi, cagr)
      - giá trị đầu kỳ bằng hoặc dưới 0 (chia cho nó thì vô nghĩa)
      - khoảng thời gian bằng 0 (cagr)
    """
    if ten not in HAM_THOI_GIAN:raise ValueError(f'Không có hàm thời gian {ten!r}')
    cap=[(nam_thap_phan(m),v) for m,v in zip(moc,gia_tri)
         if v is not None and nam_thap_phan(m) is not None]
    cap.sort()
    if not cap:return None
    so=[v for _,v in cap]
    if ten=='tong':return round(sum(so),4)
    if ten=='trung_binh':return round(sum(so)/len(so),4)
    if len(cap)<2 or so[0]<=0:return None
    if ten=='thay_doi':return round(100*(so[-1]/so[0]-1),4)
    khoang=cap[-1][0]-cap[0][0]
    if khoang<=0:return None
    return round(100*((so[-1]/so[0])**(1/khoang)-1),4)


CODEBOOK=[
 # --- Định danh và thời gian ---
 ('province_code','Mã tỉnh, thành phố theo Cục Thống kê (63 tỉnh trước sáp nhập)','String',''),
 ('province_name','Tên tỉnh, thành phố','String',''),
 ('year','Năm','Numeric',''),
 ('month','Tháng; 0 với dòng ghi theo năm','Numeric',''),
 ('period','"2010" (theo năm) hoặc "2016-03" (theo tháng)','String',''),
 ('frequency','annual hoặc monthly — tần suất của chính dòng đó','String',''),
 ('source','DMSP, VIIRS, Landsat hoặc Sentinel-2','String',''),
 ('area_km2','Diện tích tự nhiên của tỉnh (polygon GADM 4.1, EPSG:6933)','Numeric','km²'),
 # --- Ba chỉ số kế hoạch quản lý dữ liệu bắt buộc ---
 ('sol','Quy mô kinh tế đêm: tổng giá trị pixel hợp lệ SAU khi trừ nền','Numeric','DN (DMSP) / nW/cm²/sr (VIIRS)'),
 ('sol_density','Mật độ kinh tế đêm: sol / area_km2','Numeric','đơn vị bức xạ/km²'),
 ('sol_change_pct','Thay đổi so với NĂM trước, chỉ khi cùng nguồn ảnh. Chỉ có ở dòng '
  'theo năm, nên trống ở toàn bộ nửa VIIRS theo tháng của ntl_panel','Numeric','%'),
 # --- Biến động theo tháng (chỉ nửa VIIRS) ---
 ('sol_change_yoy_pct','Thay đổi so với CÙNG THÁNG năm trước. Chỉ có ở dòng theo tháng. '
  'Dòng 2014 lấy mốc so sánh từ VIIRS 2013 — cùng cảm biến nên hợp lệ, nhưng các tháng '
  '2013 nằm ở ntl_monthly chứ không ở ntl_panel','Numeric','%'),
 ('sol_change_mom_pct','Thay đổi so với THÁNG LIỀN TRƯỚC; trống nếu tháng trước thiếu. '
  'Chỉ có ở dòng theo tháng; tháng 01/2014 so với 12/2013','Numeric','%'),
 ('sol_ma3','Trung bình trượt 3 tháng của sol, làm mượt dao động mùa. Chỉ có ở dòng '
  'theo tháng; cửa sổ của đầu 2014 với tới các tháng 2013','Numeric','nW/cm²/sr'),
 # --- Trừ ánh sáng nền ---
 ('sol_raw','Tổng giá trị TRƯỚC khi trừ nền, để đo tác động của bước lọc nền','Numeric','DN / nW/cm²/sr'),
 ('background_threshold','Ngưỡng nền đã dùng (VIIRS 0,5; DMSP 0 vì stable_lights đã loại nền)','Numeric','nW/cm²/sr hoặc DN'),
 ('background_pixels','Số pixel dưới ngưỡng nền, đóng góp 0 vào sol','Numeric','pixel'),
 # --- Phân bố bức xạ trong tỉnh ---
 ('rad_mean','Bức xạ trung bình trên pixel hợp lệ','Numeric','DN / nW/cm²/sr'),
 ('rad_std','Độ lệch chuẩn bức xạ trong tỉnh','Numeric','DN / nW/cm²/sr'),
 ('rad_min','Giá trị nhỏ nhất trong tỉnh','Numeric','DN / nW/cm²/sr'),
 ('rad_max','Giá trị lớn nhất trong tỉnh','Numeric','DN / nW/cm²/sr'),
 ('rad_cv','Hệ số biến thiên rad_std/rad_mean: chênh lệch sáng–tối trong tỉnh','Numeric','không thứ nguyên'),
 # --- Vùng có ánh sáng ---
 ('lit_pixels','Số pixel vượt ngưỡng sáng','Numeric','pixel'),
 ('lit_area_km2','Diện tích các pixel vượt ngưỡng sáng','Numeric','km²'),
 ('lit_area_pct','lit_area_km2 / area_km2: tỷ lệ diện tích tỉnh được chiếu sáng','Numeric','%'),
 ('lit_pixel_pct','lit_pixels / valid_pixels: tỷ lệ số pixel sáng trên số pixel có dữ liệu','Numeric','%'),
 ('lit_sol','Tổng bức xạ CHỈ trên các pixel vượt ngưỡng','Numeric','DN / nW/cm²/sr'),
 ('lit_threshold','Ngưỡng xác định pixel sáng (VIIRS 1,5 nW/cm²/sr; DMSP DN 5)','Numeric','nW/cm²/sr hoặc DN'),
 # --- Chất lượng ---
 ('valid_pixels','Số pixel có dữ liệu trong ranh giới tỉnh','Numeric','pixel'),
 ('cloud_free_obs','Số lượt quan sát sạch mây trung bình (cf_cvg). Trống với DMSP vì '
  'sản phẩm stable_lights của NOAA không có băng này','Numeric','lượt'),
 ('status','OK, OK_TOA, CHUA_CO_ANH, MISSING_SOURCE, INSUFFICIENT_QUALITY','String',''),
 ('obs_status','Cờ trạng thái quan sát theo CL_OBS_STATUS của IMF, một mã mỗi dòng: '
  'A bình thường · B đứt gãy chuỗi do đổi vệ tinh (năm 2010 và 2014) · L có ảnh nhưng '
  'không pixel nào hợp lệ · O không có ảnh · U ít lượt quan sát sạch mây nên kém tin cậy. '
  'Ưu tiên O > L > B > U > A. Chuỗi tháng không có mã B vì toàn VIIRS','String',''),
 ('note','DOI_NGUON_ANH_CHUA_HIEU_CHINH tại năm chuyển từ DMSP sang VIIRS; rỗng ở mọi '
  'dòng khác, nên trong ntl_panel (hai nửa không giáp nhau) luôn rỗng','String',''),
 # --- Hiệu chỉnh liên vệ tinh DMSP→VIIRS (chỉ bảng theo năm) ---
 ('sol_cal','sol sau khi quy DMSP về thang VIIRS; dòng VIIRS giữ nguyên','Numeric','nW/cm²/sr'),
 ('sol_density_cal','sol_cal / area_km2','Numeric','nW/cm²/sr trên km²'),
 ('sol_change_cal_pct','Thay đổi trên chuỗi đã hiệu chỉnh; CÓ giá trị tại mốc 2013→2014','Numeric','%'),
 ('calibration','Tên phương pháp hiệu chỉnh, hoặc PENDING','String',''),
 # --- Bảng năm chồng lấn ntl_overlap_2013 ---
 ('sol_dmsp','sol của ảnh DMSP 2013, dùng để khớp mô hình hiệu chỉnh','Numeric','DN'),
 ('sol_viirs','sol của ảnh VIIRS 2013, cùng ngưỡng nền với cột sol','Numeric','nW/cm²/sr'),
 # --- Bảng ảnh ngày ---
 ('reflectance_type','SR (phản xạ bề mặt) hoặc TOA (Sentinel-2 2015–2018)','String',''),
 ('<KÊNH>_mean / _std','Trung bình / độ lệch chuẩn phản xạ kênh (BLUE..SWIR2) và chỉ số NDVI, NDBI, MNDWI, BSI','Numeric','phản xạ (0–1) / không thứ nguyên'),
 ('valid_area_km2','Diện tích pixel hợp lệ ở mọi kênh','Numeric','km²'),
 ('valid_area_pct','valid_area_km2 / area_km2','Numeric','%'),
 ('window_days','Cửa sổ ngày của ảnh tổng hợp','String',''),
 ('collections','Bộ sưu tập ảnh đã dùng','String',''),
 ('months_used','Số tháng đã gộp lên dòng năm','Numeric','tháng'),
]
