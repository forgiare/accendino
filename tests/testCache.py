import os
import pathlib
import tempfile
import unittest
from accendino.builditems import CMakeBuildArtifact, MesonBuildArtifact, QMakeBuildArtifact
from accendino.machine import Machine
from accendino.main import AccendinoConfig, TOOLS_MANIFEST

class TestToolsManifest(unittest.TestCase):

    def testManifestAndPrune(self):
        with tempfile.TemporaryDirectory() as d:
            config = AccendinoConfig()
            config.toolsDir = pathlib.PurePath(d)
            tools = pathlib.Path(d)
            for sub in ('emsdk/upstream', 'meson-1.4.0/bin', 'meson-1.2.0/bin', 'qt/linux-desktop-linux_gcc_64/6.12.0/gcc_64',
                        'qt/linux-desktop-linux_gcc_64/6.11.0/gcc_64', 'qt/windows-desktop-win64_mingw/6.12.0'):
                os.makedirs(tools / sub)
            (tools / 'stray.txt').write_text('x')

            config.registerTool('meson-1.4.0', '1.4.0')
            config.registerTool('emsdk', '6.0.11')
            config.registerTool('qt/linux-desktop-linux_gcc_64/6.12.0', '6.12.0 linux_gcc_64 qtwebsockets')
            self.assertEqual((tools / TOOLS_MANIFEST).read_text(), 'emsdk 6.0.11\nmeson-1.4.0 1.4.0\n'
                             'qt/linux-desktop-linux_gcc_64/6.12.0 6.12.0 linux_gcc_64 qtwebsockets\n')

            config.pruneToolsDir()
            remaining = sorted(str(p.relative_to(tools)) for p in tools.rglob('*') if p.is_dir() or p.is_file())
            self.assertEqual(remaining, [TOOLS_MANIFEST, 'emsdk', 'emsdk/upstream', 'meson-1.4.0', 'meson-1.4.0/bin', 'qt',
                                         'qt/linux-desktop-linux_gcc_64', 'qt/linux-desktop-linux_gcc_64/6.12.0',
                                         'qt/linux-desktop-linux_gcc_64/6.12.0/gcc_64'])


class TestCcache(unittest.TestCase):

    def _config(self, ccache=True):
        config = AccendinoConfig()
        config.ccache = ccache
        config.ccacheEnv = {'CCACHE_DIR': '/w/ccache', 'CCACHE_BASEDIR': '/w'}
        return config

    def _artifact(self, cls, targetDistrib='Ubuntu', arch='x86_64'):
        item = cls('item', [], None)
        item.machine = Machine('Ubuntu', '24.04', targetDistrib, arch, 'x86_64')
        return item

    def testDisabled(self):
        item = self._artifact(MesonBuildArtifact)
        self.assertEqual(item._ccacheEnv(self._config(False), {'CC': 'gcc'}), {})

    def testCompilerPrefix(self):
        env = self._artifact(MesonBuildArtifact)._ccacheEnv(self._config(), {'CC': 'gcc', 'CXX': 'ccache g++'})
        self.assertEqual(env, {'CCACHE_DIR': '/w/ccache', 'CCACHE_BASEDIR': '/w', 'CC': 'ccache gcc'})

    def testLauncher(self):
        # cmake has CMAKE_<LANG>_COMPILER_LAUNCHER, CC is left as is
        env = self._artifact(CMakeBuildArtifact)._ccacheEnv(self._config(), {'CC': 'gcc'})
        self.assertNotIn('CC', env)
        self.assertEqual(env['CCACHE_DIR'], '/w/ccache')

    def testEmscripten(self):
        env = self._artifact(MesonBuildArtifact, 'emscripten', 'wasm32')._ccacheEnv(self._config(), {'CC': 'emcc'})
        self.assertEqual(env['EM_COMPILER_WRAPPER'], 'ccache')
        self.assertNotIn('CC', env)

    def testNoCcache(self):
        self.assertEqual(self._artifact(QMakeBuildArtifact)._ccacheEnv(self._config(), {'CC': 'gcc'}), {})

if __name__ == '__main__':
    unittest.main()
