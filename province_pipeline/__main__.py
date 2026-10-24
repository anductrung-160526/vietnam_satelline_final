"""Run `python -m province_pipeline --help`. No credential values are logged."""
import argparse
import csv
import json
import logging
import os
from pathlib import Path
from .common import atomic_json, load_config, provinces


def main():
    parser = argparse.ArgumentParser(description='63-province Earth Engine → Drive → external disk')
    parser.add_argument('--config', default='province_pipeline/config/local.json')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('prepare-gadm')
    sub.add_parser('sync-boundaries')
    sub.add_parser('inventory')
    plan = sub.add_parser('plan')
    plan.add_argument('--output', default='.province-local/plan.json')
    work = sub.add_parser('work')
    work.add_argument('--plan', required=True)
    work.add_argument('--group', required=True, type=int, choices=range(10))
    recv = sub.add_parser('receive')
    recv.add_argument('--dry-run', action='store_true')
    sub.add_parser('enroll-disk')
    sub.add_parser('aggregate')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | system | province | %(message)s')
    c = load_config(args.config, live=args.command in ('plan','work','inventory','receive','sync-boundaries'))
    if args.command == 'prepare-gadm' or (args.command == 'sync-boundaries' and c.get('boundary_provider') == 'gadm41'):
        from .prepare_gadm import prepare
        print('Prepared GADM research provinces:', prepare(c))
        return
    if args.command == 'enroll-disk':
        from .receiver import enroll
        print('Set volume_marker in the local config to:', enroll(c['local_root']))
        return
    if args.command == 'aggregate':
        from .receiver import verify_volume, single_receiver
        from .aggregate import aggregate
        root = verify_volume(c)
        with single_receiver(root):
            print('Source panels written:', aggregate(root))
        return
    if args.command == 'validate':
        from .boundaries import load_boundaries
        boundaries, metadata = load_boundaries(c)
        from .jobs import generate
        jobs = list(generate(c, boundaries, metadata))
        print(json.dumps({'provinces':len(provinces()), 'selected':len(c['province_codes']),
                          'jobs':len(jobs), 'groups':sorted({j['province']['group_id'] for j in jobs}),
                          'largest_reservation_bytes':max(j['reserved_bytes'] for j in jobs)}, indent=2))
        return
    from .drive import Drive, credentials
    credential_path = os.environ.get('PROVINCE_GOOGLE_CREDENTIALS')
    if not credential_path:
        raise ValueError('Set PROVINCE_GOOGLE_CREDENTIALS to an authorized credentials file; never paste credentials in chat')
    creds = credentials(credential_path)
    drive = Drive(creds)
    if args.command == 'sync-boundaries':
        for field, id_field in [('boundaries','boundaries_drive_id'), ('boundary_metadata','boundary_metadata_drive_id')]:
            if not c.get(id_field):
                raise ValueError(f'Configure {id_field} to retrieve the verified boundary asset')
            path = Path(c[field])
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix('.part')
            drive.download(c[id_field], part)
            part.replace(path)
        from .boundaries import load_boundaries
        load_boundaries(c)  # Verify checksum and crosswalk before any exports.
        return
    if args.command == 'receive':
        from .receiver import run
        run(c, drive, args.dry_run)
        return
    from .boundaries import load_boundaries
    boundaries, metadata = load_boundaries(c)
    from .earth_engine import initialize, inventory, operations
    initialize(c, creds)
    import ee
    def check(job):
        geometry = ee.Geometry(boundaries[job['province']['ma_tinh']]['geometry'])
        result = inventory(dict(c, _province_code=job['province']['ma_tinh']), job['product'], job['period'], geometry)
        return dict(result, ma_tinh=job['province']['ma_tinh'])
    if args.command == 'work':
        from .controller import work
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
        work(c, drive, plan, args.group, boundaries)
        return
    from .jobs import generate
    candidates = list(generate(c, boundaries, metadata))
    if args.command == 'inventory':
        seen, records = set(), []
        for job in candidates:
            key = (job['province']['ma_tinh'],job['product'],job['period'])
            if key not in seen:
                records.append(check(job))
                seen.add(key)
        path = Path('.province-local/source_inventory.csv')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        print(path)
        return
    from .controller import prepare
    plan = prepare(c, drive, candidates, check, operations())
    atomic_json(args.output, plan)
    print('Planned jobs:', len(plan['jobs']))


if __name__ == '__main__':
    main()
