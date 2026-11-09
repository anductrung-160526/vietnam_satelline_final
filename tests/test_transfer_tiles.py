"""Chuyển tiles từ máy ảo về ổ E: chỉ lấy tiles, không lấy ảnh ghép.

Ảnh ghép VN_<SẢN PHẨM>_<năm>.tif nặng ~24 GB mỗi năm và dựng lại được từ chính các tile
này bất cứ lúc nào, nên không có lý do gì để kéo nó qua đường truyền. Test chạy thật
script bash trên một cây thư mục giả, với gcloud giả, rồi giải nén và đối chiếu.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'scripts' / 'cloud_vm' / 'dong_goi_tiles.sh'
PACKAGE = 'VN_LandCover_Panel_2004_2025'
UNDER = f'{PACKAGE}/raw_data/DAY/SENTINEL2'


def have_bash():
    return shutil.which('bash') is not None


@unittest.skipUnless(have_bash(), 'cần bash')
class PackageTilesTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / 'root'
        self.bin = Path(self.dir.name) / 'bin'
        self.bin.mkdir(parents=True)
        (self.bin / 'gcloud').write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
        (self.bin / 'gcloud').chmod(0o755)
        for year in (2016, 2024):
            folder = self.root / UNDER / f'VN_SENTINEL2_{year}'
            (folder / 'tiles').mkdir(parents=True)
            for i in range(5):
                (folder / 'tiles' / f't{i}.tif').write_bytes(os.urandom(512))
            (folder / f'VN_SENTINEL2_{year}.vrt').write_text('<VRTDataset/>', encoding='utf-8')
            # Ảnh ghép: phải KHÔNG xuất hiện trong gói.
            (folder / f'VN_SENTINEL2_{year}.tif').write_bytes(os.urandom(200_000))

    def _run(self, *args):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}')
        return subprocess.run(['bash', str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_the_inventory_lists_every_year_and_flags_the_merged_image(self):
        done = self._run('--kiem-ke')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('2016', done.stdout)
        self.assertIn('2024', done.stdout)
        self.assertIn('SENTINEL2', done.stdout)

    def test_the_package_holds_the_tiles_and_the_vrt_but_never_the_merged_image(self):
        done = self._run('--nam', '2016', '--bucket', 'gs://x', '--giu-lai')
        self.assertEqual(done.returncode, 0, done.stderr)
        import tarfile
        with tarfile.open(self.root / 'tiles_SENTINEL2_2016.tar') as archive:
            names = archive.getnames()
        self.assertEqual(sum(1 for n in names if n.endswith('.tif')), 5)
        self.assertIn('VN_SENTINEL2_2016/VN_SENTINEL2_2016.vrt', names)
        # Ảnh ghép 24 GB: không một byte nào được đi qua đường truyền.
        self.assertNotIn('VN_SENTINEL2_2016/VN_SENTINEL2_2016.tif', names)

    def test_only_the_requested_year_is_packaged(self):
        self._run('--nam', '2016', '--bucket', 'gs://x', '--giu-lai')
        self.assertTrue((self.root / 'tiles_SENTINEL2_2016.tar').exists())
        self.assertFalse((self.root / 'tiles_SENTINEL2_2024.tar').exists())

    def test_the_manifest_carries_what_the_windows_side_verifies(self):
        import hashlib
        self._run('--nam', '2016', '--bucket', 'gs://x', '--giu-lai')
        tar = self.root / 'tiles_SENTINEL2_2016.tar'
        manifest = dict(line.split('=', 1) for line in
                        (tar.parent / (tar.name + '.manifest')).read_text(
                            encoding='utf-8').strip().splitlines())
        self.assertEqual(manifest['so_tile'], '5')
        self.assertEqual(manifest['san_pham'], 'SENTINEL2')
        self.assertEqual(manifest['nam'], '2016')
        self.assertEqual(manifest['duong_dan_giai_nen'], UNDER)
        self.assertEqual(manifest['sha256'],
                         hashlib.sha256(tar.read_bytes()).hexdigest())

    def test_extracting_under_the_manifest_path_rebuilds_the_vm_layout(self):
        """Giải nén đúng chỗ thì cây thư mục trên ổ E trùng với trên máy ảo."""
        import tarfile
        self._run('--nam', '2016', '--bucket', 'gs://x', '--giu-lai')
        tar = self.root / 'tiles_SENTINEL2_2016.tar'
        manifest = dict(line.split('=', 1) for line in
                        (tar.parent / (tar.name + '.manifest')).read_text(
                            encoding='utf-8').strip().splitlines())
        o_e = Path(self.dir.name) / 'E'
        dich = o_e / manifest['duong_dan_giai_nen']
        dich.mkdir(parents=True)
        with tarfile.open(tar) as archive:
            archive.extractall(dich, filter='data')
        tiles = o_e / UNDER / 'VN_SENTINEL2_2016' / 'tiles'
        self.assertEqual(len(list(tiles.glob('*.tif'))), 5)
        self.assertTrue((tiles.parent / 'VN_SENTINEL2_2016.vrt').exists())
        self.assertFalse((tiles.parent / 'VN_SENTINEL2_2016.tif').exists())

    def test_a_year_that_does_not_exist_fails_loudly(self):
        done = self._run('--nam', '1999', '--bucket', 'gs://x')
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('1999', done.stderr)

    def test_a_bucket_is_required(self):
        done = self._run('--nam', '2016')
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('bucket', done.stderr.lower())


if __name__ == '__main__':
    unittest.main()
