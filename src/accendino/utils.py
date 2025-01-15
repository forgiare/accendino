from packaging.version import Version
import typing as T

from zenlog import log as logging

def checkAccendinoVersion(cond: str, v: str) -> bool:
    ''' '''
    tokens = cond.split(' ', 2)
    if len(tokens) != 2:
        logging.error(f"invalid condition string {cond}")
        return False

    op = tokens[0]
    checkVersion = tokens[1]

    if op in ('=', '==',):
        return checkVersion == v

    if op in ('!', '!=',):
        return checkVersion != v

    if op == '<':
        return Version(v) < Version(checkVersion)

    if op == '<=':
        return Version(v) <= Version(checkVersion)

    if op == '>':
        return Version(v) > Version(checkVersion)

    if op == '>=':
        return Version(v) >= Version(checkVersion)

    logging.error(f"operation {op} not supported")
    return False


def checkVersionCondition(cond: str, distribId: str, distribVersion: str) -> bool:
    ''' '''
    tokens = cond.split(' ', 3)
    if len(tokens) < 2:
        logging.error(f"invalid condition string {cond}")
        return False

    op = tokens[0]
    os = tokens[1]

    if op in ('=', '==',):
        if distribId != os:
            return False

        if len(tokens) < 3:
            return True
        return distribVersion == tokens[2]

    if op in ('!', '!=',):
        if distribId == os:
            return False

        if len(tokens) < 3:
            return True
        return distribVersion != tokens[2]

    # do version comparisons from here
    if distribId != os:
        return False

    if len(tokens) < 3:
        logging.error(f"invalid condition string {cond}")
        return False

    version = tokens[2]
    if op == '<':
        return distribVersion < version

    if op == '<=':
        return distribVersion <= version

    if op == '>':
        return distribVersion > version

    if op == '>=':
        return distribVersion >= version

    logging.error(f"operation {op} not supported")
    return False

class ConditionalDep:
    ''' '''
    def __init__(self, cond) -> None:
        ''' '''
        self.conditions = cond.strip().split('|')

    def apply(self, _config, deps: T.List[str]) -> T.List[str]:
        ''' '''
        return deps

    def condVerified(self, config) -> bool:
        for cond in self.conditions:
            if checkVersionCondition(cond, config.distribId, config.distribVersion):
                return True
        return False

class DepsAdjuster(ConditionalDep):
    ''' '''

    def __init__(self, cond, add=[], drop=[]) -> None:
        ''' '''
        ConditionalDep.__init__(self, cond)
        self.addItems = add
        self.dropItems = drop

    def apply(self, config, deps: T.List[str]) -> T.List[str]:
        ''' '''
        if not self.condVerified(config):
            return deps

        ret = deps[:]
        ret += self.addItems
        for i in self.dropItems:
            ret.remove(i)
        return ret
