import unittest
from accendino.machine import Machine
from accendino.toolchain import CROSS_FILE_DIR, EmscriptenToolChain, GccToolChain, MingwToolChain

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
        m = Machine('Ubuntu', '24.04', 'Ubuntu', 'aarch64', 'x86_64')
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
        m = Machine('Ubuntu', '24.04', 'Ubuntu', 'aarch64', 'x86_64')
        m.toolchainObj = GccToolChain(None, machine=m)
        self.assertIsNone(m.getCrossPlatformFile('cmake'))
