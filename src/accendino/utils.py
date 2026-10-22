import os
import pathlib
import typing as T
from packaging.version import Version

from zenlog import log as logging
from accendino.platform import accendinoPlatform

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
    operSys = tokens[1]

    if len(tokens) > 2:
        pos = tokens[2].find('.')
        if pos == -1:
            # no minor number to compare, that's the case with cond='>= Ubuntu 24', so let's truncate
            # distribVersion

            pos = distribVersion.find('.')
            if pos != -1:
                distribVersion = distribVersion[0:pos]


    if op in ('=', '==',):
        if distribId != operSys:
            return False

        if len(tokens) < 3:
            return True
        return distribVersion == tokens[2]

    if op in ('!', '!=',):
        if distribId == operSys:
            return False

        if len(tokens) < 3:
            return True
        return distribVersion != tokens[2]

    # do version comparisons from here
    if distribId != operSys:
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


CROSS_TARGETS = (('mingw', 'x86_64'), ('mingw', 'i686'), ('emscripten', 'wasm32'))

def doCrossDeps(distribs: T.List[str], deps: T.List[T.Any], target: T.Dict[str, T.Any]):
    ''' adds deps to the package requirements of all the cross targets (mingw, emscripten) of the given
        host distribs '''
    for d in distribs:
        for targetDistrib, arch in CROSS_TARGETS:
            key = f'{d}->{targetDistrib}@{arch}'
            baseV = target.get(key, [])
            target[key] = baseV + deps[:]

# kept for accendino files that may use the old name
doMingwCrossDeps = doCrossDeps


class NativePath:
    ''' class that represents a native path '''
    def __init__(self, *args, **kwargs):
        self.prefix = kwargs.get('prefix', '')
        self.suffix = kwargs.get('suffix', '')
        self.items = args[:]

    def __str__(self) -> str:
        return self.prefix + str(pathlib.PurePath(*self.items)) + self.suffix

class RunInShell:
    ''' class that represent something to execute in a shell (UNIX shell or msys2) '''
    def __init__(self, args):
        self.items = args[:]

    def expand(self):
        if accendinoPlatform.isWindows:
            cmdItems = []
            for item in self.items:
                cmdItems.append(str(item))

            return [accendinoPlatform.msys2path, '-defterm', '-no-start', '-mingw64', '-here', '-c', ' '.join(cmdItems)]

        return self.items

def findInPATH(name: str) -> str:
    if accendinoPlatform.isWindows:
        if not name.endswith(".exe"):
            name += ".exe"

    for p in os.environ.get('PATH', '').split(os.pathsep):
        fpath = os.path.join(p, name)
        if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
            return fpath
    return None

def escapeForPowershell(s):
    ret = ''
    haveSpace = False

    for c in s:
        if c == '\\':
            c = '\\\\'
        elif c == ' ':
            haveSpace = True

        ret += c

    if haveSpace:
        return  "'" + ret + "'"

    return ret

def as_msys2_path(p) -> str:
    if p.drive:
        l = [ p.drive[:-1].lower() ] + list( p.parts[1:] )
        return '/' + '/'.join(l)

    return p.as_posix()

def is_exact_instance(obj, klass):
    s1 = obj.__class__.__name__
    s2 = klass.__name__
    return s1 == s2

def getArchLibDir(distribId: str, archId: str) -> T.Optional[str]:
    ''' returns the multiarch library sub directory (x86_64-linux-gnu, ...) of Linux distributions, None for others '''
    OS_KEYS = {
        'Ubuntu': '-linux-gnu',
        'Debian': '-linux-gnu',
        'Fedora': '-linux-gnu',
        'Redhat': '-linux-gnu'
    }
    osKey = OS_KEYS.get(distribId, None)
    if not osKey:
        return None

    ARCH_KEYS = {
        'amd64': 'x86_64',
        'x86_64': 'x86_64',
        'i686': 'i386',
        'arm64': 'aarch64',
    }

    archKey = ARCH_KEYS.get(archId, None)
    if not archKey:
        logging.warning(f"arch {archId} not handled yet for library sub directories")
        return None
    return archKey + osKey


def homebrewPrefix() -> T.Optional[str]:
    ''' returns the prefix of Homebrew on macOS (/opt/homebrew on Apple Silicon, /usr/local on Intel), None if
        it's not installed '''
    prefix = os.environ.get('HOMEBREW_PREFIX')
    if prefix:
        return prefix

    for prefix in ('/opt/homebrew', '/usr/local'):
        if os.path.exists(os.path.join(prefix, 'bin', 'brew')):
            return prefix
    return None


def pkgConfigDirs(prefix: T.Optional[str], libdir: str, targetDistrib: str, arch: str, extraPath: T.Optional[str],
                  crossCompilation: bool = False) -> T.List[str]:
    ''' returns the pkg-config search directories for a machine, with the ones of prefix if given, and
        the paths of extraPath (a PKG_CONFIG_PATH like string) at the end
    '''
    ret = []
    if prefix:
        ret += [f'{prefix}/{libdir}/pkgconfig', f'{prefix}/share/pkgconfig']

    archLibDir = getArchLibDir(targetDistrib, arch)
    if archLibDir:
        if prefix:
            ret.append(f'{prefix}/{libdir}/{archLibDir}/pkgconfig')
        ret.append(f'/usr/lib/{archLibDir}/pkgconfig')

    # host .pc files must never satisfy a WebAssembly build, nor a macOS build for the other architecture (Homebrew only
    # has the local one)
    if targetDistrib == 'emscripten' or (targetDistrib == 'Darwin' and crossCompilation):
        return ret

    if targetDistrib == 'Darwin':
        # PKG_CONFIG_LIBDIR replaces the default search path of Homebrew's pkg-config
        brewPrefix = homebrewPrefix()
        if brewPrefix:
            ret += [f'{brewPrefix}/lib/pkgconfig', f'{brewPrefix}/share/pkgconfig']

    ret.append('/usr/share/pkgconfig')
    if extraPath:
        ret += [p for p in extraPath.split(':') if p]

    return ret

def envForDepotTools(env: T.Dict[str, str] = None):
    ''' cleanups PYTHONPATH for gclient, fetch and gn otherwise we have conflicts between
        python versions
    '''
    if env is None:
        env = os.environ.copy()
    else:
        env = env.copy()

    if 'PYTHONPATH' in env:
        del env['PYTHONPATH']

    return env
