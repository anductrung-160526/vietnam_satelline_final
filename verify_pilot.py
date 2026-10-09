"""Verify district TIFFs and CSVs for the configured cross-year period."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import ExitStack

import numpy as np
import pandas as pd
import rasterio

import vngis_2024 as v


def load_status(root):
    states = {}
    for path in sorted(Path(root, '_control', 'status').glob('status_*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                state = json.loads(line)
                if v.current_status(state):
                    states[state['gid_2']] = state
            except (ValueError, KeyError):
                continue
    return states


def check_tif(path, bands, scale, night=False):
    ok, empty, note = v.inspect_tif(path, bands)
    if not ok or empty:
        return 'FAIL', note or 'Không có pixel hợp lệ'
    with rasterio.open(path) as src:
        if not night and v.DAY_FORMAT == 'int16':
            if any(dtype != 'int16' for dtype in src.dtypes) or src.nodata != v.DAY_NODATA:
                return 'FAIL', 'TIFF ngày phải là Int16 với NoData -32768'
            if any(abs(s - 1.0 / v.DAY_SCALE_INV) > 1e-12 for s in src.scales) or any(src.offsets):
                return 'FAIL', 'Sai scale/offset Int16'
        elif any(np.dtype(dtype).kind != 'f' for dtype in src.dtypes):
            return 'FAIL', 'TIFF không có kiểu float'
        if night and any(dtype != 'float64' for dtype in src.dtypes):
            return 'FAIL', 'Ảnh đêm phải là float64'
        if any(abs(abs(res) * 111319.49 - scale) > scale * 0.01 for res in (src.transform.a, src.transform.e)):
            return 'FAIL', 'Độ phân giải khác cấu hình'
    return 'PASS', ''


def verify_district(root, gid, state, day_csv, night_csv):
    checks = [('Trạng thái', 'PASS' if v.district_complete(state) and state.get('status') == 'done' else 'FAIL',
               state.get('status', 'không có trạng thái'))]
    ctx = None
    for frame in (day_csv, night_csv):
        if frame is not None and all(col in frame for col in v.ADM_COLS):
            metadata = frame[frame.GID_2 == gid]
            if not metadata.empty:
                ctx = v.build_ctx(metadata.iloc[0].to_dict())
                break
    for label, sub, name, bands, scale in [('Ngày', 'Day', v.day_name, v.DAY_BANDS, 20),
                                          ('Đêm', 'Night', v.night_name, 2, 500)]:
        failed = []
        for period in v.PERIODS:
            filename = name({'gid2': gid}, period)
            if ctx is not None:
                folder = ctx['rel_day_dir' if sub == 'Day' else 'rel_night_dir']
                expected = Path(root, folder, filename)
                files = [expected] if expected.is_file() else []
            else:
                files = list(Path(root, sub).glob(f'*/{gid}_*/{filename}'))
            if len(files) != 1:
                failed.append(v.month_key(period) + ': thiếu hoặc trùng TIFF')
                continue
            level, note = check_tif(files[0], bands, scale, night=sub == 'Night')
            if level != 'PASS':
                failed.append(v.month_key(period) + ': ' + note)
        checks.append((f'TIFF {label}', 'FAIL' if failed else 'PASS', '; '.join(failed) or f'Đủ {len(v.PERIODS)} tháng'))
    for kind, frame, columns in [('Ngày', day_csv, v.DAY_COLUMNS), ('Đêm', night_csv, v.NIGHT_COLUMNS)]:
        if frame is None or 'GID_2' not in frame:
            checks.append((f'CSV {kind}', 'FAIL', 'Không có CSV/GID_2'))
            continue
        data = frame[frame.GID_2 == gid]
        if list(frame.columns) != columns or data.empty:
            checks.append((f'CSV {kind}', 'FAIL', 'Thiếu huyện hoặc sai schema cấp 2'))
            continue
        periods = {(int(r.YEAR), int(r.MONTH)) for r in data.itertuples()}
        ok = (len(data) == len(v.PERIODS) and periods == set(v.PERIODS)
              and not data.duplicated(['GID_2', 'YEAR', 'MONTH']).any()
              and data.DATA_STATUS.eq('ok').all())
        checks.append((f'CSV {kind}', 'PASS' if ok else 'FAIL',
                       f'{len(data)}/{len(v.PERIODS)} dòng; ' + ('đúng năm/tháng' if ok else 'thiếu dữ liệu hoặc sai năm/tháng')))
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root')
    parser.add_argument('--remote')
    parser.add_argument('--report')
    parser.add_argument('--gids', default='')
    args = parser.parse_args()
    with ExitStack() as stack:
        root = args.root
        if args.remote:
            root = stack.enter_context(tempfile.TemporaryDirectory(prefix='vngis_district_verify_'))
            subprocess.run(['rclone', 'copy', args.remote, root, '--exclude', '_control/logs/**',
                            '--exclude', '_control/parts/**', '--transfers', '2'], check=True)
        if not root or not os.path.isdir(root):
            raise SystemExit('Cần --root hoặc --remote hợp lệ')
        states = load_status(root)
        gids = [g.strip() for g in args.gids.split(',') if g.strip()] or sorted(states)
        frames = []
        for name in ['day_indices.csv', 'night_indices.csv']:
            path = Path(root, 'CSV', name)
            frames.append(pd.read_csv(path, dtype={'GID_1': str, 'GID_2': str}) if path.exists() else None)
        failed = not gids
        lines = [f'# Kiểm tra huyện {v.START_MONTH}–{v.END_MONTH}', '']
        if not gids:
            lines.append('FAIL: không có trạng thái huyện thuộc khoảng thời gian này.')
        for gid in gids:
            checks = verify_district(root, gid, states.get(gid) or {}, *frames)
            failed |= any(level == 'FAIL' for _, level, _ in checks)
            lines += [f'## {gid}', '', '| Mục | Kết quả | Ghi chú |', '|---|---|---|']
            lines += [f'| {label} | {level} | {note.replace(chr(124), "/")} |' for label, level, note in checks]
            lines.append('')
        lines.append('**FAIL: chưa đủ dữ liệu.**' if failed else '**PASS: đủ TIFF và CSV cho mọi tháng.**')
        report = Path(args.report) if args.report else Path(root, '_control', 'verify_report.md')
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(report.read_text(encoding='utf-8'))
        if args.remote:
            subprocess.run(['rclone', 'copyto', str(report), f'{args.remote}/_control/verify_report.md'], check=True)
        return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
