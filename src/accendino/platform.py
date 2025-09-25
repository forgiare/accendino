import sys
import os

def findFirstExistingPath(cands):
    for cand in cands:
        if os.path.exists(cand):
            return cand
    return None


class AccendinoPlatform:
    ''' '''
    def __init__(self):
        self.isWindows = sys.platform.startswith("win")
        if self.isWindows:
            self.msys2path = findFirstExistingPath(['c://tools/msys64/msys2_shell.cmd', 'c://msys64/msys2_shell.cmd'])
        else:
            self.msys2path = None

accendinoPlatform = AccendinoPlatform()
