import unittest
from accendino.builditems import CMakeBuildArtifact
from accendino.sources import LocalSource


class Test(unittest.TestCase):

    def testNoTrailingSeparator(self):
        # a trailing backslash would escape the quote powershell puts around a path with spaces
        for d in ('C:\\Program Files\\Python313\\Lib\\site-packages\\accendino\\pocket\\libusb\\',
                  'C:\\Program Files\\Python313\\Lib\\site-packages\\accendino\\pocket\\libusb'):
            a = CMakeBuildArtifact('x', [], LocalSource('/x', False), cmakeProjectDir=d)
            self.assertEqual(a.cmakeProjectDir, 'C:\\Program Files\\Python313\\Lib\\site-packages\\accendino\\pocket\\libusb')

        a = CMakeBuildArtifact('x', [], LocalSource('/x', False), cmakeProjectDir='/p/wrapper/')
        self.assertEqual(a.cmakeProjectDir, '/p/wrapper')
        a = CMakeBuildArtifact('x', [], LocalSource('/x', False))
        self.assertEqual(a.cmakeProjectDir, '{srcdir}')
