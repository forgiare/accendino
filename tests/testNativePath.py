
import unittest
from accendino.utils import NativePath

class Test(unittest.TestCase):


    def testNativePath(self):
        p = NativePath('tmp', 'ogon', prefix='--prefix=')
        self.assertEqual(p.prefix, '--prefix=')
        self.assertEqual(str(p), '--prefix=tmp/ogon')


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()