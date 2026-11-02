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
from pathlib import Path
from province_pipeline.common import atomic_json
from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
from .paths import CONTROL,file_lock,append_log

NODATA=-9999
DAY_BANDS=['BLUE','GREEN','RED','NIR','SWIR1','SWIR2']
INDICES=['NDVI','NDBI','MNDWI','BSI']
LIT_THRESHOLD_VIIRS=1.5
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


def up_to_date(target,inputs):
    """True when target exists and was built from exactly these inputs."""
    import rasterio
    if not Path(target).exists():return False
    try:
        with rasterio.open(target) as ds:
            return json.loads(ds.tags().get('INPUT_STAMP','null'))==stamp(inputs)
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
        if all(up_to_date(t,inputs) for t in targets.values()):
            out.update({f'{year}-{m:02}':t for m,t in targets.items()});continue
        sources=[rasterio.open(x) for x in inputs]
        try:
            first=sources[0];profile=zstd_profile(first.profile,1,'float32')
            blocks={m:[] for m,_ in months};spikes=0
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
            for m,path in months:
                write(targets[m],profile,['avg_rad_filtered'],blocks[m],
                      dict(SOURCE='VIIRS_MONTHLY',PERIOD=f'{year}-{m:02}',UNIT='nW/cm2/sr',HARMONIZATION='PENDING',
                           FILTER='cf_cvg=0->NoData; negative->0; value>max(3*annual median, median+5)->annual median',
                           SPIKES_CAPPED_IN_YEAR=str(spikes)),inputs)
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
        if up_to_date(target,inputs):
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
            write(target,profile,['avg_rad_annual'],blocks(),
                  dict(SOURCE='MEDIAN_OF_FILTERED_VIIRS_MONTHS',YEAR=year,UNIT='nW/cm2/sr',
                       HARMONIZATION='PENDING',MONTHS_USED=str(len(inputs))),inputs)
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
    row=dict(so_pixel_hop_le=n,dt_hop_le_km2=round(area,3),cua_so_ngay=tags.get('WINDOW_DAYS',''),
             bo_suu_tap=tags.get('COLLECTIONS',''))
    for k,(s,s2) in acc.items():
        mean=s/n if n else None
        row[k+'_mean']=round(mean,6) if mean is not None else None
        row[k+'_std']=round(math.sqrt(max(s2/n-mean*mean,0)),6) if n else None
    return row


def ntl_stats(path,threshold=None):
    import numpy as np
    import rasterio
    total=0.0;n=0;lit=0;mx=None
    with rasterio.open(path) as ds:
        for w in windows(ds.height,ds.width):
            x=ds.read(1,window=w).astype('float64');x=x[x!=NODATA]
            if not x.size:continue
            total+=x.sum();n+=x.size;mx=max(mx or x.max(),x.max())
            if threshold is not None:lit+=int((x>=threshold).sum())
    return dict(sol_ntl=round(total,4) if n else None,so_pixel_hop_le=n,max_ntl=round(float(mx),4) if mx is not None else None,
                mean_ntl=round(total/n,6) if n else None,so_pixel_sang=lit if threshold is not None else None)


def pct(cur,prev):
    return round(100*(cur/prev-1),4) if cur is not None and prev not in (None,0) and prev>0 else None


class Cache:
    """Per-file statistics cache keyed by size+mtime, so re-runs only read changed files."""
    def __init__(self,path):
        self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
    def get(self,path,compute):
        st=Path(path).stat();key=str(path);sig=[st.st_size,st.st_mtime_ns]
        hit=self.data.get(key)
        if hit and hit['sig']==sig:return hit['row']
        row=compute(path);self.data[key]=dict(sig=sig,row=row);return row
    def save(self):
        atomic_json(self.path,self.data)


def base(p,nam,thang,nguon,area):
    row=dict(ma_tinh=p['ma_tinh'],ten_tinh=p['ten_tinh'],nam=int(nam))
    if thang is not None:row['thang']=int(thang)
    row.update(nguon_anh=nguon,dt_tu_nhien_km2=round(area,3))
    return row


def day_rows(province,status,raw,area,cache):
    """status: {(product,period): job status}; raw: {(product,period): path}."""
    rows=[]
    for (product,period),state in sorted(status.items()):
        if product not in SENSOR:continue
        row=base(province,period[:4],period[5:],'Landsat' if product=='LANDSAT' else 'Sentinel-2',area)
        collection='TOA' if product=='SENTINEL2' and int(period[:4])<2019 else 'SR'
        row['loai_phan_xa']=collection
        if (product,period) in raw:
            row.update(cache.get(raw[(product,period)],day_stats))
            row['ty_le_hop_le_pct']=round(100*row['dt_hop_le_km2']/area,2) if area else None
            row['trang_thai']='OK'+('_TOA' if collection=='TOA' else '')
        else:
            row['trang_thai']=state or 'CHUA_CO_ANH'
        rows.append(row)
    return rows


def ntl_monthly_rows(province,filtered,area,cache):
    rows=[];by={}
    for period,path in sorted(filtered.items()):
        row=base(province,period[:4],period[5:],'VIIRS',area)
        row.update(cache.get(path,lambda x:ntl_stats(x,LIT_THRESHOLD_VIIRS)))
        row['mat_do_ntl']=round(row['sol_ntl']/area,6) if row['sol_ntl'] is not None and area else None
        by[period]=row;rows.append(row)
    for period,row in by.items():
        prev=by.get(f'{int(period[:4])-1}-{period[5:]}')
        row['thay_doi_ntl_yoy_pct']=pct(row['sol_ntl'],prev['sol_ntl']) if prev else None
        row['hieu_chinh']='PENDING'
    return rows


def ntl_annual_rows(province,dmsp,viirs,area,cache):
    rows=[];overlap=None;prev=None
    for year in range(2004,2026):
        y=str(year)
        if year<=2013 and y in dmsp:path,src=dmsp[y],'DMSP'
        elif year>=2014 and y in viirs:path,src=viirs[y],'VIIRS'
        else:path,src=None,'DMSP' if year<=2013 else 'VIIRS'
        row=base(province,year,None,src,area)
        if path:
            row.update(cache.get(path,ntl_stats))
            row['mat_do_ntl']=round(row['sol_ntl']/area,6) if row['sol_ntl'] is not None and area else None
        else:
            row.update(sol_ntl=None,mat_do_ntl=None)
        same=prev is not None and prev['nguon_anh']==src
        row['thay_doi_ntl_pct']=pct(row['sol_ntl'],prev['sol_ntl']) if same else None
        row['ghi_chu']='' if same or prev is None else 'DOI_NGUON_ANH_CHUA_HIEU_CHINH'
        row['hieu_chinh']='PENDING';row['trang_thai']='OK' if path else 'CHUA_CO_ANH'
        rows.append(row);prev=row
    if '2013' in dmsp and '2013' in viirs:
        d=cache.get(dmsp['2013'],ntl_stats);v=cache.get(viirs['2013'],ntl_stats)
        overlap=dict(ma_tinh=province['ma_tinh'],ten_tinh=province['ten_tinh'],nam=2013,
                     sol_dmsp=d['sol_ntl'],sol_viirs=v['sol_ntl'],dt_tu_nhien_km2=round(area,3))
    return rows,overlap


TABLES={
    'day_indices_monthly':DAY_PACKAGE,
    'ntl_monthly':NTL_PACKAGE,
    'ntl_annual':NTL_PACKAGE,
    'ntl_overlap_2013':NTL_PACKAGE,
}
KEYS=('ma_tinh','nam','thang','nguon_anh')


def write_part(control,name,rows):
    import pandas as pd
    path=Path(control)/'tables'/f'{name}.csv';path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix('.csv.part')
    pd.DataFrame(rows).to_csv(part,index=False,encoding='utf-8-sig');part.replace(path)
    return path


def merge(root):
    """Combine every branch's table parts into the shared data_processed files (.csv/.xlsx/.dta)."""
    import pandas as pd
    root=Path(root);written=[]
    with file_lock(root/CONTROL/'.tables.lock'):
        for name,package in TABLES.items():
            parts=sorted(root.glob(f'{CONTROL}/*/tables/{name}.csv'))
            if not parts:continue
            frames=[pd.read_csv(p,dtype={'ma_tinh':str},encoding='utf-8-sig') for p in parts if p.stat().st_size]
            if not frames:continue
            frame=pd.concat(frames,ignore_index=True)
            keys=[k for k in KEYS if k in frame.columns]
            frame=frame.drop_duplicates(subset=keys,keep='last').sort_values(keys).reset_index(drop=True)
            dest=root/package/'data_processed';dest.mkdir(parents=True,exist_ok=True)
            for suffix,save in (('.csv',lambda f,p:f.to_csv(p,index=False,encoding='utf-8-sig')),
                                ('.xlsx',lambda f,p:f.to_excel(p,index=False)),
                                ('.dta',lambda f,p:f.to_stata(p,write_index=False,version=118))):
                target=dest/(name+suffix);tmp=target.with_name(target.stem+'.part'+suffix)
                try:
                    save(frame,tmp);tmp.replace(target);written.append(target)
                except ImportError:
                    tmp.unlink(missing_ok=True)   # optional writer (openpyxl) not installed
    return written


README={
 NTL_PACKAGE:"""# VN_NTL_Panel_2004_2025

Bộ dữ liệu ánh sáng ban đêm cấp tỉnh, 63 tỉnh, thành phố (trước sáp nhập), 2004–2025.

- raw_data/NTL/DMSP/: DMSP-OLS stable_lights tổng hợp năm 2004–2013 (Earth Engine, NOAA/NCEI), cắt theo tỉnh.
- raw_data/NTL/VIIRS/: VIIRS DNB tháng (VCMSLCFG, thiếu tháng dùng VCMCFG) 2013–2025; ảnh năm VIIRS tổng hợp từ ảnh tháng (data_intermediate).
- data_intermediate/: ảnh đã lọc nhiễu, cắt ranh giới (DMSP/, VIIRS_MONTHLY/, VIIRS_ANNUAL/). Hiệu chỉnh liên kết DMSP–VIIRS: PENDING.
- data_processed/: ntl_annual, ntl_monthly, ntl_overlap_2013 (.csv/.xlsx/.dta), khóa ma_tinh + nam (+ thang).
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
- data_processed/: day_indices_monthly (.csv/.xlsx/.dta), khóa ma_tinh + nam + thang.
- metadata/: Codebook. logs/: nhật ký cập nhật. Mã nguồn: repository vietnam_satelline_final (task_pipeline/).
""",
}

CODEBOOK=[
 ('ma_tinh','Mã tỉnh, thành phố theo Cục Thống kê (63 tỉnh trước sáp nhập)','String',''),
 ('ten_tinh','Tên tỉnh, thành phố','String',''),
 ('nam','Năm','Numeric',''),('thang','Tháng','Numeric',''),
 ('nguon_anh','DMSP, VIIRS, Landsat hoặc Sentinel-2','String',''),
 ('dt_tu_nhien_km2','Diện tích tự nhiên của tỉnh (polygon GADM 4.1, EPSG:6933)','Numeric','km²'),
 ('sol_ntl','Quy mô kinh tế đêm: tổng giá trị pixel hợp lệ trong tỉnh','Numeric','DN (DMSP) / nW/cm²/sr (VIIRS)'),
 ('mat_do_ntl','Mật độ: sol_ntl / dt_tu_nhien_km2','Numeric','đơn vị bức xạ/km²'),
 ('thay_doi_ntl_pct','Mức độ thay đổi so với năm trước, chỉ khi cùng nguồn ảnh','Numeric','%'),
 ('thay_doi_ntl_yoy_pct','Thay đổi so với cùng tháng năm trước (VIIRS)','Numeric','%'),
 ('hieu_chinh','Trạng thái hiệu chỉnh liên kết DMSP–VIIRS','String',''),
 ('so_pixel_sang','Số pixel VIIRS ≥ 1,5 nW/cm²/sr','Numeric','pixel'),
 ('loai_phan_xa','SR (phản xạ bề mặt) hoặc TOA (Sentinel-2 2015–2018)','String',''),
 ('<KÊNH>_mean / _std','Trung bình / độ lệch chuẩn của phản xạ kênh (BLUE..SWIR2) và chỉ số NDVI, NDBI, MNDWI, BSI trên pixel hợp lệ','Numeric','phản xạ (0–1) / không thứ nguyên'),
 ('ty_le_hop_le_pct','Diện tích pixel hợp lệ / diện tích tự nhiên','Numeric','%'),
 ('trang_thai','OK, OK_TOA, MISSING_SOURCE (không có ảnh), INSUFFICIENT_QUALITY, CHUA_CO_ANH','String',''),
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
