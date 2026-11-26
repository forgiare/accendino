import os
import tempfile
import unittest
from accendino.sources import LocalSource


class Test(unittest.TestCase):

    def testRelinkWhenSrcdirChanges(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, 'old')
            new = os.path.join(d, 'new')
            target = os.path.join(d, 'target')
            os.makedirs(old)
            os.makedirs(new)

            src = LocalSource(old, True)
            self.assertTrue(src.checkout(target, None))
            self.assertTrue(src.refreshed)
            self.assertFalse(src.replaced)

            # same srcdir: nothing to do
            self.assertTrue(src.checkout(target, None))
            self.assertFalse(src.refreshed)
            self.assertFalse(src.replaced)

            # another srcdir: the link is replaced and a rebuild is asked
            src = LocalSource(new, True)
            self.assertTrue(src.checkout(target, None))
            self.assertTrue(src.replaced)
            self.assertEqual(os.path.realpath(target), os.path.realpath(new))

    def testRelinkDanglingLink(self):
        with tempfile.TemporaryDirectory() as d:
            new = os.path.join(d, 'new')
            target = os.path.join(d, 'target')
            os.makedirs(new)
            os.symlink(os.path.join(d, 'gone'), target)

            src = LocalSource(new, True)
            self.assertTrue(src.checkout(target, None))
            self.assertTrue(src.replaced)
            self.assertEqual(os.path.realpath(target), os.path.realpath(new))


if __name__ == '__main__':
    unittest.main()
