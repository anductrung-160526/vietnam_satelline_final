"""Laptop-only processing (no Earth Engine): raw_data -> data_intermediate -> data_processed.

Stage B (data_intermediate, images)
  DAY  annual dry-season composite per province/year: per-pixel median of the monthly raw
       composites in the region's dry-season months (all months of the year if none);
       land-cover classification waits for training samples in samples/.
  NTL  VIIRS monthly filtered (cf_cvg=0 -> NoData, negative -> 0, temporal spikes such as
       fires capped at the pixel's annual median), VIIRS annual (median of the
       filtered months of that year), DMSP annual.
       DMSP-VIIRS inter-calibration is NOT applied until a validated method is chosen;
       every NTL file and table row carries HARMONIZATION=PENDING.
Stage C (data_processed, tables; key ma_tinh + nam [+ thang])
  day_indices_monthly   spectral statistics of each monthly raw day image
  ntl_monthly           VIIRS 2013-2025 monthly SOL/density/YoY from filtered images
  ntl_annual            DMSP 2004-2013 then VIIRS 2014-2025 annual SOL/density/change
  ntl_overlap_2013      DMSP and VIIRS side by side for the 2013 calibration year
Each branch writes table parts under _control/<branch>/tables; merge() combines all six
parts into the shared data_processed files under a file lock.
"""
import json
import math
import sys
from pathlib import Path
from province_pipeline.common import atomic_json
from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
from .paths import CONTROL,file_lock,append_log

NODATA=-9999
DAY_BANDS=['BLUE','GREEN','RED','NIR','SWIR1','SWIR2']
INDICES=['NDVI','NDBI','MNDWI','BSI']
LIT_THRESHOLD_VIIRS=1.5
LIT_THRESHOLD_DMSP=5
# Ngưỡng "có ánh sáng" theo từng nguồn, hai thang đo khác nhau:
#   VIIRS  1,5 nW/cm2/sr  (task_pipeline/scope.py đặt lit_threshold_viirs=1.5)
#   DMSP   DN 5           (province_pipeline/profiles.py lit_threshold_dmsp=5)
# Không dùng chung một con số cho cả hai: DMSP là DN 0-63, VIIRS là bức xạ.
LIT_THRESHOLD={'VIIRS':LIT_THRESHOLD_VIIRS,'DMSP':LIT_THRESHOLD_DMSP}
# Ngưỡng nền: giá trị dưới mức này coi là nhiễu nền, đóng góp 0 vào sol_ntl.
#   VIIRS 0,5 nW/cm2/sr — đúng mặc định lit_threshold_viirs của province_pipeline/profiles.py,
#     thấp hơn ngưỡng "có ánh sáng" 1,5 nên hai khái niệm vẫn tách bạch.
#   DMSP  0 — sản phẩm stable_lights của NOAA đã loại nền sẵn; trừ thêm lần nữa là trừ hai lần.
BACKGROUND={'VIIRS':0.5,'DMSP':0.0}
# Đổi công thức trong ntl_stats/day_stats thì tăng số này, nếu không Cache sẽ trả kết quả cũ.
STATS_VERSION=5
ROWS=512
SENSOR={'LANDSAT':'LANDSAT','SENTINEL2':'SENTINEL2'}


def dry_season(ma_tinh,override=None):
    """Regional dry season inside one calendar year (documented default, overridable)."""
    if override and ma_tinh in override:
        return list(override[ma_tinh])
    code=int(ma_tinh)
    if code<=42:return [1,2,3,4,11,12]      # North and north-central: Nov-Apr
    if code<=60:return [1,2,3,4,5,6,7,8]    # Quang Binh..Binh Thuan: rain Sep-Dec
    return [1,2,3,4,12]                     # Highlands, South East, Mekong: Dec-Apr


def zstd_profile(src_profile,count,dtype):
    p=dict(src_profile)
    p.update(driver='GTiff',count=count,dtype=dtype,nodata=NODATA,compress='ZSTD',zstd_level=19,
             predictor=3 if dtype.startswith('float') else 2,tiled=True,blockxsize=512,blockysize=512,BIGTIFF='IF_SAFER')
    return p


def windows(height,width):
    """512x512 tiles (bounded memory even for 12 months x 6 bands of a large province)."""
    from rasterio.windows import Window
    for row in range(0,height,ROWS):
        for col in range(0,width,ROWS):
            yield Window(col,row,min(ROWS,width-col),min(ROWS,height-row))


def pixel_area_km2(transform,window,crs):
    """Area of each pixel row in km2 (geographic grid uses latitude; projected grid is exact)."""
    import numpy as np
    if str(crs).upper().endswith('4326'):
        rows=np.arange(window.row_off,window.row_off+window.height)+.5
        lat=transform.f+rows*transform.e
        return (abs(transform.a)*abs(transform.e)*(111.320**2)*np.cos(np.radians(lat)))[:,None]
    return np.full((window.height,1),abs(transform.a*transform.e)/1e6)


def province_area_km2(boundary):
    from shapely.geometry import shape
    from rasterio.warp import transform_geom
    return shape(transform_geom('EPSG:4326','EPSG:6933',boundary['geometry'])).area/1e6


def stamp(paths):
    return [[str(p),Path(p).stat().st_size,Path(p).stat().st_mtime_ns] for p in paths]


def up_to_date(target,inputs,can_co=()):
    """True when target exists and was built from exactly these inputs.

    can_co: những thẻ mà bản dựng HIỆN TẠI phải có. Thêm một thẻ mới vào sản phẩm
    trung gian mà không khai ở đây thì ảnh cũ vẫn được coi là còn mới, thẻ không bao
    giờ được ghi, và cột đọc từ thẻ đó rỗng vĩnh viễn mà không có gì báo lỗi.
    """
    import rasterio
    if not Path(target).exists():return False
    try:
        with rasterio.open(target) as ds:
            tags=ds.tags()
            if any(k not in tags for k in can_co):return False
            return json.loads(tags.get('INPUT_STAMP','null'))==stamp(inputs)
    except Exception:
        return False


def write(path,profile,band_names,blocks,tags,inputs):
    """Atomic write of a masked, compressed TIFF from (window, data, valid) blocks."""
    import rasterio
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_name(path.stem+'.part.tif')
    try:
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),rasterio.open(part,'w',**profile) as dst:
            for i,name in enumerate(band_names,1):dst.set_band_description(i,name)
            for window,data,valid in blocks:
                dst.write(data,window=window)
                dst.write_mask((valid*255).astype('uint8'),window=window)
            dst.update_tags(**tags,INPUT_STAMP=json.dumps(stamp(inputs)))
            if profile['dtype']=='int16':
                dst.scales=[1e-4]*len(band_names);dst.offsets=[0.0]*len(band_names)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path


# ---------------------------------------------------------------- Stage B: day

def day_annual(raw,province,root,override=None):
    """raw: {(product, 'YYYY-MM'): path}. One dry-season composite per product/year."""
    import numpy as np
    import rasterio
    built=[]
    p=province;name=f"{p['ma_tinh']}_{p['slug']}"
    years=sorted({(prod,period[:4]) for prod,period in raw if prod in SENSOR})
    for product,year in years:
        months=dry_season(p['ma_tinh'],override)
        inputs=[raw[(product,f'{year}-{m:02}')] for m in months if (product,f'{year}-{m:02}') in raw]
        rule='DRY_SEASON'
        if not inputs:
            inputs=[raw[(product,f'{year}-{m:02}')] for m in range(1,13) if (product,f'{year}-{m:02}') in raw]
            rule='ALL_MONTHS_FALLBACK'
        if not inputs:continue
        target=Path(root)/DAY_PACKAGE/'data_intermediate'/'annual_composite'/SENSOR[product]/name/f'{name}_{product}_{year}_dryseason_sr6.tif'
        if up_to_date(target,inputs):
            built.append(target);continue
        sources=[rasterio.open(x) for x in inputs]
        try:
            first=sources[0]
            profile=zstd_profile(first.profile,len(DAY_BANDS)+1,'int16')
            def blocks():
                for w in windows(first.height,first.width):
                    stack=np.stack([s.read(window=w).astype('float32') for s in sources])  # months,bands,h,w
                    stack[stack==NODATA]=np.nan
                    good=~np.isnan(stack).any(axis=1)                                     # months,h,w
                    stack[~np.broadcast_to(good[:,None],stack.shape)]=np.nan
                    count=good.sum(axis=0)
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore',RuntimeWarning)
                        med=np.nanmedian(stack,axis=0)
                    valid=count>0
                    out=np.full((len(DAY_BANDS)+1,)+count.shape,NODATA,dtype='int16')
                    out[:-1][:,valid]=np.clip(np.round(med[:,valid]),-32767,32767).astype('int16')
                    out[-1][valid]=count[valid]
                    yield w,out,valid
            write(target,profile,DAY_BANDS+['OBS_MONTHS'],blocks(),
                  dict(SOURCE=product,YEAR=year,COMPOSITE='median_of_monthly_composites',SEASON_RULE=rule,
                       SEASON_MONTHS=','.join(map(str,months)),INPUT_MONTHS=str(len(inputs)),
                       SCALE_FACTOR='0.0001 (bands 1-6); OBS_MONTHS unscaled'),inputs)
        finally:
            for s in sources:s.close()
        built.append(target)
    return built


def landcover_status(root):
    samples=Path(root)/DAY_PACKAGE/'samples'
    has=samples.is_dir() and any(f.is_file() for f in samples.rglob('*'))
    return 'SAMPLES_PRESENT_CLASSIFIER_NOT_CONFIGURED' if has else 'PENDING_SAMPLES'


# ---------------------------------------------------------------- Stage B: night

def viirs_filtered(raw,province,root):
    """Filter each VIIRS month; spikes judged against the same pixel's annual median."""
    import numpy as np
    import rasterio
    p=province;name=f"{p['ma_tinh']}_{p['slug']}";out={}
    years=sorted({period[:4] for prod,period in raw if prod=='VIIRS_MONTHLY'})
    for year in years:
        months=[(m,raw[('VIIRS_MONTHLY',f'{year}-{m:02}')]) for m in range(1,13) if ('VIIRS_MONTHLY',f'{year}-{m:02}') in raw]
        inputs=[path for _,path in months]
        targets={m:Path(root)/NTL_PACKAGE/'data_intermediate'/'VIIRS_MONTHLY'/name/f'{name}_VIIRS_{year}-{m:02}_filtered.tif' for m,_ in months}
        if all(up_to_date(t,inputs,can_co=('CF_CVG_MEAN',)) for t in targets.values()):
            out.update({f'{year}-{m:02}':t for m,t in targets.items()});continue
        sources=[rasterio.open(x) for x in inputs]
        try:
            first=sources[0];profile=zstd_profile(first.profile,1,'float32')
            blocks={m:[] for m,_ in months};spikes=0
            # Số lượt quan sát sạch mây trung bình của từng tháng. Băng cf_cvg chỉ có ở
            # ảnh thô và bị bỏ khi ghi ảnh đã lọc, nên phải thu ở đây; nó là trường chất
            # lượng: tháng mùa mưa ít lượt quan sát hơn nên con số dựa trên ít dữ liệu hơn.
            cf={m:[0.0,0] for m,_ in months}
            for w in windows(first.height,first.width):
                rad=np.stack([s.read(1,window=w) for s in sources]).astype('float64')
                cov=np.stack([s.read(2,window=w) for s in sources]).astype('float64')
                valid=(rad!=NODATA)&(cov!=NODATA)&(cov>0)
                rad=np.where(valid,np.maximum(rad,0),np.nan)
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',RuntimeWarning)
                    median=np.nanmedian(rad,axis=0)
                spike=valid&(rad>np.maximum(3*median,median+5))
                spikes+=int(spike.sum())
                rad=np.where(spike,median,rad)
                for i,(m,_) in enumerate(months):
                    data=np.where(valid[i],rad[i],NODATA).astype('float32')[None]
                    blocks[m].append((w,data,valid[i]))
                    cf[m][0]+=float(cov[i][valid[i]].sum());cf[m][1]+=int(valid[i].sum())
            for m,path in months:
                write(targets[m],profile,['avg_rad_filtered'],blocks[m],
                      dict(SOURCE='VIIRS_MONTHLY',PERIOD=f'{year}-{m:02}',UNIT='nW/cm2/sr',HARMONIZATION='PENDING',
                           FILTER='cf_cvg=0->NoData; negative->0; value>max(3*annual median, median+5)->annual median',
                           SPIKES_CAPPED_IN_YEAR=str(spikes),
                           CF_CVG_MEAN=('' if not cf[m][1] else str(round(cf[m][0]/cf[m][1],4)))),inputs)
                out[f'{year}-{m:02}']=targets[m]
        finally:
            for s in sources:s.close()
    return out


def viirs_annual(raw,filtered,province,root):
    """Annual VIIRS = per-pixel median of the filtered months of that year."""
    import numpy as np
    import rasterio
    p=province;name=f"{p['ma_tinh']}_{p['slug']}";out={}
    for year in sorted({period[:4] for period in filtered}):
        target=Path(root)/NTL_PACKAGE/'data_intermediate'/'VIIRS_ANNUAL'/name/f'{name}_VIIRS_{year}_annual.tif'
        inputs=[filtered[k] for k in sorted(filtered) if k[:4]==year]
        if up_to_date(target,inputs,can_co=('CF_CVG_MEAN',)):
            out[year]=target;continue
        sources=[rasterio.open(x) for x in inputs]
        try:
            first=sources[0];profile=zstd_profile(first.profile,1,'float32')
            def blocks():
                for w in windows(first.height,first.width):
                    stack=np.stack([s.read(1,window=w) for s in sources]).astype('float64')
                    stack[stack==NODATA]=np.nan
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore',RuntimeWarning)
                        rad=np.nanmedian(stack,axis=0)
                    valid=~np.isnan(rad)
                    yield w,np.where(valid,rad,NODATA).astype('float32')[None],valid
            cf=[]
            for src in sources:
                v=src.tags().get('CF_CVG_MEAN')
                if v:
                    try:cf.append(float(v))
                    except ValueError:pass
            write(target,profile,['avg_rad_annual'],blocks(),
                  dict(SOURCE='MEDIAN_OF_FILTERED_VIIRS_MONTHS',YEAR=year,UNIT='nW/cm2/sr',
                       HARMONIZATION='PENDING',MONTHS_USED=str(len(inputs)),
                       CF_CVG_MEAN=('' if not cf else str(round(sum(cf)/len(cf),4)))),inputs)
        finally:
            for s in sources:s.close()
        out[year]=target
    return out


def dmsp_annual(raw,province,root):
    import numpy as np
    import rasterio
    p=province;name=f"{p['ma_tinh']}_{p['slug']}";out={}
    for (product,year),path in sorted(raw.items()):
        if product!='DMSP':continue
        target=Path(root)/NTL_PACKAGE/'data_intermediate'/'DMSP'/name/f'{name}_DMSP_{year}.tif'
        if not up_to_date(target,[path]):
            with rasterio.open(path) as src:
                profile=zstd_profile(src.profile,1,'float32')
                def blocks():
                    for w in windows(src.height,src.width):
                        dn=src.read(1,window=w);valid=dn!=NODATA
                        yield w,np.where(valid,dn,NODATA).astype('float32')[None],valid
                write(target,profile,['stable_lights'],blocks(),
                      dict(SOURCE='DMSP',YEAR=year,UNIT='DN 0-63',HARMONIZATION='PENDING'),[path])
        out[year]=target
    return out


# ---------------------------------------------------------------- Stage C: tables

def day_stats(path):
    """Population mean/std of the 6 bands and 4 indices over pixels valid in all bands."""
    import numpy as np
    import rasterio
    acc={k:[0.0,0.0] for k in DAY_BANDS+INDICES};n=0;area=0.0
    with rasterio.open(path) as ds:
        tags=ds.tags()
        for w in windows(ds.height,ds.width):
            data=ds.read(list(range(1,len(DAY_BANDS)+1)),window=w).astype('float64')
            valid=(data!=NODATA).all(axis=0)
            if not valid.any():continue
            v={b:data[i][valid]/10000 for i,b in enumerate(DAY_BANDS)}
            def nd(a,b):
                d=a+b;return np.where(np.abs(d)>1e-8,(a-b)/np.where(d==0,1,d),np.nan)
            v['NDVI']=nd(v['NIR'],v['RED']);v['NDBI']=nd(v['SWIR1'],v['NIR']);v['MNDWI']=nd(v['GREEN'],v['SWIR1'])
            v['BSI']=nd(v['SWIR1']+v['RED'],v['NIR']+v['BLUE'])
            for k,x in v.items():
                x=x[np.isfinite(x)];acc[k][0]+=x.sum();acc[k][1]+=(x*x).sum()
            n+=int(valid.sum());area+=float((np.broadcast_to(pixel_area_km2(ds.transform,w,ds.crs),valid.shape)[valid]).sum())
    row=dict(valid_pixels=n,valid_area_km2=round(area,3),window_days=tags.get('WINDOW_DAYS',''),
             collections=tags.get('COLLECTIONS',''))
    for k,(s,s2) in acc.items():
        mean=s/n if n else None
        row[k+'_mean']=round(mean,6) if mean is not None else None
        row[k+'_std']=round(math.sqrt(max(s2/n-mean*mean,0)),6) if n else None
    return row


def ntl_stats(path,threshold=None,background=0.0):
    """Thống kê một ảnh đêm trong một lượt đọc. Tên khoá = tên cột trong bảng xuất ra.

    background: ngưỡng nền. Pixel dưới ngưỡng vẫn là pixel hợp lệ (vẫn tính vào diện tích
    và vào rad_mean/rad_std) nhưng đóng góp 0 vào sol — đó là nghĩa của "trừ ánh sáng nền".
    sol_raw giữ tổng chưa trừ nền để đo được bước này lấy đi bao nhiêu.

    threshold=None thì bỏ qua mọi chỉ số vùng sáng (trả None), không coi mọi pixel là sáng.

    cloud_free_obs đọc từ thẻ CF_CVG_MEAN do viirs_filtered ghi; ảnh DMSP không có thẻ này
    nên trả None. Đây là trường chất lượng: tháng mùa mưa ít lượt quan sát sạch mây hơn,
    con số của tháng đó dựa trên ít dữ liệu hơn.
    """
    import numpy as np
    import rasterio
    total=0.0;tho=0.0;sq=0.0;n=0;nen=0;lit=0;lit_total=0.0;lit_area=0.0;mx=None;mn=None
    with rasterio.open(path) as ds:
        cov=ds.tags().get('CF_CVG_MEAN')
        for w in windows(ds.height,ds.width):
            a=ds.read(1,window=w).astype('float64')
            valid=a!=NODATA
            if not valid.any():continue
            x=a[valid]
            tho+=x.sum()
            tren_nen=x>=background if background else np.ones(x.shape,dtype=bool)
            nen+=int((~tren_nen).sum())
            total+=float(x[tren_nen].sum())
            sq+=float((x*x).sum());n+=x.size
            mx=x.max() if mx is None else max(mx,x.max())
            mn=x.min() if mn is None else min(mn,x.min())
            if threshold is not None:
                sang=valid&(a>=threshold)
                if sang.any():
                    lit+=int(sang.sum());lit_total+=float(a[sang].sum())
                    lit_area+=float(np.broadcast_to(
                        pixel_area_km2(ds.transform,w,ds.crs),sang.shape)[sang].sum())
    try:
        cov=round(float(cov),4) if cov is not None else None
    except ValueError:
        cov=None
    if not n:
        return dict(sol=None,sol_raw=None,valid_pixels=0,background_pixels=None,
                    rad_max=None,rad_min=None,rad_mean=None,rad_std=None,rad_cv=None,
                    lit_pixels=None,lit_sol=None,lit_area_km2=None,lit_pixel_pct=None,
                    background_threshold=background,cloud_free_obs=cov)
    mean=tho/n
    std=math.sqrt(max(sq/n-mean*mean,0))
    co_nguong=threshold is not None
    return dict(sol=round(total,4),sol_raw=round(tho,4),
                valid_pixels=n,background_pixels=nen,background_threshold=background,
                rad_max=round(float(mx),4),rad_min=round(float(mn),4),
                rad_mean=round(mean,6),rad_std=round(std,6),
                # Hệ số biến thiên: mức chênh lệch sáng-tối bên trong tỉnh.
                rad_cv=round(std/mean,4) if mean>0 else None,
                lit_pixels=lit if co_nguong else None,
                lit_sol=round(lit_total,4) if co_nguong else None,
                lit_area_km2=round(lit_area,4) if co_nguong else None,
                # Tỷ lệ SỐ PIXEL sáng (notebook gốc gọi là electrification ratio), khác
                # lit_area_pct vốn chia cho diện tích tự nhiên của tỉnh.
                lit_pixel_pct=round(100*lit/n,4) if co_nguong else None,
                cloud_free_obs=cov)


def pct(cur,prev):
    return round(100*(cur/prev-1),4) if cur is not None and prev not in (None,0) and prev>0 else None


class Cache:
    """Per-file statistics cache keyed by size+mtime, so re-runs only read changed files."""
    def __init__(self,path):
        self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
    def get(self,path,compute,nhan=()):
        # STATS_VERSION nằm trong khoá: đổi công thức là mọi mục cũ tự hết hiệu lực.
        # nhan: phân biệt các lần gọi cùng một file nhưng khác tham số (ngưỡng nền,
        # ngưỡng sáng). Thiếu nó thì lần gọi sau nhận kết quả của lần gọi trước mà
        # không có gì báo — chính là lỗi đã làm sai bảng chồng lấn 2013.
        st=Path(path).stat();sig=[st.st_size,st.st_mtime_ns,STATS_VERSION]
        # nhan vào KHÓA, không vào sig: cùng một file với hai bộ ngưỡng là hai mục
        # riêng, nếu không chúng ghi đè nhau và mỗi lần chạy lại đọc lại cả ảnh.
        key='|'.join((str(path),*nhan))
        hit=self.data.get(key)
        if hit and hit['sig']==sig:return hit['row']
        row=compute(path);self.data[key]=dict(sig=sig,row=row);return row
    def save(self):
        atomic_json(self.path,self.data)


def base(p,nam,thang,nguon,area):
    """Khung chung của một dòng. province dict giữ khoá tiếng Việt (khoá nội bộ của
    luồng tải ảnh); từ đây trở đi tên khoá chính là TÊN CỘT trong bảng xuất ra."""
    row=dict(province_code=p['ma_tinh'],province_name=p['ten_tinh'],year=int(nam))
    row['month']=int(thang) if thang is not None else 0
    row['period']=f'{int(nam)}-{int(thang):02}' if thang is not None else f'{int(nam)}'
    row['frequency']='monthly' if thang is not None else 'annual'
    row.update(source=nguon,area_km2=round(area,3))
    return row


def day_rows(province,status,raw,area,cache):
    """status: {(product,period): job status}; raw: {(product,period): path}."""
    rows=[]
    for (product,period),state in sorted(status.items()):
        if product not in SENSOR:continue
        row=base(province,period[:4],period[5:],'Landsat' if product=='LANDSAT' else 'Sentinel-2',area)
        collection='TOA' if product=='SENTINEL2' and int(period[:4])<2019 else 'SR'
        row['reflectance_type']=collection
        if (product,period) in raw:
            row.update(cache.get(raw[(product,period)],day_stats))
            row['valid_area_pct']=round(100*row['valid_area_km2']/area,2) if area else None
            row['status']='OK'+('_TOA' if collection=='TOA' else '')
        else:
            row['status']=state or 'CHUA_CO_ANH'
        rows.append(row)
    return rows


# Cờ trạng thái quan sát, theo CL_OBS_STATUS của IMF (docs/THAM_KHAO_FAS_IMF.md).
# Chỉ dùng năm mã trong số 25 mã của IMF, vì năm mã đó là tất cả những gì bộ dữ liệu này
# phân biệt được Ở MỨC DÒNG.
#
# Hai mã của IMF cố ý KHÔNG dùng ở đây, vì chúng là thuộc tính của một CỘT chứ không phải
# của cả dòng: M (dữ liệu không thể tồn tại — cloud_free_obs ở dòng DMSP) và E (giá trị
# ước lượng — nhóm cột _cal). Gán chúng cho cả dòng sẽ nói sai về những cột còn lại.
# cloud_free_obs trống ở DMSP đã được giải thích trong codebook; nhóm _cal đã có cột
# calibration mang tên phương pháp.
MOC_DOI_VE_TINH = (2010, 2014)   # F16->F18 và DMSP->VIIRS
IT_TIN_CAY = 2.0                 # dưới 2 lượt quan sát sạch mây


def co_trang_thai(row,co_anh,moc_gay=()):
    """Một dòng mang ĐÚNG một mã. Thiếu dữ liệu quan trọng hơn mọi ghi chú khác.

    Thứ tự ưu tiên O > L > B > U > A:
      O  không có ảnh
      L  có ảnh nhưng không pixel nào hợp lệ (cả tỉnh mây che)
      B  đứt gãy chuỗi do đổi vệ tinh
      U  ít lượt quan sát sạch mây nên con số kém tin cậy
      A  bình thường
    """
    if not co_anh:return 'O'
    if not row.get('valid_pixels'):return 'L'
    if int(row['year']) in moc_gay:return 'B'
    cov=row.get('cloud_free_obs')
    if cov is not None and cov < IT_TIN_CAY:return 'U'
    return 'A'


def _dan_xuat(row,area):
    """Các cột suy ra từ thống kê ảnh và diện tích tỉnh. Dùng chung cho năm và tháng."""
    row['sol_density']=round(row['sol']/area,6) if row['sol'] is not None and area else None
    row['lit_area_pct']=(round(100*row['lit_area_km2']/area,4)
                         if row.get('lit_area_km2') is not None and area else None)
    return row


def ntl_monthly_rows(province,filtered,area,cache):
    rows=[];by={}
    for period,path in sorted(filtered.items()):
        row=base(province,period[:4],period[5:],'VIIRS',area)
        row.update(cache.get(path,lambda x:ntl_stats(x,LIT_THRESHOLD['VIIRS'],BACKGROUND['VIIRS']),
                             nhan=('VIIRS',)))
        _dan_xuat(row,area)
        row['lit_threshold']=LIT_THRESHOLD['VIIRS']
        by[period]=row;rows.append(row)
    thu_tu=sorted(by)
    for i,period in enumerate(thu_tu):
        row=by[period]
        cung_ky=by.get(f'{int(period[:4])-1}-{period[5:]}')
        row['sol_change_yoy_pct']=pct(row['sol'],cung_ky['sol']) if cung_ky else None
        # So với tháng liền trước TRONG CHUỖI, chỉ khi hai tháng thật sự liền nhau:
        # thiếu một tháng ở giữa thì để trống chứ không so vượt qua lỗ hổng.
        truoc=by[thu_tu[i-1]] if i else None
        lien_ke=truoc is not None and _lien_ke(thu_tu[i-1],period)
        row['sol_change_mom_pct']=pct(row['sol'],truoc['sol']) if lien_ke else None
        cua_so=[by[k]['sol'] for k in thu_tu[max(0,i-2):i+1] if by[k]['sol'] is not None]
        row['sol_ma3']=round(sum(cua_so)/len(cua_so),4) if cua_so else None
        row['calibration']='PENDING'
        row['status']='OK' if row['sol'] is not None else 'CHUA_CO_ANH'
        # Chuỗi tháng toàn VIIRS nên không có mốc đổi vệ tinh nào: không gán B ở đây.
        row['obs_status']=co_trang_thai(row,row['sol'] is not None)
    return rows


def _lien_ke(truoc,sau):
    """'2016-12' và '2017-01' là liền kề; '2016-10' và '2016-12' thì không."""
    a=int(truoc[:4])*12+int(truoc[5:]);b=int(sau[:4])*12+int(sau[5:])
    return b-a==1


def ntl_annual_rows(province,dmsp,viirs,area,cache):
    rows=[];overlap=None;prev=None
    for year in range(2004,2026):
        y=str(year)
        if year<=2013 and y in dmsp:path,src=dmsp[y],'DMSP'
        elif year>=2014 and y in viirs:path,src=viirs[y],'VIIRS'
        else:path,src=None,'DMSP' if year<=2013 else 'VIIRS'
        row=base(province,year,None,src,area)
        nguong=LIT_THRESHOLD.get(src);nen=BACKGROUND.get(src,0.0)
        if path:
            row.update(cache.get(path,lambda x:ntl_stats(x,nguong,nen),nhan=(src,)))
            _dan_xuat(row,area)
        else:
            row.update(sol=None,sol_density=None,lit_area_pct=None)
        same=prev is not None and prev['source']==src
        row['sol_change_pct']=pct(row['sol'],prev['sol']) if same else None
        row['note']='' if same or prev is None else 'DOI_NGUON_ANH_CHUA_HIEU_CHINH'
        row['lit_threshold']=nguong
        row['calibration']='PENDING';row['status']='OK' if path else 'CHUA_CO_ANH'
        row['obs_status']=co_trang_thai(row,bool(path),MOC_DOI_VE_TINH)
        rows.append(row);prev=row
    if '2013' in dmsp and '2013' in viirs:
        # Phải dùng ĐÚNG ngưỡng nền của cột sol. Gọi ntl_stats trần (background=0) thì
        # sol_viirs gồm cả nhiễu nền dưới 0,5 — một lượng tỷ lệ với diện tích tỉnh chứ
        # không với kinh tế — và mô hình sẽ khớp trên đại lượng khác với đại lượng nó
        # được áp lên. Đã xảy ra thật: R² tụt còn 0,57 và b < 1 (sai chiều vật lý).
        d=cache.get(dmsp['2013'],lambda x:ntl_stats(x,LIT_THRESHOLD['DMSP'],BACKGROUND['DMSP']),
                    nhan=('DMSP',))
        v=cache.get(viirs['2013'],lambda x:ntl_stats(x,LIT_THRESHOLD['VIIRS'],BACKGROUND['VIIRS']),
                    nhan=('VIIRS',))
        overlap=dict(province_code=province['ma_tinh'],province_name=province['ten_tinh'],
                     year=2013,sol_dmsp=d['sol'],sol_viirs=v['sol'],area_km2=round(area,3))
    return rows,overlap


def ntl_panel_rows(annual,monthly):
    """MỘT bộ dữ liệu duy nhất: DMSP theo NĂM đến 2013, VIIRS theo THÁNG từ 2014.

    Hai nửa có tần suất khác nhau nên cột frequency nói rõ từng dòng là năm hay tháng,
    và một vài cột chỉ có nghĩa ở một nửa (sol_change_pct cho nửa năm; sol_change_mom_pct,
    sol_ma3, cloud_free_obs cho nửa tháng). Trả về bản sao để không chia sẻ dict với
    ntl_annual/ntl_monthly — sửa bảng này không được đụng vào bảng kia.
    """
    out=[dict(r) for r in annual if int(r['year'])<=2013 and r.get('source')=='DMSP']
    out+=[dict(r) for r in monthly if int(r['year'])>=2014]
    return sorted(out,key=lambda r:(int(r['year']),int(r.get('month') or 0)))


TABLES={
    'day_indices_monthly':DAY_PACKAGE,
    'ntl_monthly':NTL_PACKAGE,
    'ntl_annual':NTL_PACKAGE,
    # Bộ dữ liệu gộp để dùng và để nộp: DMSP theo năm 2004-2013 + VIIRS theo tháng 2014-2025.
    'ntl_panel':NTL_PACKAGE,
    'ntl_overlap_2013':NTL_PACKAGE,
}
KEYS=('province_code','year','month','source')


def write_part(control,name,rows):
    import pandas as pd
    path=Path(control)/'tables'/f'{name}.csv';path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix('.csv.part')
    pd.DataFrame(rows).to_csv(part,index=False,encoding='utf-8-sig');part.replace(path)
    return path


def stata_safe(frame):
    """Cột chữ toàn ô trống làm to_stata từ chối ghi cả bảng. Đổi ô trống thành ''.

    Xảy ra khi một bảng gộp từ nhiều nguồn mà chỉ vài nguồn có cột đó. Để nguyên thì
    mất luôn tệp .dta của cả bảng vì một cột phụ.
    """
    out=frame.copy()
    for col in out.columns:
        if out[col].dtype==object:
            out[col]=out[col].where(out[col].notna(),'')
    return out


def merge(root):
    """Combine every branch's table parts into the shared data_processed files (.csv/.xlsx/.dta)."""
    import pandas as pd
    root=Path(root);written=[];bo_qua=[]
    with file_lock(root/CONTROL/'.tables.lock'):
        for name,package in TABLES.items():
            parts=sorted(root.glob(f'{CONTROL}/*/tables/{name}.csv'))
            if not parts:continue
            # province_code phải đọc là CHUỖI: để pandas đoán thì '01' thành số 1 và mọi
            # phép nối theo mã tỉnh về sau đều trượt.
            frames=[]
            for p in parts:
                if not p.stat().st_size:continue
                f=pd.read_csv(p,dtype={'province_code':str},encoding='utf-8-sig')
                # Phần bảng của phiên bản cũ KHÔNG có cột khoá hiện tại. Gộp vào thì mọi
                # dòng cũ mang khoá rỗng, và drop_duplicates coi các ô rỗng là GIỐNG NHAU
                # nên hàng nghìn dòng co lại còn một. Đã xảy ra thật: 1144 dòng còn 1.
                # Bỏ qua và nói ra, để nhóm tỉnh đó được tính lại chứ không âm thầm mất.
                if 'province_code' not in f.columns:
                    bo_qua.append(p);continue
                frames.append(f)
            if not frames:continue
            frame=pd.concat(frames,ignore_index=True)
            keys=[k for k in KEYS if k in frame.columns]
            frame=frame.drop_duplicates(subset=keys,keep='last').sort_values(keys).reset_index(drop=True)
            dest=root/package/'data_processed';dest.mkdir(parents=True,exist_ok=True)
            for suffix,save in (('.csv',lambda f,p:f.to_csv(p,index=False,encoding='utf-8-sig')),
                                ('.xlsx',lambda f,p:f.to_excel(p,index=False)),
                                ('.dta',lambda f,p:stata_safe(f).to_stata(p,write_index=False,version=118))):
                target=dest/(name+suffix);tmp=target.with_name(target.stem+'.part'+suffix)
                try:
                    save(frame,tmp);tmp.replace(target);written.append(target)
                except ImportError:
                    tmp.unlink(missing_ok=True)   # optional writer (openpyxl) not installed
    if bo_qua:
        nhom=sorted({p.parent.parent.name for p in bo_qua})
        print(f'BỎ QUA {len(bo_qua)} phần bảng của phiên bản cũ (thiếu cột province_code), '
              f'thuộc nhóm: {", ".join(nhom)}',file=sys.stderr)
        print('  Những nhóm tỉnh đó chưa vào bảng gộp. Chạy lại chỉ số cho chúng.',
              file=sys.stderr)
    return written


README={
 NTL_PACKAGE:"""# VN_NTL_Panel_2004_2025

Bộ dữ liệu ánh sáng ban đêm cấp tỉnh, 63 tỉnh, thành phố (trước sáp nhập), 2004–2025.

- raw_data/NTL/DMSP/: DMSP-OLS stable_lights tổng hợp năm 2004–2013 (Earth Engine, NOAA/NCEI), cắt theo tỉnh.
- raw_data/NTL/VIIRS/: VIIRS DNB tháng (VCMSLCFG, thiếu tháng dùng VCMCFG) 2013–2025; ảnh năm VIIRS tổng hợp từ ảnh tháng (data_intermediate).
- data_intermediate/: ảnh đã lọc nhiễu, cắt ranh giới (DMSP/, VIIRS_MONTHLY/, VIIRS_ANNUAL/). Hiệu chỉnh liên kết DMSP–VIIRS: PENDING.
- data_processed/: khóa province_code + year + month (month = 0 với dòng theo năm).
  - ntl_panel: BỘ DỮ LIỆU CHÍNH — DMSP theo năm 2004–2013 + VIIRS theo tháng 2014–2025.
  - ntl_annual: chuỗi theo năm 2004–2025 (VIIRS năm = trung vị các tháng), cho so sánh năm
    và cho bước hiệu chỉnh liên vệ tinh.
  - ntl_monthly: mọi tháng VIIRS có ảnh, kể cả 2013 (năm chồng lấn, không vào ntl_panel).
  - ntl_overlap_2013: cặp DMSP–VIIRS của năm 2013 để khớp mô hình hiệu chỉnh.
  Mỗi bảng có .csv/.xlsx/.dta.
- metadata/: Codebook. logs/: nhật ký cập nhật. Mã nguồn: repository vietnam_satelline_final (task_pipeline/).
Môi trường: Python 3.11, rasterio, numpy, pandas, earthengine-api (xem task_pipeline/HUONG_DAN_CHAY_LOCAL.md).
""",
 DAY_PACKAGE:"""# VN_LandCover_Panel_2004_2025

Bộ dữ liệu ảnh vệ tinh ban ngày cấp tỉnh, 63 tỉnh, thành phố (trước sáp nhập), 2004–2025.

- raw_data/DAY/LANDSAT/: ảnh tổng hợp tháng Landsat 5/7/8/9 C2 L2, 30 m, 2004–2014.
- raw_data/DAY/SENTINEL2/: ảnh tổng hợp tháng Sentinel-2, 20 m, 2015–2025 (2015–2018 là TOA, 2019–2025 là SR).
  Lưu int16 = phản xạ × 10000 (scale 0.0001), 6 kênh BLUE, GREEN, RED, NIR, SWIR1, SWIR2, nén ZSTD, ngoài ranh giới tỉnh = NoData.
  Dùng 20 m thay cho 10 m để vừa dung lượng lưu trữ; kênh SWIR gốc chỉ có 20 m.
- data_intermediate/annual_composite/: ảnh tổng hợp năm mùa khô (median các ảnh tháng), kèm kênh OBS_MONTHS.
- data_intermediate/ bản đồ phân loại 5 lớp: chờ bộ điểm mẫu trong samples/.
- data_processed/: day_indices_monthly (.csv/.xlsx/.dta), khóa province_code + year + month.
- metadata/: Codebook. logs/: nhật ký cập nhật. Mã nguồn: repository vietnam_satelline_final (task_pipeline/).
""",
}

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


def write_docs(root):
    """README.md and Codebook are written once; later edits by the team are kept."""
    import csv
    root=Path(root)
    with file_lock(root/CONTROL/'.docs.lock'):
        for package,text in README.items():
            readme=root/package/'README.md';readme.parent.mkdir(parents=True,exist_ok=True)
            if not readme.exists():readme.write_text(text,encoding='utf-8')
            book=root/package/'metadata'/'codebook.csv';book.parent.mkdir(parents=True,exist_ok=True)
            if not book.exists():
                with book.open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.writer(f);w.writerow(['ten_bien','mo_ta','kieu_du_lieu','don_vi']);w.writerows(CODEBOOK)
