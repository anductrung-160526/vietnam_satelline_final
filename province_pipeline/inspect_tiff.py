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
        for i in range(1,ds.count+1):
            count=0;total=0;lo=None;hi=None
            for _,window in ds.block_windows(i):
                data=ds.read(i,window=window,masked=True);values=data.compressed()
                values=values[np.isfinite(values)]
                total+=data.size;count+=values.size
                if values.size:
                    lo=min(lo,float(values.min())) if lo is not None else float(values.min())
                    hi=max(hi,float(values.max())) if hi is not None else float(values.max())
            report['bands'].append(dict(band=i,name=names[i-1],valid_pixels=int(count),
                valid_pct=100*count/total if total else 0,min=lo,max=hi))
        selected=[names.index(n)+1 for n in ('RED','GREEN','BLUE')] if all(n in names for n in ('RED','GREEN','BLUE')) else [1]*3
        factor=min(1,1024/max(ds.width,ds.height))
        h,w=max(1,round(ds.height*factor)),max(1,round(ds.width*factor))
        data=ds.read(selected,out_shape=(3,h,w),masked=True,resampling=Resampling.nearest)
        rgb=np.zeros((h,w,3),dtype='uint8')
        for i in range(3):
            good=~np.ma.getmaskarray(data[i]) & np.isfinite(data[i].data)
            values=data[i].data[good]
            if values.size:
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
