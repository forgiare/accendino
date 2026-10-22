import unittest
from accendino.builditems import DepsBuildArtifact
from accendino.machine import Machine
from accendino.qtinstaller import QtInstaller, AqtQtArtifact, qtSystemPackages


class Test(unittest.TestCase):

    def testSystemPackages(self):
        pkgs = qtSystemPackages(6, ['qtbase', 'qtbase-private', 'qtwebsockets', 'qt5compat'])
        self.assertEqual(pkgs['Ubuntu|Debian'], ['qt6-base-dev', 'qt6-base-dev-tools', 'qt6-base-private-dev', 'qt6-websockets-dev',
                                                 'qt6-5compat-dev'])
        self.assertEqual(pkgs['Fedora|Redhat'], ['qt6-qtbase-devel', 'qt6-qtbase-private-devel', 'qt6-qtwebsockets-devel',
                                                 'qt6-qt5compat-devel'])
        self.assertEqual(pkgs['Arch'], ['qt6-base', 'qt6-websockets', 'qt6-5compat'])
        self.assertEqual(pkgs['Darwin'], ['qt'])

        pkgs = qtSystemPackages(5, ['qtbase', 'qtwebsockets', 'qttools'])
        self.assertEqual(pkgs['Ubuntu|Debian'], ['qtbase5-dev', 'qtbase5-dev-tools', 'libqt5websockets5-dev', 'qttools5-dev',
                                                 'qttools5-dev-tools'])
        self.assertEqual(pkgs['Darwin'], ['qt@5'])

    def testFactory(self):
        item = QtInstaller('qt6', version='system', modules=['qtwebsockets'], provides=['qt-artifact'])
        self.assertIs(type(item), DepsBuildArtifact)
        self.assertEqual(item.name, 'qt6')
        self.assertEqual(item.provides, ['qt-artifact'])

        item = QtInstaller('qt5', flavor=5, version='5.15.2', modules=['qtwebsockets', 'qttools'])
        self.assertIsInstance(item, AqtQtArtifact)
        self.assertEqual(item.provides, [])
        # qttools comes with the base installation, Qt 5 has no tools for the build machine
        self.assertEqual(item.modules, ['qtwebsockets'])
        self.assertEqual(item.toolDeps, [])

        # Qt 6 uses the Qt of the build machine when cross compiling
        self.assertEqual(QtInstaller('lastQt6').toolDeps, ['lastQt6'])
        with self.assertRaises(ValueError):
            QtInstaller('qt4', flavor=4)

    def testArchs(self):
        item = QtInstaller('qt6')
        cases = (
            (Machine('Ubuntu', '24.04', 'Ubuntu', 'x86_64', 'x86_64'), ('linux', 'desktop'), 'linux_gcc_64'),
            (Machine('Ubuntu', '24.04', 'Ubuntu', 'arm64', 'arm64'), ('linux_arm64', 'desktop'), 'linux_gcc_arm64'),
            (Machine('Ubuntu', '24.04', 'mingw', 'x86_64', 'x86_64'), ('windows', 'desktop'), 'win64_mingw'),
            (Machine('Windows', '10', 'Windows', 'x86_64', 'x86_64'), ('windows', 'desktop'), 'win64_msvc2022_64'),
            (Machine('Darwin', '15.0', 'Darwin', 'x86_64', 'arm64'), ('mac', 'desktop'), 'clang_64'),
            (Machine('Ubuntu', '24.04', 'emscripten', 'wasm32', 'x86_64'), (None, None), None),
        )
        for machine, hostTarget, defaultArch in cases:
            item.machine = machine
            self.assertEqual(item._aqtHostAndTarget(), hostTarget)
            if defaultArch:
                self.assertEqual(item._defaultArch(item._archPreferences()[0]), defaultArch)


if __name__ == '__main__':
    unittest.main()
