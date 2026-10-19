import unittest
from accendino.machine import Machine

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
        m.crossPlatformFileChooser = lambda builder, local, target, arch: f'{builder}:{local}:{target}:{arch}'
        self.assertEqual(m.getCrossPlatformFile('meson'), 'meson:Ubuntu:emscripten:wasm32')
