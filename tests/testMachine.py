import os
import unittest
from accendino.machine import Machine
from accendino.toolchain import CROSS_FILE_DIR, ClangToolChain, EmscriptenToolChain, GccToolChain, MingwToolChain
from accendino.utils import getArchLibDir, pkgConfigDirs

class Test(unittest.TestCase):

    def testNative(self):
        m = Machine('Ubuntu', '24.04', 'Ubuntu', 'x86_64', 'x86_64')
        self.assertFalse(m.crossCompilation)
        self.assertEqual(m.libdir, 'lib')
        self.assertEqual(m.packageKeys(), ('Ubuntu', 'Ubuntu 24.04'))

    def testCross(self):
        m = Machine('Fedora', '40', 'mingw', 'x86_64', 'x86_64')
        self.assertTrue(m.crossCompilation)
        self.assertEqual(m.libdir, 'lib64')
        self.assertEqual(m.packageKeys(), ('Fedora->mingw@x86_64', 'Fedora 40->mingw@x86_64'))

        # same distrib, other arch
        m = Machine('Ubuntu', '24.04', 'Ubuntu', 'arm64', 'x86_64')
        self.assertTrue(m.crossCompilation)

    def testCrossPlatformFile(self):
        m = Machine('Ubuntu', '24.04', 'emscripten', 'wasm32', 'x86_64')
        m.toolchainObj = EmscriptenToolChain(None, machine=m)
        self.assertEqual(m.getCrossPlatformFile('meson'), str(CROSS_FILE_DIR / 'emscripten.meson'))

        # the chooser of the accendino files wins, the toolchain's file is used when it returns None
        m.crossPlatformFileChooser = lambda builder, machine: f'/x/{builder}-{machine.arch}' if builder == 'cmake' else None
        self.assertEqual(m.getCrossPlatformFile('cmake'), '/x/cmake-wasm32')
        self.assertEqual(m.getCrossPlatformFile('meson'), str(CROSS_FILE_DIR / 'emscripten.meson'))

    def testMingwCrossFile(self):
        m = Machine('Ubuntu', '24.04', 'mingw', 'x86_64', 'x86_64')
        m.toolchainObj = MingwToolChain(None, machine=m)
        self.assertEqual(m.getCrossPlatformFile('cmake'), str(CROSS_FILE_DIR / 'debian-mingw64.cmake'))

        m = Machine('Fedora', '40', 'mingw', 'i686', 'x86_64')
        m.toolchainObj = MingwToolChain(None, machine=m)
        self.assertEqual(m.getCrossPlatformFile('meson'), '/usr/share/mingw/toolchain-mingw32.meson')

    def testNoCrossFile(self):
        m = Machine('Ubuntu', '24.04', 'Ubuntu', 'arm64', 'x86_64')
        m.toolchainObj = GccToolChain(None, machine=m)
        self.assertIsNone(m.getCrossPlatformFile('cmake'))

    def testDarwinCross(self):
        m = Machine('Darwin', '15.0', 'Darwin', 'x86_64', 'arm64')
        self.assertTrue(m.crossCompilation)
        m.toolchainObj = ClangToolChain(None, machine=m)
        self.assertEqual(m.getCrossPlatformFile('cmake'), str(CROSS_FILE_DIR / 'darwin-x86_64.cmake'))
        self.assertIn('-arch x86_64', m.toolchainObj.extraEnv(['c'])['CFLAGS'])

        m = Machine('Darwin', '15.0', 'Darwin', 'arm64', 'x86_64')
        m.toolchainObj = ClangToolChain(None, machine=m)
        self.assertEqual(m.getCrossPlatformFile('meson'), str(CROSS_FILE_DIR / 'darwin-arm64.meson'))

        # native builds have no -arch and no cross file
        m = Machine('Darwin', '15.0', 'Darwin', 'arm64', 'arm64')
        m.toolchainObj = ClangToolChain(None, machine=m)
        self.assertIsNone(m.getCrossPlatformFile('cmake'))
        self.assertNotIn('CFLAGS', m.toolchainObj.extraEnv(['c']))

    def testCrossFilesExist(self):
        for name in ('darwin-x86_64', 'darwin-arm64'):
            for builder in ('cmake', 'meson'):
                self.assertTrue((CROSS_FILE_DIR / f'{name}.{builder}').exists())

    def testPkgConfigDirs(self):
        os.environ['HOMEBREW_PREFIX'] = '/opt/homebrew'
        try:
            dirs = pkgConfigDirs('/p', 'lib', 'Darwin', 'arm64', None)
            self.assertEqual(dirs, ['/p/lib/pkgconfig', '/p/share/pkgconfig', '/opt/homebrew/lib/pkgconfig',
                                    '/opt/homebrew/share/pkgconfig', '/usr/share/pkgconfig'])
            # the Homebrew libraries are not for the target architecture
            self.assertEqual(pkgConfigDirs('/p', 'lib', 'Darwin', 'x86_64', '/x', True), ['/p/lib/pkgconfig', '/p/share/pkgconfig'])
        finally:
            del os.environ['HOMEBREW_PREFIX']

        self.assertEqual(pkgConfigDirs('/p', 'lib', 'Ubuntu', 'x86_64', None),
                         ['/p/lib/pkgconfig', '/p/share/pkgconfig', '/p/lib/x86_64-linux-gnu/pkgconfig',
                          '/usr/lib/x86_64-linux-gnu/pkgconfig', '/usr/share/pkgconfig'])
        self.assertIsNone(getArchLibDir('Darwin', 'arm64'))
        self.assertEqual(getArchLibDir('Debian', 'arm64'), 'aarch64-linux-gnu')
