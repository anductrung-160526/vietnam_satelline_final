"""Canonical data-package layout, shared by Drive and the external disk.

Layout is storage metadata, not a new scientific job. Keep existing job IDs and
filenames so changing folders cannot cause satellite data to be fetched twice.
"""
from pathlib import PurePosixPath
from .sources import NTL_PACKAGE, DAY_PACKAGE

LAYOUT_VERSION = 3
COMMON = ('data_intermediate','data_processed','metadata','code','docs','logs','dashboard')
PACKAGE_DIRECTORIES = {
    NTL_PACKAGE: (*COMMON, 'raw_data/NTL/DMSP','raw_data/NTL/VIIRS'),
    DAY_PACKAGE: (*COMMON, 'samples','raw_data/DAY/LANDSAT','raw_data/DAY/SENTINEL2'),
}


def province_name(job):
    p=job['province']
    return p['ma_tinh']+'_'+p['slug']


def output_directory(job):
    product=job['product']
    night=product.startswith(('DMSP','VIIRS'))
    package=NTL_PACKAGE if night else DAY_PACKAGE
    province=province_name(job)
    sensor='VIIRS' if product.startswith('VIIRS') else product.split('_')[0]
    if job['kind']=='table':
        return f'{package}/data_processed/{province}/source/{product}'
    if job['variant']=='filtered':
        return f'{package}/data_intermediate/{province}'
    return f'{package}/raw_data/{"NTL" if night else "DAY"}/{sensor}/{province}'


def canonical_job(job):
    return dict(job,local_directory=output_directory(job),layout_version=LAYOUT_VERSION)


def relative_output(job,filename):
    if PurePosixPath(filename).name != filename or '\\' in filename or ':' in filename:
        raise ValueError('Unsafe output filename')
    return output_directory(job)+'/'+filename


def ensure_drive_packages(drive,root):
    for package,paths in PACKAGE_DIRECTORIES.items():
        base=drive.folder(root,package)
        for relative in paths:
            parent=base
            for name in relative.split('/'):
                parent=drive.folder(parent,name)


def ensure_output_folder(drive,root,job):
    parent=root
    parts=output_directory(job).split('/')
    for name in parts:
        parent=drive.folder(parent,name)
    return parent,parts[-1]


def local_manifest(manifest):
    """Map old remote manifests to canonical disk paths without changing remote metadata."""
    job=manifest['job']
    # Older third-party/minimal manifests without canonical province identity stay readable.
    if not job.get('province',{}).get('slug'):
        return manifest
    updated=canonical_job(job)
    files=[]
    for original in manifest['files']:
        target=relative_output(updated,original['name'])
        legacy=list(original.get('legacy_local_relative_paths',[]))
        if original['local_relative_path']!=target:
            legacy.append(original['local_relative_path'])
        files.append(dict(original,local_relative_path=target,
                          legacy_local_relative_paths=list(dict.fromkeys(legacy))))
    return dict(manifest,job=updated,files=files,local_layout_version=LAYOUT_VERSION)


def version2_directory(job):
    directory=output_directory(job)
    if job['kind']=='table':
        return directory
    if job['variant']=='filtered':
        product=job['product']
        sensor='VIIRS' if product.startswith('VIIRS') else product.split('_')[0]
        return directory+'/'+sensor+'/'+job['period']
    return directory+'/'+job['period']
