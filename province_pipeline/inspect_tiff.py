"""Local GeoTIFF diagnosis and browser-friendly PNG; never modify the TIFF."""
import json
import struct
import zlib
from pathlib import Path


def inspect(path, output):
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    path=Path(path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with rasterio.open(path) as ds:
        names=list(ds.descriptions)
        report=dict(file=path.name,width=ds.width,height=ds.height,crs=str(ds.crs),
                    transform=list(ds.transform)[:6],nodata=ds.nodata,bands=[],
                    warning='PNG is percentile-stretched display only. Original TIFF values unchanged.')
        counters=[dict(band=i,name=names[i-1],valid_pixels=0,min=None,max=None) for i in range(1,ds.count+1)]
        for _,window in ds.block_windows(1):
            block=ds.read(window=window,masked=True)
            for i,item in enumerate(counters):
                values=block[i].compressed();values=values[np.isfinite(values)]
                item['valid_pixels']+=int(values.size)
                if values.size:
                    item['min']=min(item['min'],float(values.min())) if item['min'] is not None else float(values.min())
                    item['max']=max(item['max'],float(values.max())) if item['max'] is not None else float(values.max())
        for item in counters:item['valid_pct']=100*item['valid_pixels']/(ds.width*ds.height)
        report['bands']=counters
        selected=[names.index(n)+1 for n in ('RED','GREEN','BLUE')] if all(n in names for n in ('RED','GREEN','BLUE')) else [1]*3
        factor=min(1,1024/max(ds.width,ds.height))
        h,w=max(1,round(ds.height*factor)),max(1,round(ds.width*factor))
        data=ds.read(selected,out_shape=(3,h,w),masked=True,resampling=Resampling.nearest)
        rgb=np.zeros((h,w,3),dtype='uint8')
        night=any(n in ('stable_lights','avg_rad') for n in names)
        report['display']='night_log1p_positive_99pct' if night else 'rgb_percentile_2_98'
        for i in range(3):
            good=~np.ma.getmaskarray(data[i]) & np.isfinite(data[i].data)
            values=data[i].data[good]
            if values.size:
                if night:
                    shown=np.log1p(np.maximum(data[i].data,0))
                    positives=np.log1p(values[values>0])
                    high=float(np.percentile(positives,99)) if positives.size else 0
                    if high>0:rgb[:,:,i][good]=(255*np.clip(shown[good]/high,0,1)).astype('uint8')
                    continue
                low,high=np.percentile(values,[2,98])
                if high>low:
                    rgb[:,:,i][good]=(1+254*np.clip((values-low)/(high-low),0,1)).astype('uint8')
                else:
                    rgb[:,:,i][good]=128
        def chunk(kind,content):
            return struct.pack('!I',len(content))+kind+content+struct.pack('!I',zlib.crc32(kind+content)&0xffffffff)
        scan=b''.join(b'\x00'+rgb[y].tobytes() for y in range(h))
        png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+
             chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
        report['has_valid_pixels']=any(b['valid_pixels'] for b in report['bands'])
    (output/(path.stem+'.png')).write_bytes(png)
    (output/(path.stem+'.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report
