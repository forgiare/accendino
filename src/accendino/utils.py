import pathlib
import typing as T
from packaging.version import Version

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


def treatPackageDeps(pkgs: T.Dict[str, T.Any]) -> T.Dict[str, T.Any]:
    ''' expands a package deps map, it treats keys that have the form
        `'k1|k2|k3': V` by splitting and setting V for the k1, k2, k3 keys
        Note that we expect V to be a list and so you can have concatenation by
        doing:
            'k1|k2': V1
            'k1': V2

        You will end up with
            'k1': V1 + V2,
            'k2': V1
    '''
    ret = {}

    for k, v in pkgs.items():
        keys = k.split('|')
        for key in keys:
            baseV = ret.get(key, [])
            ret[key] = baseV + v[:]

    return ret

def mergePkgDeps(d1: T.Dict[str, T.Any], d2: T.Dict[str, T.Any]) -> T.Dict[str, T.Any]:
    ret = d1.copy()
    for k, v in d2.items():
        d1_value = ret.get(k, [])
        ret[k] = d1_value + v

    return ret


def doMingwCrossDeps(distribs: T.List[str], deps: T.List[T.Any], target: T.Dict[str, T.Any]):
    for d in distribs:
        for arch in ('x86_64', 'i686',):
            key = f'{d}->mingw@{arch}'
            baseV = target.get(key, [])
            target[key] = baseV + deps[:]


class NativePath:
    ''' class that represents a native path '''
    def __init__(self, *args, **kwargs):
        self.prefix = kwargs.get('prefix', '')
        self.suffix = kwargs.get('suffix', '')
        self.items = args[:]

    def __str__(self) -> str:
        return self.prefix + str(pathlib.PurePath(*self.items)) + self.suffix
