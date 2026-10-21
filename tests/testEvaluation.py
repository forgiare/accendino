import os
import tempfile
import unittest
import configparser
from accendino.main import AccendinoConfig

ACCENDINO_FILE = '''
ARTIFACTS += [
    DepsBuildArtifact('tool', [], provides=['tool-artifact']),
    DepsBuildArtifact('lib', ['tool-artifact']),
    DepsBuildArtifact('app', ['lib'], toolDeps=['tool-artifact']),
    DepsBuildArtifact(f"opt-{getOption('foo.x')}-{getOption('foo.y')}-{buildingTools}-{toolsForDistribId}", []),
]
include(INCLUDED)
include(INCLUDED)
DEFAULT_TARGETS = 'app'
'''

INCLUDED_FILE = '''
ARTIFACTS += [ DepsBuildArtifact('included', []) ]
'''

OPTIONS = '''
[foo]
x=target
y=both
[native:foo]
x=native
'''

class Test(unittest.TestCase):

    def setUp(self):
        self.tmpDir = tempfile.TemporaryDirectory()
        included = os.path.join(self.tmpDir.name, 'included.accendino')
        with open(included, 'wt', encoding='utf8') as f:
            f.write(INCLUDED_FILE)

        self.mainFile = os.path.join(self.tmpDir.name, 'main.accendino')
        with open(self.mainFile, 'wt', encoding='utf8') as f:
            f.write(f'INCLUDED = {included!r}\n' + ACCENDINO_FILE)

    def tearDown(self):
        self.tmpDir.cleanup()

    def _config(self, targetDistrib: str, targetArch: str) -> AccendinoConfig:
        config = AccendinoConfig()
        config.workDir = self.tmpDir.name
        config.targetDistrib = targetDistrib
        config.targetArch = targetArch
        config.localArch = 'x86_64'
        config.options = configparser.ConfigParser()
        config.options.optionxform = str
        config.options.read_string(OPTIONS)
        config.sources = [self.mainFile]

        config.setPlatform('Ubuntu', '24.04')
        self.assertTrue(config.readSource(self.mainFile, True))
        config.finalizeConfig()
        self.assertTrue(config.setupBuildMachine())
        return config

    def _names(self, config):
        return [item.name for item in config.buildDefs]

    def testNative(self):
        config = self._config(None, 'x86_64')
        self.assertIsNone(config.buildMachine)
        self.assertEqual(self._names(config), ['tool', 'lib', 'app', 'opt-target-both-False-None', 'included'])

        # without cross compilation tool dependencies are plain dependencies
        self.assertEqual(config.getBuildItem('app').deps, ['lib', 'tool-artifact'])

    def testCross(self):
        config = self._config('mingw', 'x86_64')
        buildMachine = config.buildMachine
        self.assertIsNotNone(buildMachine)
        self.assertFalse(buildMachine.crossCompilation)
        self.assertEqual(buildMachine.targetDistrib, 'Ubuntu')
        self.assertEqual(buildMachine.prefix, config.buildToolsPrefix)

        self.assertEqual(self._names(config), [
            'tool', 'lib', 'app', 'opt-target-both-False-None', 'included',
            'native:tool', 'native:lib', 'native:app', 'native:opt-native-both-True-mingw', 'native:included',
        ])

        app = config.getBuildItem('app')
        self.assertEqual(app.deps, ['lib', 'native:tool-artifact'])
        self.assertIs(app.machine, config.targetMachine)

        nativeLib = config.getBuildItem('native:lib')
        self.assertEqual(nativeLib.deps, ['native:tool-artifact'])
        self.assertIs(nativeLib.machine, buildMachine)
        self.assertEqual(config.getBuildItem('native:tool-artifact').name, 'native:tool')

        # the build plan builds the tool for the build machine before app
        plan = []
        self.assertTrue(config.createBuildPlan(['app'], plan))
        self.assertEqual([item.name for item in plan], ['tool', 'lib', 'native:tool', 'app'])

    def testCrossWithoutTools(self):
        # no tool dependencies: the files are evaluated only once
        with open(self.mainFile, 'at', encoding='utf8') as f:
            f.write("for a in ARTIFACTS:\n    a.toolDeps = []\n")

        config = self._config('mingw', 'x86_64')
        self.assertIsNone(config.buildMachine)
        self.assertEqual(config.getBuildItem('app').deps, ['lib'])

    def _appendBuildMachineOnly(self):
        # tools-only artifact, no toolDeps anywhere: buildMachineOnly alone needs the build machine
        with open(self.mainFile, 'at', encoding='utf8') as f:
            f.write("for a in ARTIFACTS:\n    a.toolDeps = []\n")
            f.write("ARTIFACTS += [\n"
                    "    DepsBuildArtifact('gen', [], provides=['gen-artifact'], buildMachineOnly=True),\n"
                    "    DepsBuildArtifact('user', ['lib', 'gen-artifact']),\n"
                    "]\n"
                    "DEFAULT_TARGETS = 'gen,user'\n")

    def testBuildMachineOnlyNative(self):
        self._appendBuildMachineOnly()
        config = self._config(None, 'x86_64')
        self.assertIsNone(config.buildMachine)
        self.assertEqual(config.getBuildItem('user').deps, ['lib', 'gen-artifact'])
        self.assertEqual(config.targets, ['gen', 'user'])

    def testBuildMachineOnlyCross(self):
        self._appendBuildMachineOnly()
        config = self._config('mingw', 'x86_64')
        self.assertIsNotNone(config.buildMachine)

        names = self._names(config)
        self.assertNotIn('gen', names)
        self.assertIn('native:gen', names)

        self.assertEqual(config.getBuildItem('user').deps, ['lib', 'native:gen-artifact'])
        self.assertEqual(config.targets, ['native:gen', 'user'])

        plan = []
        self.assertTrue(config.createBuildPlan(config.targets, plan))
        self.assertEqual([item.name for item in plan], ['native:gen', 'tool', 'lib', 'user'])


class TestWayland(unittest.TestCase):
    ''' the wayland pocket recipe: wayland uses its own scanner, from the build machine when cross compiling '''

    def setUp(self):
        self.tmpDir = tempfile.TemporaryDirectory()
        self.mainFile = os.path.join(self.tmpDir.name, 'main.accendino')
        with open(self.mainFile, 'wt', encoding='utf8') as f:
            f.write("include('wayland.accendino')\nDEFAULT_TARGETS = 'wayland'\n")

    def tearDown(self):
        self.tmpDir.cleanup()

    def _config(self, targetDistrib: str) -> AccendinoConfig:
        config = AccendinoConfig()
        config.workDir = self.tmpDir.name
        config.targetDistrib = targetDistrib
        config.targetArch = 'x86_64'
        config.localArch = 'x86_64'
        config.options = configparser.ConfigParser()
        config.options.optionxform = str
        config.options.read_string('[wayland]\nfromSources=True\n')
        config.sources = [self.mainFile]

        config.setPlatform('Ubuntu', '24.04')
        self.assertTrue(config.readSource(self.mainFile, True))
        config.finalizeConfig()
        self.assertTrue(config.setupBuildMachine())
        return config

    def testNative(self):
        config = self._config(None)
        wayland = config.getBuildItem('wayland')
        # the tool dependency on itself is dropped
        self.assertEqual(wayland.deps, [])
        self.assertNotIn('-Dscanner=false', wayland.mesonOpts)

        plan = []
        self.assertTrue(config.createBuildPlan(['wayland'], plan))
        self.assertEqual([item.name for item in plan], ['wayland'])

    def testCross(self):
        config = self._config('mingw')
        wayland = config.getBuildItem('wayland')
        self.assertEqual(wayland.deps, ['native:wayland-artifact'])
        self.assertIn('-Dscanner=false', wayland.mesonOpts)

        # only the scanner for the build machine
        nativeWayland = config.getBuildItem('native:wayland')
        self.assertEqual(nativeWayland.deps, [])
        self.assertIn('-Dlibraries=false', nativeWayland.mesonOpts)

        plan = []
        self.assertTrue(config.createBuildPlan(['wayland'], plan))
        self.assertEqual([item.name for item in plan], ['native:wayland', 'wayland'])
