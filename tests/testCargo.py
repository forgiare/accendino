import unittest
from unittest import mock
from accendino.builditems import BuildArtifact, CargoBuildArtifact, rustTriple
from accendino.machine import Machine
from accendino.toolchain import MingwToolChain
from accendino.main import AccendinoConfig


class TestCargo(unittest.TestCase):

    def testRustTriple(self):
        self.assertEqual(rustTriple('Ubuntu', 'x86_64'), 'x86_64-unknown-linux-gnu')
        self.assertEqual(rustTriple('Fedora', 'arm64'), 'aarch64-unknown-linux-gnu')
        self.assertEqual(rustTriple('mingw', 'i686'), 'i686-pc-windows-gnu')
        self.assertEqual(rustTriple('Windows', 'x86_64'), 'x86_64-pc-windows-msvc')
        self.assertEqual(rustTriple('Windows', 'x86_64', 'mingw'), 'x86_64-pc-windows-gnu')
        self.assertEqual(rustTriple('Darwin', 'arm64'), 'aarch64-apple-darwin')
        self.assertEqual(rustTriple('emscripten', 'wasm32'), 'wasm32-unknown-emscripten')

    def testPackages(self):
        item = CargoBuildArtifact('item', [], None, capi=True)
        self.assertIn('cargo-c', item.pkgs['Ubuntu'])
        self.assertIn('rustc', item.pkgs['Debian'])
        self.assertIn('rust-std-static-x86_64-pc-windows-gnu', item.pkgs['Fedora->mingw@x86_64'])

        self.assertEqual(CargoBuildArtifact('item', [], None, rustVersion='1.85.0').pkgs, {})

    def _crossCommands(self, **kwargs):
        config = AccendinoConfig()
        config.distribId = 'Fedora'
        item = CargoBuildArtifact('item', [], None, **kwargs)
        item.machine = Machine('Fedora', '42', 'mingw', 'x86_64', 'x86_64')
        item.machine.toolchainObj = MingwToolChain(config, item.machine)
        item.buildType = 'release'

        captured = {}
        def fakePrepare(self, _config):
            captured.update(prepare=self.prepare_cmds, build=self.build_cmds, env=self.extraEnv)
            return True

        with mock.patch.object(BuildArtifact, 'prepare', fakePrepare):
            item.prepare(config)
        return captured

    def testCrossCommands(self):
        c = self._crossCommands(features=['a', 'b'], locked=True, extraEnv={'FOO': 'bar'})
        self.assertEqual(c['prepare'][0][0], ['cargo', 'fetch', '--manifest-path', '{srcdir}/Cargo.toml', '--target',
                                             'x86_64-pc-windows-gnu', '--locked'])
        build = c['build'][0][0]
        self.assertEqual(build[:2], ['cargo', 'install'])
        self.assertIn('--features', build)
        self.assertEqual(build[build.index('--target') + 1], 'x86_64-pc-windows-gnu')
        self.assertEqual(build[build.index('--profile') + 1], 'release')
        self.assertEqual(c['env']['PKG_CONFIG_ALLOW_CROSS'], '1')
        self.assertEqual(c['env']['FOO'], 'bar')

        c = self._crossCommands(capi=True)
        self.assertEqual(c['build'][0][0][:2], ['cargo', 'cinstall'])


if __name__ == '__main__':
    unittest.main()
