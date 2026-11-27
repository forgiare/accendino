import os
import pathlib
import tempfile
import unittest
from accendino.builditems import MesonBuildArtifact


def makeArtifact(buildDir):
    # only what beforePrepare() uses
    ret = MesonBuildArtifact.__new__(MesonBuildArtifact)
    ret.buildDir = pathlib.Path(buildDir)
    ret.mesonPath = 'meson'
    ret.prepare_cmds = [(['meson', 'setup'], '{builddir}', 'running meson configure')]
    return ret


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wt', encoding='utf8') as f:
        f.write('x')


class Test(unittest.TestCase):

    def populate(self, d, configured=True):
        touch(os.path.join(d, 'build.log'))
        touch(os.path.join(d, 'accendino-native.ini'))
        touch(os.path.join(d, 'accendino.prepared'))
        touch(os.path.join(d, 'meson-private', 'coredata.dat'))
        touch(os.path.join(d, 'meson-info', 'meson-info.json'))
        touch(os.path.join(d, 'src', 'foo.obj'))
        if configured:
            touch(os.path.join(d, 'meson-private', 'build.dat'))

    def testSettingsChanged(self):
        with tempfile.TemporaryDirectory() as d:
            self.populate(d)
            a = makeArtifact(d)
            a.beforePrepare(None, True)
            self.assertEqual(sorted(os.listdir(d)), ['accendino-native.ini', 'build.log'])
            self.assertEqual(len(a.prepare_cmds), 1)

    def testFailedConfigure(self):
        with tempfile.TemporaryDirectory() as d:
            self.populate(d, configured=False)
            a = makeArtifact(d)
            a.beforePrepare(None, False)
            self.assertEqual(sorted(os.listdir(d)), ['accendino-native.ini', 'build.log'])

    def testDepsUpdated(self):
        # same settings (a dependency was rebuilt): keep the build directory and clear the meson cache
        with tempfile.TemporaryDirectory() as d:
            self.populate(d)
            a = makeArtifact(d)
            a.beforePrepare(None, False)
            self.assertTrue(os.path.exists(os.path.join(d, 'src', 'foo.obj')))
            self.assertEqual(a.prepare_cmds[0][0], ['meson', 'configure', '--clearcache'])

    def testNewBuildDir(self):
        with tempfile.TemporaryDirectory() as d:
            a = makeArtifact(d)
            a.beforePrepare(None, True)
            self.assertEqual(len(a.prepare_cmds), 1)


if __name__ == '__main__':
    unittest.main()
