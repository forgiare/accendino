import unittest
from accendino.toolchain import computeEnvDiff


class Test(unittest.TestCase):

    def testEqualInValues(self):
        content = [
            'Path=C:\\Windows',
            'c28fc6f98a2c44abbbd89d6a3037d0d9_POSIX_FD_STATE=AAAAAAICAgA=',
            'OPTS=a=b=c',
            '========',
            '**********************************************************************',
            '** Visual Studio 2022 Developer Command Prompt v17.14.14',
            '**********************************************************************',
            '[vcvarsall.bat] Environment initialized for: \'x64\'',
            'PATH=C:\\VS;C:\\Windows',
            'c28fc6f98a2c44abbbd89d6a3037d0d9_POSIX_FD_STATE=AAAAAAICAgA=',
            'OPTS=a=b=c',
            'INCLUDE=C:\\VS\\include',
        ]
        self.assertEqual(computeEnvDiff(content), {'PATH': 'C:\\VS;C:\\Windows', 'INCLUDE': 'C:\\VS\\include'})


if __name__ == '__main__':
    unittest.main()
