"""P1: Moran toàn cục và thay đổi trên miền quan sát chung; không suy diễn nhân quả."""
import math
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, transform
from .build_light_classes import validate_breaks, validate_radiance

CHANGE_NAMES = ['Không sáng ở cả hai năm', 'Giữ lớp sáng', 'Mới sáng', 'Mất sáng',
                'Tăng lớp trong vùng sáng', 'Giảm lớp trong vùng sáng']
CHANGE_COLORS = ['#243049','#b0bac9','#52cf93','#fa7469','#f5c451','#ad84eb']


def queen_neighbors(polygons, tolerance_m=1.0):
    """Queen trên polygon EPSG:6933, dung sai khe ranh giới tối đa 1 m được công bố."""
    if not 0 <= tolerance_m <= 10:raise ValueError('Dung sai tiếp giáp phải trong 0–10 m.')
    codes=sorted(polygons);result={code:[] for code in codes}
    for i,a in enumerate(codes):
        if polygons[a].is_empty or not polygons[a].is_valid:raise ValueError('Polygon không hợp lệ: '+a)
        for b in codes[i+1:]:
            if polygons[a].distance(polygons[b])<=tolerance_m:
                result[a].append(b);result[b].append(a)
    return result


def global_moran(values, neighbors, permutations=9999, seed=20261123):
    """I=n/S0*(z'Wz)/(z'z); chuẩn hóa hàng sau loại thiếu và đảo cô lập."""
    if permutations<99 or permutations>99999:raise ValueError('Cần 99–99999 hoán vị.')
    excluded={};active=set()
    for code in neighbors:
        value=values.get(code)
        if value is None or not np.isfinite(value):excluded[code]='missing_or_unverified_value'
        else:active.add(code)
    # Láng giềng được xác định trước khi xem giá trị; không nối kNN để lấp chỗ trống.
    islands={c for c in active if not active.intersection(neighbors[c])}
    for code in islands:excluded[code]='no_observed_neighbor'
    codes=sorted(active-islands);n=len(codes)
    result=dict(status='insufficient',n=n,total_provinces=len(neighbors),included=codes,excluded=excluded,
                moran_i=None,expected_i=-1/(n-1) if n>1 else None,p_value=None,
                permutation_mean=None,permutation_std=None,permutations=permutations,seed=seed,
                weight_method='queen_distance_tolerance_row_standardized',
                p_method='two_sided_absolute_distance_from_expected_plus_one')
    if n<3:return result
    w=np.array([[float(b in neighbors[a]) for b in codes] for a in codes])
    w/=w.sum(axis=1,keepdims=True)
    z=np.array([values[c] for c in codes],dtype=float);z-=z.mean();den=float(z@z)
    if den==0:
        result['status']='zero_variance';return result
    multiplier=n/w.sum()/den
    observed=float(multiplier*(z@w@z));expected=result['expected_i']
    rng=np.random.default_rng(seed);simulated=np.empty(permutations)
    for i in range(permutations):
        shuffled=rng.permutation(z);simulated[i]=multiplier*(shuffled@w@shuffled)
    p=float((np.count_nonzero(np.abs(simulated-expected)>=abs(observed-expected)-1e-12)+1)/(permutations+1))
    result.update(status='ready' if n==len(neighbors) else 'partial',moran_i=observed,p_value=p,
                  permutation_mean=float(simulated.mean()),permutation_std=float(simulated.std(ddof=1)))
    return result


def aligned_radiance(source, target):
    """Đọc băng 1 về lưới target bằng nearest; NoData/NaN không trở thành 0."""
    validate_radiance(source)
    data=source.read(1,masked=True).astype('float64').filled(np.nan)
    if np.any(np.isfinite(data)&(data<0)):raise ValueError('Ảnh processed còn bức xạ âm.')
    if source.crs==target.crs and source.transform==target.transform and source.shape==target.shape:
        return data,False
    result=np.full(target.shape,np.nan,dtype='float64')
    reproject(data,result,src_transform=source.transform,src_crs=source.crs,src_nodata=np.nan,
              dst_transform=target.transform,dst_crs=target.crs,dst_nodata=np.nan,
              resampling=Resampling.nearest,num_threads=1)
    return result,True


def centroid(values, valid, areas, image, background=0.5):
    # Bức xạ × diện tích giao pixel, trên cùng tập pixel hai năm.
    mass=np.where(valid&(values>=background),values*areas,0.)
    total=float(mass.sum())
    if total<=0:return None
    rows,cols=np.nonzero(mass)
    # Trọng tâm đặt ở tâm ô; có sai số độ phân giải tại pixel giao ranh giới.
    xs,ys=rasterio.transform.xy(image.transform,rows,cols,offset='center')
    xs,ys=transform(image.crs,'EPSG:6933',xs,ys)
    weights=mass[rows,cols]
    x=float(np.dot(xs,weights)/total);y=float(np.dot(ys,weights)/total)
    lon,lat=transform('EPSG:6933','EPSG:4326',[x],[y])
    return dict(longitude=lon[0],latitude=lat[0],radiance_area_sum=total)


def displacement(start,end):
    if start is None or end is None:return dict(centroid_shift_km=None,centroid_bearing_deg=None,direction=None)
    lat1,lat2=map(math.radians,[start['latitude'],end['latitude']]);dlon=math.radians(end['longitude']-start['longitude'])
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    distance=6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))
    if distance<1e-9:return dict(centroid_shift_km=0.,centroid_bearing_deg=None,direction='không dịch chuyển')
    bearing=math.degrees(math.atan2(math.sin(dlon)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dlon)))%360
    names=['Bắc','Đông Bắc','Đông','Đông Nam','Nam','Tây Nam','Tây','Tây Bắc']
    return dict(centroid_shift_km=distance,centroid_bearing_deg=bearing,direction=names[int((bearing+22.5)//45)%8])


def compare_rasters(start_path,end_path,code,area_model,breaks):
    validate_breaks(breaks)
    with rasterio.open(start_path) as start,rasterio.open(end_path) as end:
        validate_radiance(end)
        before,regridded=aligned_radiance(start,end);after,_=aligned_radiance(end,end)
        weights=area_model.weights(code,end);domain=weights>0
        a=domain&np.isfinite(before);b=domain&np.isfinite(after);common=a&b
        first=np.searchsorted(breaks,np.where(common,before,0),side='right')
        last=np.searchsorted(breaks,np.where(common,after,0),side='right')
        # Lớp bức xạ có thể bắt đầu ở 2,00; pixel sáng của chỉ số vẫn theo ngưỡng 1,50.
        from .calculate_ntl import LIT_THRESHOLD
        lit_a=before>=LIT_THRESHOLD['VIIRS'];lit_b=after>=LIT_THRESHOLD['VIIRS']
        classes=np.full(end.shape,255,dtype='uint8')
        masks=[common&~lit_a&~lit_b,common&lit_a&lit_b&(first==last),common&~lit_a&lit_b,
               common&lit_a&~lit_b,common&lit_a&lit_b&(last>first),common&lit_a&lit_b&(last<first)]
        areas=[]
        for i,mask in enumerate(masks):classes[mask]=i;areas.append(float(weights[mask].sum()))
        common_area=float(weights[common].sum());province_area=area_model.areas[code]
        if not math.isclose(sum(areas),common_area,rel_tol=1e-10,abs_tol=1e-8):raise ValueError('Tổng diện tích thay đổi không cân bằng.')
        transitions=[dict(from_class=i,to_class=j,area_km2=float(weights[common&(first==i)&(last==j)].sum())) for i in range(5) for j in range(5)]
        delta=np.full(end.shape,-9999.,dtype='float32');delta[common]=(after[common]-before[common]).astype('float32')
        if not np.isfinite(delta[common]).all():raise ValueError('Chênh lệch bức xạ không hữu hạn.')
        if np.any(delta[common]==-9999.):raise ValueError('Giá trị chênh lệch trùng NoData; cần chọn mã NoData khác trước khi xuất.')
        ca=centroid(before,common,weights,end);cb=centroid(after,common,weights,end)
        summary=dict(status='ready' if common_area>0 else 'no_common_observations',
                     grid_reprojected=regridded,target_crs=str(end.crs),target_transform=list(end.transform),
                     width=end.width,height=end.height,resampling='nearest',area_km2=province_area,
                     common_area_km2=common_area,common_area_pct=100*common_area/province_area,
                     start_only_area_km2=float(weights[a&~b].sum()),end_only_area_km2=float(weights[b&~a].sum()),
                     neither_area_km2=float(weights[domain&~a&~b].sum()),
                     outside_target_grid_area_km2=max(0.,province_area-float(weights.sum())),
                     change_areas_km2=areas,lit_gain_km2=areas[2],lit_loss_km2=areas[3],lit_net_km2=areas[2]-areas[3],
                     lit_net_pct=100*(areas[2]-areas[3])/province_area,
                     mean_radiance_change=float(np.sum((after[common]-before[common])*weights[common])/common_area) if common_area else None,
                     centroid_start=ca,centroid_end=cb,**displacement(ca,cb),transitions=transitions)
        profile=dict(driver='GTiff',width=end.width,height=end.height,count=1,crs=end.crs,transform=end.transform)
    return summary,classes,delta,profile
