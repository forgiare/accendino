import unittest
from accendino.main import parseOsRelease


class Test(unittest.TestCase):

    def testRocky(self):
        content = '''NAME="Rocky Linux"
VERSION="9.4 (Blue Onyx)"
ID="rocky"
ID_LIKE="rhel centos fedora"
VERSION_ID="9.4"
PLATFORM_ID="platform:el9"
'''
        self.assertEqual(parseOsRelease(content), ('Redhat', '9.4'))

    def testRhelLike(self):
        content = 'ID=someclone\nID_LIKE="rhel fedora"\nVERSION_ID=8.10\n'
        self.assertEqual(parseOsRelease(content), ('Redhat', '8.10'))

    def testArch(self):
        content = 'NAME="Arch Linux"\nID=arch\nBUILD_ID=rolling\n'
        self.assertEqual(parseOsRelease(content), ('Arch', 'rolling'))

    def testFreeBSD(self):
        content = "NAME=FreeBSD\nVERSION='14.1-RELEASE'\nID=freebsd\nVERSION_ID=14.1\n"
        self.assertEqual(parseOsRelease(content), ('FreeBSD', '14.1'))

    def testUnknown(self):
        self.assertEqual(parseOsRelease('ID=linuxmint\nID_LIKE="ubuntu debian"\nVERSION_ID="21.3"\n'), (None, None))
        self.assertEqual(parseOsRelease(''), (None, None))


if __name__ == '__main__':
    unittest.main()
