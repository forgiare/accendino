
import unittest
from accendino.utils import NativePath, checkVersionCondition

class Test(unittest.TestCase):


    def testNativePath(self):
        p = NativePath('tmp', 'ogon', prefix='--prefix=')
        self.assertEqual(p.prefix, '--prefix=')
        self.assertEqual(str(p), '--prefix=tmp/ogon')


    def testCheckVersionCondition(self):
        self.assertTrue(checkVersionCondition(">= Ubuntu 24", "Ubuntu", "26.04"))
        self.assertTrue(checkVersionCondition("> Ubuntu 24", "Ubuntu", "26.04"))
        self.assertFalse(checkVersionCondition("> Ubuntu 24", "Ubuntu", "24.04"))
        self.assertFalse(checkVersionCondition("> Ubuntu 24", "Ubuntu", "24.10"))
        self.assertFalse(checkVersionCondition("> Ubuntu 24", "Ubuntu", "22.04"))
        self.assertTrue(checkVersionCondition(">= Ubuntu 24", "Ubuntu", "24.04"))
        self.assertTrue(checkVersionCondition("<= Ubuntu 24", "Ubuntu", "24.04"))
        self.assertFalse(checkVersionCondition("<= Ubuntu 24", "Fedora", "42"))

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()