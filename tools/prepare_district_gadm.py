"""Prepare the unmodified GADM 4.1 level-2 files for Earth Engine table upload."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import struct
import urllib.request
import zipfile

URL = 'https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip'
MEMBERS = [f'gadm41_VNM_2.{ext}' for ext in ('shp', 'shx', 'dbf', 'prj', 'cpg')]
FIELDS = ['GID_1', 'NAME_1', 'GID_2', 'NAME_2', 'TYPE_2']


def dbf_rows(data, encoding):
    f = io.BytesIO(data)
    head = f.read(32)
    count, header_len, record_len = struct.unpack('<IHH', head[4:12])
    fields = []
    while True:
        desc = f.read(32)
        if not desc or desc[0] == 0x0D:
            break
        fields.append((desc[:11].split(b'\0')[0].decode('ascii'), desc[16]))
    f.seek(header_len)
    rows = []
    for _ in range(count):
        record = f.read(record_len)
        if not record or record[:1] == b'*':
            continue
        pos, row = 1, {}
        for name, size in fields:
            row[name] = record[pos:pos + size].decode(encoding).strip()
            pos += size
        rows.append(row)
    return rows


def prepare(archive, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = Path(archive)
    with zipfile.ZipFile(archive) as source:
        if source.testzip():
            raise ValueError('GADM archive has a corrupt ZIP member')
        encoding = source.read('gadm41_VNM_2.cpg').decode().strip()
        if encoding.upper().replace('-', '') == 'UTF8':
            encoding = 'utf-8'
        rows = dbf_rows(source.read('gadm41_VNM_2.dbf'), encoding)
        if len(rows) != 710 or len({r['GID_2'] for r in rows}) != 710 or len({r['GID_1'] for r in rows}) != 63:
            raise ValueError('GADM level 2 does not match the verified 710 districts / 63 provinces')
        shp, shx = source.read('gadm41_VNM_2.shp'), source.read('gadm41_VNM_2.shx')
        if ((len(shx) - 100) // 8 != len(rows) or struct.unpack('<i', shp[32:36])[0] != 5
                or struct.unpack('>i', shp[24:28])[0] * 2 != len(shp)):
            raise ValueError('Shapefile geometry/index does not match the level-2 DBF')
        pos, geometry_count = 100, 0
        while pos < len(shp):
            record, length = struct.unpack('>ii', shp[pos:pos + 8])
            body = shp[pos + 8:pos + 8 + length * 2]
            if len(body) != length * 2 or len(body) < 44 or struct.unpack('<i', body[:4])[0] != 5:
                raise ValueError('Null or invalid district polygon')
            geometry_count += 1
            pos += 8 + length * 2
        if geometry_count != len(rows):
            raise ValueError('Geometry count differs from DBF record count')
        for name in MEMBERS:
            (output / name).write_bytes(source.read(name))
        target = output / 'gadm41_VNM_2.zip'
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as dest:
            for name in MEMBERS:
                dest.writestr(name, source.read(name))
    with (output / 'districts_l2_admin.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    source_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    target_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / 'SOURCE.md').write_text(
        f'# GADM 4.1 Vietnam, level 2\n\nSource: {URL}\n\n'
        f'Unmodified level-2 components: {", ".join(MEMBERS)}.\n\n'
        f'710 districts; 63 provinces. Shapefile record count and GID_2 uniqueness verified.\n\n'
        f'Original archive SHA-256: `{source_hash}`\n\nPrepared ZIP SHA-256: `{target_hash}`\n\n'
        'GADM attribution and use terms: https://gadm.org/license.html\n', encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', help='Existing original GADM ZIP; otherwise download from the source')
    parser.add_argument('--output', default='artifacts/gadm41_VNM_2')
    args = parser.parse_args()
    archive = Path(args.archive) if args.archive else Path(args.output) / 'gadm41_VNM_shp.zip'
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(URL, headers={'User-Agent': 'VNGIS district preparation'})
        with urllib.request.urlopen(request, timeout=900) as response:
            data = response.read()
        archive.write_bytes(data)
    print(prepare(archive, args.output))
    print('Verified 710 districts / 63 provinces; upload the level-2 ZIP as districts_l2.')


if __name__ == '__main__':
    main()
