#
#  Copyright (C) 2026 David Fort <contact@hardening-consulting.com>
#
''' Qt from the platform packages or installed with aqtinstall '''
import os
import re
import sys
import subprocess
import typing as T

from zenlog import log as logging
from accendino.builditems import BuildArtifact, DepsBuildArtifact
from accendino.machine import NATIVE_PREFIX
from accendino.utils import mergePkgDeps


AQT_DEFAULT_VERSION = '3.3.0'

# modules of the default aqt installation, they are not given with -m
AQT_BASE_MODULES = ('qtbase', 'qtdeclarative', 'qtsvg', 'qttools', 'qttranslations', 'qtwayland')

# Qt modules (named like Qt repositories) to platform packages, when the name can't be derived
DEBIAN_QT6_PKGS = {
    'qtbase': ['qt6-base-dev', 'qt6-base-dev-tools'],
    'qtbase-private': ['qt6-base-private-dev'],
    'qttools': ['qt6-tools-dev', 'qt6-tools-dev-tools', 'qt6-l10n-tools'],
    'qt5compat': ['qt6-5compat-dev'],
    'qtimageformats': ['qt6-image-formats-plugins'],
    'qttranslations': ['qt6-translations-l10n'],
}
DEBIAN_QT5_PKGS = {
    'qtbase': ['qtbase5-dev', 'qtbase5-dev-tools'],
    'qtbase-private': ['qtbase5-private-dev'],
    'qttools': ['qttools5-dev', 'qttools5-dev-tools'],
    'qtdeclarative': ['qtdeclarative5-dev'],
    'qtmultimedia': ['qtmultimedia5-dev'],
    'qtwayland': ['qtwayland5-dev-tools', 'qtwayland5-private-dev'],
    'qtimageformats': ['qt5-image-formats-plugins'],
    'qtwebengine': ['qtwebengine5-dev'],
    'qtpositioning': ['qtpositioning5-dev'],
    'qttranslations': ['qttranslations5-l10n'],
}


def qtSystemPackages(flavor: int, modules: T.List[str]) -> T.Dict[str, T.List[str]]:
    ''' returns the platform packages of the given Qt modules
        @param flavor: 5 or 6
        @param modules: the modules, named like Qt repositories (qtbase, qttools, qtwebsockets, ...), qtbase-private
                        for the private headers of qtbase
    '''
    debian = []
    redhat = []
    arch = []
    for m in modules:
        short = m[2:] if m.startswith('qt') else m

        if flavor == 6:
            debian += DEBIAN_QT6_PKGS.get(m, [f'qt6-{short}-dev'])
        else:
            debian += DEBIAN_QT5_PKGS.get(m, [f'libqt5{short}5-dev'])

        # Fedora names are regular: qt6-qtbase-devel, qt6-qtbase-private-devel, qt5-qtwebsockets-devel, ...
        redhat.append(f'qt{flavor}-{m}-devel')
        if m != 'qtbase-private':
            arch.append(f'qt{flavor}-{short}')

    return {
        'Ubuntu|Debian': debian,
        'Fedora|Redhat': redhat,
        'Arch': arch,
        'Darwin': ['qt' if flavor == 6 else 'qt@5'],
    }


def QtInstaller(name: str, deps=[], flavor: int = 6, version: str = 'latest', modules=[], provides=[],
                pkgs={}, aqtArch: T.Optional[str] = None, aqtVersion: str = AQT_DEFAULT_VERSION):
    ''' returns an artifact providing Qt

        @param name: name of the artifact
        @param deps: list of dependencies to other build artifacts
        @param flavor: the Qt major version, 5 or 6
        @param version: system to use the platform packages, latest for the latest <flavor>.x.y Qt release, <major>.<minor>
                        for its latest release, or a precise version (6.8.3)
        @param modules: the needed Qt modules, named like Qt repositories (qtwebsockets, qtmultimedia, ...). qtbase is
                        always there, with aqt qtdeclarative, qtsvg, qttools, qttranslations and qtwayland come with it
        @param provides: list of provided build artifacts
        @param pkgs: extra platform packages
        @param aqtArch: the aqt architecture to install (linux_gcc_64, win64_msvc2022_64, ...), guessed by default
        @param aqtVersion: the version of aqtinstall to use
    '''
    if flavor not in (5, 6):
        raise ValueError(f'Qt flavor must be 5 or 6, not {flavor}')


    if version == 'system':
        allModules = ['qtbase'] + [m for m in modules if m != 'qtbase']
        return DepsBuildArtifact(name, deps, provides, mergePkgDeps(qtSystemPackages(flavor, allModules), pkgs),
                                 toolchainArtifacts=[])

    return AqtQtArtifact(name, deps, flavor, version, modules, provides, pkgs, aqtArch, aqtVersion)


class AqtQtArtifact(BuildArtifact):
    ''' Qt installed with aqtinstall in the tools directory. Artifacts depending on it get Qt in CMAKE_PREFIX_PATH,
        PKG_CONFIG_LIBDIR and PATH, and QT_HOST_PATH when cross compiling with Qt 6.
    '''

    def __init__(self, name: str, deps, flavor: int, version: str, modules: T.List[str], provides: T.List[str], pkgs,
                 aqtArch: T.Optional[str], aqtVersion: str) -> None:
        # aqt runs in a venv, and the CMake files of Qt6Gui look for OpenGL and xkbcommon
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['python3-venv', 'libgl-dev', 'libegl-dev', 'libxkbcommon-dev', 'libfontconfig1-dev'],
            'Fedora|Redhat': ['mesa-libGL-devel', 'mesa-libEGL-devel', 'libxkbcommon-devel', 'fontconfig-devel'],
        })

        # Qt 6 cross builds need the Qt of the build machine for its tools (moc, rcc, ...)
        toolDeps = [name] if flavor == 6 else []
        BuildArtifact.__init__(self, name, deps, None, provides=provides, pkgs=pkgs, toolchainArtifacts=[],
                               toolDeps=toolDeps)
        self.flavor = flavor
        self.version = version
        self.modules = [m for m in modules if m not in AQT_BASE_MODULES]
        self.aqtArch = aqtArch
        self.aqtVersion = aqtVersion
        self.aqtPath = None
        self.resolvedVersion = None
        self.host = None
        self.target = None
        self.outputDir = None

    def _aqtHostAndTarget(self) -> T.Tuple[T.Optional[str], T.Optional[str]]:
        ''' returns the aqt host and target for the machine of this artifact '''
        m = self.machine
        if m.targetDistrib in ('mingw', 'Windows'):
            return ('windows', 'desktop')
        if m.targetDistrib == 'Darwin':
            return ('mac', 'desktop')
        if m.targetDistrib in ('emscripten',) or m.crossCompilation:
            return (None, None)
        return ('linux_arm64' if m.arch == 'arm64' else 'linux', 'desktop')

    def _archPreferences(self) -> T.List[str]:
        ''' returns regexps of the aqt architectures matching the machine and the toolchain, by preference '''
        m = self.machine
        if m.targetDistrib == 'mingw':
            return [r'win64_mingw$', r'win64_mingw\d+$'] if m.arch == 'x86_64' else [r'win32_mingw\d*$']
        if m.targetDistrib == 'Windows':
            return [r'win64_msvc\d+_arm64$'] if m.arch == 'arm64' else [r'win64_msvc\d+_64$']
        if m.targetDistrib == 'Darwin':
            return [r'clang_64$']
        return [r'linux_gcc_arm64$'] if m.arch == 'arm64' else [r'linux_gcc_64$', r'gcc_64$']

    @staticmethod
    def _defaultArch(pattern: str) -> str:
        ''' a guess of the architecture from a preference regexp, when aqt can't list them '''
        return pattern.replace(r'\d+', '2022' if 'msvc' in pattern else '').replace(r'\d*', '').rstrip('$')

    def _runAqt(self, args: T.List[str]) -> T.Optional[str]:
        ''' runs aqt and returns its output, None if it failed '''
        with open(self.logFile, "at", encoding='utf8') as flog:
            flog.write(f'running {self.aqtPath} {" ".join(args)}\n')
            p = subprocess.run([str(self.aqtPath)] + args, stdout=subprocess.PIPE, stderr=flog, text=True, check=False)
            flog.write(p.stdout)
        return p.stdout.strip() if p.returncode == 0 else None

    def _pickArch(self) -> str:
        ''' returns the aqt architecture to install for the machine of this artifact '''
        listed = self._runAqt(['list-qt', self.host, self.target, '--arch', self.resolvedVersion])
        archs = listed.split() if listed else []
        prefs = self._archPreferences()
        for pattern in prefs:
            candidates = sorted([a for a in archs if re.match(pattern, a)], reverse=True)
            if candidates:
                return candidates[0]

        ret = self._defaultArch(prefs[0])
        logging.warning(f'{self.name}: no aqt architecture found for Qt {self.resolvedVersion} on {self.host}, trying {ret}')
        return ret

    def init(self, config) -> bool:
        if not BuildArtifact.init(self, config):
            return False

        (self.host, self.target) = self._aqtHostAndTarget()
        if not self.host:
            logging.error(f'{self.name}: no Qt from aqtinstall for {self.machine.targetDistrib}@{self.machine.arch}, '
                          'build it from sources')
            return False

        venvDir = config.toolsDir / f'aqtinstall-{self.aqtVersion}'
        binDir = venvDir / ('Scripts' if sys.platform == 'win32' else 'bin')
        self.aqtPath = binDir / ('aqt.exe' if sys.platform == 'win32' else 'aqt')
        if os.path.exists(self.aqtPath):
            return True

        cmds = [
            ([sys.executable, '-m', 'venv', venvDir], '.', 'creating venv for aqtinstall'),
            ([binDir / 'pip', 'install', f'aqtinstall=={self.aqtVersion}'], '.', f'installing aqtinstall {self.aqtVersion}'),
        ]
        return self.runCommands(cmds, os.environ.copy(), config)

    def checkout(self, config) -> bool:
        ''' resolves the Qt version and the architecture to install. They are resolved with aqt once and kept
            in the build directory until --refreshSources (that looks for a newer latest or <major>.<minor> version)
        '''
        cacheFile = self.buildDir / 'qt-version'
        precise = re.fullmatch(r'\d+\.\d+\.\d+', self.version) is not None
        (cachedVersion, cachedArch) = (None, None)
        if os.path.exists(cacheFile):
            with open(cacheFile, 'rt', encoding='utf8') as f:
                (cachedVersion, cachedArch) = (f.read().split() + [None, None])[:2]
        if precise and cachedVersion != self.version:
            (cachedVersion, cachedArch) = (None, None)

        if precise:
            self.resolvedVersion = self.version
        elif cachedVersion and not config.refreshSources:
            self.resolvedVersion = cachedVersion
        else:
            spec = str(self.flavor) if self.version == 'latest' else self.version
            self.resolvedVersion = self._runAqt(['list-qt', self.host, self.target, '--spec', spec, '--latest-version'])
            if not self.resolvedVersion:
                if not cachedVersion:
                    logging.error(f'{self.name}: unable to find the latest Qt {spec} version, check {self.logFile}')
                    return False
                logging.warning(f'{self.name}: unable to find the latest Qt {spec} version, keeping {cachedVersion}')
                self.resolvedVersion = cachedVersion

        if not self.aqtArch:
            if cachedArch and self.resolvedVersion == cachedVersion:
                self.aqtArch = cachedArch
            else:
                self.aqtArch = self._pickArch()

        with open(cacheFile, 'wt', encoding='utf8') as f:
            f.write(f'{self.resolvedVersion} {self.aqtArch}\n')

        self.outputDir = config.toolsDir / 'qt' / f'{self.host}-{self.target}-{self.aqtArch}'
        installCmd = ['{aqt}', 'install-qt', self.host, self.target, self.resolvedVersion, self.aqtArch,
                      '--outputdir', str(self.outputDir)]
        if self.modules:
            installCmd += ['-m'] + self.modules

        # aqt is run by build(), the prepare state holds the install command so that a version, architecture or
        # modules change reinstalls Qt
        self.prepare_cmds = []
        self.prepareDumpCmds = [(installCmd, '.', 'installing Qt')]
        self.build_cmds = [([str(self.aqtPath)] + installCmd[1:], '{builddir}', f'installing Qt {self.resolvedVersion}')]
        return True

    def qtDir(self) -> T.Optional[str]:
        ''' returns the installation directory of Qt (<outputdir>/<version>/<arch dir>), None if it's not installed '''
        if not self.outputDir or not self.resolvedVersion:
            return None

        versionDir = self.outputDir / self.resolvedVersion
        if not os.path.isdir(versionDir):
            return None
        for d in sorted(os.listdir(versionDir)):
            if os.path.isdir(versionDir / d / 'bin'):
                return (versionDir / d).as_posix()
        return None

    def exportedEnv(self, config) -> T.Dict[str, str]:
        qtDir = self.qtDir()
        if not qtDir:
            return {}

        ret = {
            'CMAKE_PREFIX_PATH': qtDir,
            'PKG_CONFIG_LIBDIR': f'{qtDir}/lib/pkgconfig',
        }

        if not self.machine.crossCompilation:
            ret['PATH'] = os.path.join(qtDir, 'bin')
            return ret

        hostQt = config.getBuildItem(NATIVE_PREFIX + self.name)
        hostDir = hostQt.qtDir() if isinstance(hostQt, AqtQtArtifact) else None
        if hostDir:
            ret['QT_HOST_PATH'] = hostDir
            ret['PATH'] = os.path.join(hostDir, 'bin')
        return ret
