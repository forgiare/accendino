import os
import pathlib
import tempfile
import time
import unittest
from accendino.builditems import BuildArtifact


def makeArtifact(name, buildDir, deps=None):
    # only what needsRebuildFromDepsUpdates() uses
    ret = BuildArtifact.__new__(BuildArtifact)
    ret.name = name
    ret.deps = deps or []
    ret.builtFile = pathlib.Path(buildDir) / 'accendino.built'
    ret.prepareStateFile = pathlib.Path(buildDir) / 'accendino.prepared'
    return ret


class FakeConfig:
    def __init__(self, items):
        self.items = {i.name: i for i in items}

    def getBuildItem(self, name):
        return self.items.get(name)


def touch(path, mtime):
    with open(path, 'wt', encoding='utf8') as f:
        f.write('x')
    os.utime(path, (mtime, mtime))


class Test(unittest.TestCase):

    def testDepRebuiltAfterFailedBuild(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'dep'))
            os.makedirs(os.path.join(d, 'item'))
            dep = makeArtifact('dep', os.path.join(d, 'dep'))
            item = makeArtifact('item', os.path.join(d, 'item'), ['dep'])
            config = FakeConfig([dep, item])
            now = time.time()

            # item prepared, then its build failed (no built file), then dep rebuilt
            touch(item.prepareStateFile, now - 100)
            touch(dep.builtFile, now)
            self.assertTrue(item.needsRebuildFromDepsUpdates(config))

            # dep built before the prepare: nothing to do
            touch(dep.builtFile, now - 200)
            self.assertFalse(item.needsRebuildFromDepsUpdates(config))

    def testBuiltFileHasPrecedence(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'dep'))
            os.makedirs(os.path.join(d, 'item'))
            dep = makeArtifact('dep', os.path.join(d, 'dep'))
            item = makeArtifact('item', os.path.join(d, 'item'), ['dep'])
            config = FakeConfig([dep, item])
            now = time.time()

            touch(item.prepareStateFile, now - 300)
            touch(dep.builtFile, now - 200)
            touch(item.builtFile, now - 100)
            self.assertFalse(item.needsRebuildFromDepsUpdates(config))

    def testNeverPrepared(self):
        with tempfile.TemporaryDirectory() as d:
            item = makeArtifact('item', d)
            self.assertFalse(item.needsRebuildFromDepsUpdates(FakeConfig([item])))


if __name__ == '__main__':
    unittest.main()
