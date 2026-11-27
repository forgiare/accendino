import os
import unittest
from accendino.main import splitSearchPath


class Test(unittest.TestCase):

    def testWindows(self):
        # the drive letters must not be split
        self.assertEqual(splitSearchPath('C:\\recipes;D:\\other\\recipes', ';'), ['C:\\recipes', 'D:\\other\\recipes'])

    def testPosix(self):
        self.assertEqual(splitSearchPath('/a/recipes:/b', ':'), ['/a/recipes', '/b'])

    def testEmptyEntries(self):
        self.assertEqual(splitSearchPath('', ':'), [])
        self.assertEqual(splitSearchPath(':/a::/b:', ':'), ['/a', '/b'])

    def testPlatformSeparator(self):
        self.assertEqual(splitSearchPath(f'x{os.pathsep}y'), ['x', 'y'])
