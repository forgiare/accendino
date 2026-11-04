import os
import pathlib
import tempfile
import unittest
from unittest import mock
from accendino.localdeps import DpkgManager, InPathSubManager, PackageManager, PackageManagerBase, PACKAGES_CACHE_MANIFEST


class TestDpkgCache(unittest.TestCase):

    def _manager(self, cacheDir, installed):
        ''' a DpkgManager with installed {pkg: version}, recording the commands it runs '''
        self.installed = dict(installed)
        self.cmds = []
        self.failing = set()

        def loadInstalled(mgr):
            mgr.allPackages = dict(self.installed)

        def runAsRoot(cmd):
            self.cmds.append(cmd)
            return cmd[1] not in self.failing if len(cmd) > 1 else True

        patches = [
            mock.patch.object(DpkgManager, '_loadInstalled', loadInstalled),
            mock.patch.object(DpkgManager, '_runAsRoot', staticmethod(runAsRoot)),
            mock.patch.object(DpkgManager, '_installedVersions', lambda _self: set(self.installed.items())),
            mock.patch('os.getuid', return_value=0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        mgr = DpkgManager()
        if cacheDir:
            mgr.setCacheDir(cacheDir)
        return mgr

    def _touch(self, d, *names):
        for n in names:
            (pathlib.Path(d) / n).write_bytes(b'')

    def testDebInfo(self):
        self.assertEqual(DpkgManager._debInfo(pathlib.Path('/c/libfoo1_1%3a2.3-1_amd64.deb')), ('libfoo1', '1:2.3-1', 'amd64'))
        self.assertIsNone(DpkgManager._debInfo(pathlib.Path('/c/lock')))

    def testNoCache(self):
        mgr = self._manager(None, {})
        self.assertTrue(mgr.installPackages(['foo']))
        self.assertEqual(self.cmds, [['apt-get', 'install', '-y', '--no-install-recommends', 'foo']])

    def testColdCache(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = self._manager(d, {'gcc': '13'})
            self.assertTrue(mgr.installPackages(['foo']))
            # empty cache: index update, then a regular install keeping the packages in the cache
            self.assertEqual(self.cmds[0], ['apt-get', 'update'])
            self.assertEqual(self.cmds[1][:4], ['apt-get', 'install', '-y', '--no-install-recommends'])
            self.assertIn(f'Dir::Cache::Archives={d}', self.cmds[1])
            self.assertEqual(self.cmds[1][-1], 'foo')

            # a second install doesn't update the index again
            self.cmds.clear()
            self.assertTrue(mgr.installPackages(['bar']))
            self.assertEqual([c[1] for c in self.cmds], ['install'])

    def testWarmCache(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'foo_1.0_amd64.deb', 'libfoo_1.0_amd64.deb', 'gcc_12_amd64.deb')
            mgr = self._manager(d, {'gcc': '13'})
            self.assertTrue(mgr.installPackages(['foo']))
            # no index update, the cached packages that aren't installed are given
            self.assertEqual(len(self.cmds), 1)
            cmd = self.cmds[0]
            self.assertIn('--no-download', cmd)
            self.assertEqual(cmd[-3:], [os.path.join(d, 'foo_1.0_amd64.deb'), os.path.join(d, 'libfoo_1.0_amd64.deb'), 'foo'])

    def testWarmCacheFallback(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'foo_1.0_amd64.deb')
            mgr = self._manager(d, {})
            self.failing.add('install')
            self.assertFalse(mgr.installPackages(['foo', 'bar']))
            self.assertEqual([c[1] for c in self.cmds], ['install', 'update', 'install'])
            self.assertNotIn('--no-download', self.cmds[2])

    def testPruneAndManifest(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'foo_1.0_amd64.deb', 'foo_0.9_amd64.deb', 'libfoo_1%3a2.0_amd64.deb', 'lock')
            os.makedirs(os.path.join(d, 'partial'))
            mgr = self._manager(d, {})
            self.installed.update({'foo': '1.0', 'libfoo': '1:2.0'})
            self.assertTrue(mgr.installPackages(['foo']))

            self.assertEqual(sorted(os.listdir(d)), [PACKAGES_CACHE_MANIFEST, 'foo_1.0_amd64.deb', 'libfoo_1%3a2.0_amd64.deb'])
            self.assertEqual(pathlib.Path(d, PACKAGES_CACHE_MANIFEST).read_text(), 'foo 1.0 amd64\nlibfoo 1:2.0 amd64\n')


class TestCacheDirs(unittest.TestCase):

    def testSubManagers(self):
        class NoCacheManager(PackageManagerBase):
            pass

        with mock.patch.object(DpkgManager, '_loadInstalled', lambda _self: None):
            dpkg = DpkgManager()
        other = NoCacheManager('other')
        mgr = PackageManager('test', {'': dpkg, 'other': other, 'path': InPathSubManager()})
        with self.assertLogs(level='WARNING') as logs:
            mgr.setCacheDir('/cache')
        # each manager that can cache has its own directory, the others are warned about
        self.assertEqual(dpkg.cacheDir, pathlib.Path('/cache/dpkg'))
        self.assertIsNone(other.cacheDir)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('other', logs.output[0])


if __name__ == '__main__':
    unittest.main()
