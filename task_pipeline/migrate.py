"""Move E:\\SatelliteData\\Task123_branches\\<NNN_NNN>\\ into the shared layout.

Moves only (same volume rename): nothing is deleted or overwritten. Safe to re-run.
    package images        -> <root>/<package>/...            (same package-relative path)
    old day images        -> <root>/_legacy/<NNN_NNN>/...    (monthly float64, 10 bands)
    old data_processed    -> <root>/_legacy/<NNN_NNN>/...    (EE tables, recomputed locally)
    state/receipts/etc.   -> <root>/_control/<NNN_NNN>/...
A file whose target exists with identical content stays in place (reported duplicate);
different content is never overwritten (reported conflict).
"""
import json
import os
from datetime import datetime
from pathlib import Path
from province_pipeline.receiver import hashes
from province_pipeline.common import atomic_json
from .paths import PACKAGES,CONTROL,LEGACY,append_log,ensure_packages

SKIP={'.work','.receiver.lock'}
OLD='Task123_branches'


def legacy(relative):
    parts=relative.split('/')
    if len(parts)>2 and parts[1]=='data_processed':
        return True
    # New day images end with _sr6 (int16, 6 bands); older day TIFFs are kept aside.
    return (len(parts)>3 and parts[1:3]==['raw_data','DAY'] and parts[-1].endswith('.tif')
            and not parts[-1].endswith('_sr6.tif'))


def move(src,dst,report):
    if dst.exists():
        if dst.is_file() and src.stat().st_size==dst.stat().st_size and hashes(src)[1]==hashes(dst)[1]:
            report['duplicates'].append(str(src))
        else:
            report['conflicts'].append(dict(source=str(src),target=str(dst)))
        return
    dst.parent.mkdir(parents=True,exist_ok=True)
    os.replace(src,dst)
    report['moved']+=1


def prune(folder):
    for path in sorted(Path(folder).rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def migrate(root):
    root=Path(root);old=root/OLD
    report=dict(moved=0,legacy=0,duplicates=[],conflicts=[],branches=[])
    if not old.is_dir():
        return report
    ensure_packages(root)
    for branch in sorted(p for p in old.iterdir() if p.is_dir()):
        report['branches'].append(branch.name)
        control=root/CONTROL/branch.name
        for entry in sorted(branch.iterdir()):
            if entry.name in SKIP:
                continue
            files=[entry] if entry.is_file() else sorted(p for p in entry.rglob('*') if p.is_file())
            for src in files:
                relative=src.relative_to(branch).as_posix()
                if entry.name in PACKAGES:
                    if legacy(relative):
                        before=report['moved'];move(src,root/LEGACY/branch.name/relative,report)
                        report['legacy']+=report['moved']-before
                        continue
                    move(src,root/relative,report)
                else:
                    move(src,control/relative,report)
        prune(branch)
    if old.exists():prune(old)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    atomic_json(root/CONTROL/f'migration_{stamp}.json',report)
    for package in PACKAGES:
        append_log(root,package,'Chuyển cấu trúc',f"Chuyển dữ liệu từ {OLD}: {report['moved']} file, "
                   f"{report['legacy']} file sang _legacy, {len(report['duplicates'])} trùng, {len(report['conflicts'])} xung đột")
    return report


def main(root):
    report=migrate(root)
    print(json.dumps(dict(report,duplicates=len(report['duplicates']),conflicts=report['conflicts'][:20]),ensure_ascii=False,indent=2))
    return 1 if report['conflicts'] else 0
