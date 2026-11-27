import unittest
from accendino.builditems import BuildStepDump


def makeDump(env):
    ret = BuildStepDump()
    ret.gitCommit = 'abc'
    ret.env = env
    ret.args = []
    return ret


class Test(unittest.TestCase):

    def testVolatileVariablesIgnored(self):
        a = makeDump({'PATH': 'C:\\bin', 'SSH_CONNECTION': '1 2 3 4',
                      'c28fc6f98a2c44abbbd89d6a3037d0d9_POSIX_FD_STATE': 'AAAAAAICAgA='})
        b = makeDump({'PATH': 'C:\\bin', 'SSH_CONNECTION': '5 6 7 8',
                      'C28FC6F98A2C44ABBBD89D6A3037D0D9_POSIX_FD_STATE': 'AAAAAAACAgA='})
        self.assertEqual(a, b)

    def testPowershellExecutionPolicy(self):
        a = makeDump({'PATH': 'C:\\bin'})
        b = makeDump({'PATH': 'C:\\bin', 'PSExecutionPolicyPreference': 'Bypass'})
        self.assertEqual(a, b)

    def testOtherVariablesChecked(self):
        a = makeDump({'PATH': 'C:\\bin'})
        b = makeDump({'PATH': 'C:\\other'})
        self.assertNotEqual(a, b)


if __name__ == '__main__':
    unittest.main()
