#! /usr/bin/env python3
import sys
import getopt
import os.path
import platform
import pathlib
import typing as T
import configparser
from zenlog import log as logging

import accendino

from accendino.builditems import BuildArtifact, AutogenBuildArtifact, CMakeBuildArtifact, DepsBuildArtifact, \
    MesonBuildArtifact, QMakeBuildArtifact, CustomCommandBuildArtifact
from accendino.localdeps import getPkgManager
from accendino.sources import LocalSource, GitSource, RemoteArchiveSource, Source
from accendino.utils import ConditionalDep, DepsAdjuster, checkVersionCondition, checkAccendinoVersion, \
    NativePath, RunInShell, mergePkgDeps, is_exact_instance
from accendino.toolchain import getToolchain, CROSS_FILE_DIR
from accendino.machine import Machine



def doHelp(args, is_error) -> int:
    ''' '''
    print(f"usage: {args[0]} [--help] [--prefix=<prefix>] [--debug] [--targets=<targets>] [--build-type=<type>] <file>")
    print("\t--help: shows this help")
    print("\t--version: prints the version")
    print("\t--debug: show verbose information of building")
    print("\t--prefix=<prefix>: where to install")
    print("\t--targets=<targets>: a list of comma separated targets to build (by default full-ogon-freerdp2)")
    print("\t--build-type=[release|debug]: type of build (defaults to release)")
    print("\t--build-as-debug=<artifacts>: a list of comma separated artifacts to build in debug mode, whatever the build type")
    print("\t--work-dir=<path>: a path to the working directory where sources are checked out and built")
    print("\t--options=<path>: a path to the build options file")
    print("\t--refreshSources: force updating git sources and rebuild artifacts whose sources changed")
    print("\t--refresh: force rebuild of the requested targets, even if they were already built")
    print("\t--targetDistrib=<distrib>: cross compile for mingw32, mingw64 or emscripten")
    print("\t--targetArch=<arch>: the target architecture (i686, x86_64, arm64 (or aarch64) or wasm32)")
    print("\t--toolchain=<name>: the toolchain to use (default, gcc, clang, vs, mingw, emscripten)")
    print("\t--buildToolsPrefix=<prefix>: when cross compiling, where tools for the build machine are installed")
    print("\t--buildToolchain=<name>: when cross compiling, the toolchain building tools for the build machine")
    if is_error:
        return 1

    return 0

def detectPlatform() -> None:
    ''' '''
    distrib_id = None
    distrib_version = None

    plat_system = platform.system()
    if plat_system == 'Linux':
        # try reading LSB file
        try:
            for l in open("/etc/lsb-release", "rt", encoding='utf8').readlines():
                pos = l.find("DISTRIB_ID=")
                if pos == 0:
                    distrib_id = l[len('DISTRIB_ID='):-1]
                    continue

                pos = l.find('DISTRIB_RELEASE=')
                if pos == 0:
                    distrib_version = l[len('DISTRIB_RELEASE='):-1]
                    continue

            return (distrib_id, distrib_version)
        except:
            logging.debug(" * failed to detect platform using /etc/lsb-release (not an error)")

        # Debian based systems
        try:
            content = open("/etc/debian_version", "rt", encoding='utf8').readline()
            distrib_id = "Debian"
            tokens = content.split('.', 2)
            distrib_version = f"{int(tokens[0]):02d}.{int(tokens[1]):02d}"
            return (distrib_id, distrib_version)
        except:
            logging.debug(" * failed reading /etc/debian_version  (not an error)")

        # Fedora based systems
        try:
            content = open("/etc/fedora-release", "rt", encoding='utf8').readline()
            distrib_id = "Fedora"
            tokens = content.split(' ', 4)
            distrib_version = tokens[2]
            return (distrib_id, distrib_version)
        except:
            logging.debug(" * failed reading /etc/fedora-version  (not an error)")

    elif plat_system in ('Linux', 'FreeBSD',):
        # Arch / FreeBSD
        try:
            distrib_id = None
            distrib_ver = None
            for l in open("/etc/os-release", "rt", encoding='utf8').readlines():
                l = l.strip()
                if l.startswith('ID='):
                    distrib_id = l[3:]
                elif l.starstwith('BUILD_ID='):
                    distrib_ver = l[9:]
                elif l.startswith('VERSION_ID="'):
                    distrib_ver = l[len('VERSION_ID="') : -1]

                if distrib_id is not None and distrib_ver is not None:
                    return (distrib_id, distrib_ver)
        except:
            logging.debug(" * failed reading /etc/os-release")

    elif plat_system in ("Windows", "Darwin",):
        distrib_id = plat_system
        if plat_system == "Windows":
            distrib_version = platform.win32_ver()[0]
        else:
            distrib_version = platform.mac_ver()[0]

    return (distrib_id, distrib_version)


BUILD_TYPES = ('release', 'debug',)
ARCHS = ('i686', 'x86_64', 'arm64', 'wasm32')

# prefix of the names of the artifacts built for the build machine when cross compiling
NATIVE_PREFIX = 'native:'


class Evaluation:
    ''' An evaluation of the accendino files: they are run once for the target machine, and when cross compiling
        and tools are needed, a second time for the build machine. Each evaluation has its own exec() namespace.
    '''

    def __init__(self, machine: Machine = None, buildingTools: bool = False, toolsFor: Machine = None) -> None:
        '''
            @param machine: the machine the artifacts of this evaluation are built for
            @param buildingTools: if this evaluation builds tools for the build machine
            @param toolsFor: when building tools, the machine the tools are for
        '''
        self.machine = machine
        self.buildingTools = buildingTools
        self.toolsFor = toolsFor
        self.toolchainName = None
        self.includedFiles = set()
        self.includesStack = []
        self.context = None


ARCHS_MAP = {
    'AMD64': 'x86_64', # Windows
    'amd64': 'x86_64', # FreeBSD
    'aarch64': 'arm64', # Linux
    'ARM64': 'arm64', # Windows
}

class AccendinoConfig:
    ''' Accendino configuration '''

    def __init__(self) -> None:
        ''' '''
        self.debug = False
        self.buildWithPowershell = True
        self.buildType = 'release'
        self.debugArtifacts = set()
        self.projectName = None
        self.workDir = pathlib.PurePath(os.getcwd())
        self.prefix = None
        self.projectDir = None
        self.sourcesDir = None
        self.buildsDir = None
        self.toolsDir = None
        self.targets = None
        self.buildDefs = []
        self.distribId = None
        self.distribVersion = None
        self.checkPackages = True
        self.doBuild = True
        self.libdir = 'lib'
        self.resumeFrom = None
        self.refreshSources = False
        self.refresh = False
        self.maxJobs = 5
        self.toolchain = 'default'
        self.targetMachine: Machine = None

        localMachine = platform.machine()
        self.localArch = ARCHS_MAP.get(localMachine, localMachine)
        self.targetArch = None
        self.targetDistrib = None
        self.pocketDir = pathlib.Path(__file__).parent / 'pocket'
        self.crossFileDir = CROSS_FILE_DIR
        self.optionsFile = None
        self.options = None
        self.buildMachine: Machine = None
        self.buildToolsPrefix = None
        self.buildToolchain = 'default'

        #
        # populate a search path that has:
        #   * first paths provided in ACCENDINO_PATH,
        #   * then in the accendino pocket
        self.pocketSearchPaths = os.environ.get('ACCENDINO_PATH', '').split(':') + [ self.pocketDir ]

        self.sources = []
        self.targetEval = Evaluation()
        self.nativeEval: Evaluation = None
        self.context = self.newContext(self.targetEval)

    def newContext(self, ev: 'Evaluation') -> T.Dict[str, T.Any]:
        ''' creates the exec() namespace of an evaluation of the accendino files '''

        def includeFn(fname: str, include_once: bool = True) -> bool:
            ''' '''
            if not fname.endswith('.accendino'):
                fname = fname + '.accendino'

            logging.debug(f"including file '{fname}'")
            return self.readSource(fname, include_once, ev)

        def findAssetFn(item: str, asset: str) -> str:
            ''' returns the absolute path of the <item>/<asset> file searched like included files, None if not found '''
            fpath = self.findSourceFile(os.path.join(item, asset), ev)
            return os.path.abspath(fpath) if fpath else None


        def pickDeps(name: str) -> T.List[T.Any]:
            ''' '''
            targets = ev.context.get("ARTIFACTS", [])
            for t in targets:
                if t.name == name:
                    return t.deps[:]
            return None

        def pickPkgDeps(name: str, extra = None, override : bool = False) -> T.Dict[str, T.List[str]]:
            ''' '''
            ret = None
            targets = ev.context.get("ARTIFACTS", [])
            for t in targets:
                if t.name == name:
                    ret = t.pkgs.copy()
                    break

            if ret is None:
                logging.error(f'error picking package dependencies of {name}')

            if extra:
                for k, v in extra.items():
                    for subk in k.split('|'):
                        if override:
                            base_v = []
                        else:
                            base_v = ret.get(subk, [])

                        ret[subk] = base_v + v

            return ret

        def checkDistrib(cond: str) -> bool:
            return checkVersionCondition(cond, self.distribId, self.distribVersion)

        def checkAccendinoVersionFn(cond: str) -> bool:
            return checkAccendinoVersion(cond, accendino.__version__)

        def getOption(optName: str, defaultVal=None):
            if self.options is None:
                return defaultVal

            tokens = optName.split('.', 2)
            if len(tokens) == 2:
                (section, name) = tokens
            else:
                section = configparser.DEFAULTSECT
                name = optName

            # when building tools for the build machine, a [native:<section>] section has precedence
            sections = [section]
            if ev.buildingTools:
                sections.insert(0, NATIVE_PREFIX + section)

            for section in sections:
                if section not in self.options.sections() or name not in self.options[section]:
                    continue

                ret = self.options[section][name]
                if ret.lower() in ('true', 'on', 'yes',):
                    return True

                if ret.lower() in ('false', 'off', 'no',):
                    return False

                return ret

            return defaultVal

        def stdGitSourceFromOptions(key: str, url: str, tag: str = 'master') -> Source:
            return GitSource(getOption(f'{key}.url', url), getOption(f'{key}.tag', tag))

        def stdBuildFromSourceTest(key: str, lokals, default_option: bool) -> bool:
            force_key = f'{key}_forceBuild'
            if force_key in lokals and lokals[force_key]:
                return True

            return getOption(f'{key}.fromSources', default_option)

        def abort(msg: str = None) -> None:
            if not msg is None:
                logging.fatal(msg)
            sys.exit(1)

        ev.context = {
            'ARTIFACTS': [],
            'DEFAULT_TARGETS': None,
            'LocalSource': LocalSource,
            'GitSource': GitSource,
            'RemoteArchiveSource': RemoteArchiveSource,
            'DepsBuildArtifact': DepsBuildArtifact,
            'CMakeBuildArtifact': CMakeBuildArtifact,
            'QMakeBuildArtifact': QMakeBuildArtifact,
            'AutogenBuildArtifact': AutogenBuildArtifact,
            'MesonBuildArtifact': MesonBuildArtifact,
            'CustomCommandBuildArtifact': CustomCommandBuildArtifact,
            'BuildArtifact': BuildArtifact,
            'include': includeFn,
            'findAsset': findAssetFn,
            'getOption': getOption,
            'checkDistrib': checkDistrib,
            'pickDeps': pickDeps,
            'pickPkgDeps': pickPkgDeps,
            'mergePkgDeps': mergePkgDeps,
            'logging': logging,
            'DepsAdjuster': DepsAdjuster,
            'NativePath': NativePath,
            'RunInShell': RunInShell,
            'accendinoVersion': accendino.__version__,
            'UBUNTU_LIKE': 'Debian|Ubuntu',
            'REDHAT_LIKE': 'Fedora|Redhat',
            'checkAccendinoVersion': checkAccendinoVersionFn,
            'stdGitSourceFromOptions': stdGitSourceFromOptions,
            'stdBuildFromSourceTest': stdBuildFromSourceTest,
            'abort': abort,
            'buildingTools': ev.buildingTools,
            'toolsForDistribId': ev.toolsFor.targetDistrib if ev.toolsFor else None,
            'toolsForArch': ev.toolsFor.arch if ev.toolsFor else None,
        }
        return ev.context

    def findSourceFile(self, fname: str, ev: 'Evaluation' = None) -> str:
        ''' searches an accendino file (or an asset), returns its path or None if not found '''
        ev = ev or self.targetEval
        searchPaths = ['.', 'pocket'] + self.pocketSearchPaths

        # also search in the directory of the last included file
        if len(ev.includesStack) > 0:
            searchPaths.append( os.path.dirname(ev.includesStack[-1]) )

        # if the requested file is a path then just try to open it
        if fname.startswith('.') or fname.startswith('/'):
            searchPaths = ['']

        for p in searchPaths:
            fpath = os.path.join(p, fname)
            if os.path.exists(fpath) and os.path.isfile(fpath):
                return fpath

        return None

    def cmakeBuildType(self, buildType: str = None) -> str:
        ''' '''
        buildType = buildType or self.buildType
        if buildType == 'release':
            return 'Release'

        if buildType == 'debug':
            return 'Debug'

        raise Exception(f"{buildType} build type not supported for cmake")

    def mesonBuildType(self, buildType: str = None) -> str:
        ''' '''
        buildType = buildType or self.buildType
        if buildType in ['release', 'debug']:
            return buildType
        raise Exception(f"{buildType} build type not supported for meson")

    def getBuildItem(self, name: str) -> BuildArtifact:
        ''' '''
        for item in self.buildDefs:
            if item.name == name or name in item.provides:
                return item
        return None

    @property
    def crossCompilation(self) -> bool:
        return self.targetMachine.crossCompilation if self.targetMachine else False

    @property
    def toolchainObj(self):
        return self.targetMachine.toolchainObj if self.targetMachine else None

    @toolchainObj.setter
    def toolchainObj(self, value) -> None:
        self.targetMachine.toolchainObj = value

    def setPlatform(self, distribId: str, distribVersion: str) -> None:
        self.distribId = distribId
        self.distribVersion = distribVersion
        if not self.targetDistrib:
            self.targetDistrib = distribId

        self.targetMachine = Machine(distribId, distribVersion, self.targetDistrib, self.targetArch, self.localArch)
        self.libdir = self.targetMachine.libdir

        self.targetEval.machine = self.targetMachine
        self.targetEval.toolchainName = self.toolchain
        self.context.update(self._platformKeys(self.targetEval))

    def _platformKeys(self, ev: Evaluation) -> T.Dict[str, T.Any]:
        ''' returns the context keys describing the machine of an evaluation '''
        machine = ev.machine
        return {
            'distribId': machine.distribId,
            'distribVersion': machine.distribVersion,
            'targetArch': machine.arch,
            'targetDistribId': machine.targetDistrib,
            'crossCompilation': machine.crossCompilation,
            'buildType': self.buildType,
            'toolchain': ev.toolchainName,
            'libdir': machine.libdir,
        }

    @property
    def toolsPrefix(self) -> pathlib.PurePath:
        ''' where the tools for the build machine are installed: the build prefix when cross compiling, the
            prefix otherwise '''
        return self.buildToolsPrefix if self.crossCompilation else self.prefix


    @staticmethod
    def checkCrossFiles(buildPlan) -> bool:
        ''' checks that the cmake and meson artifacts of the build plan that are cross compiled have a cross file '''
        checked = {}
        for item in buildPlan:
            builder = 'cmake' if isinstance(item, CMakeBuildArtifact) else 'meson' if isinstance(item, MesonBuildArtifact) else None
            if not builder or not item.machine.crossCompilation:
                continue

            key = (id(item.machine), builder)
            if key not in checked:
                path = item.machine.getCrossPlatformFile(builder)
                checked[key] = bool(path) and os.path.exists(path)
                if not path:
                    logging.error(f'no {builder} cross file to build for {item.machine.targetDistrib}@{item.machine.arch}, '
                                  'use another toolchain or set CROSS_PLATFORM_FILE_CHOOSER')
                elif not checked[key]:
                    logging.error(f'{builder} cross file {path} does not exist')

            if not checked[key]:
                logging.error(f'unable to cross compile {item.name}')
                return False
        return True

    def treatPlatformPackages(self, pkgManager, packagesToCheck, buildItems) -> None:
        ''' '''
        # let's compute platform package requirements, each artifact with the keys of its machine
        machines = [self.targetMachine]
        if self.buildMachine:
            machines.append(self.buildMachine)
        toolchainArtifacts = { id(m): [] for m in machines }

        for item in buildItems:
            if isinstance(item, str):
                continue

            machine = item.machine
            toolchainArtifacts[id(machine)] += item.toolchainArtifacts

            (shortName, longName) = machine.packageKeys()
            if longName in item.pkgs:
                pkgs = item.pkgs[longName]
            elif shortName in item.pkgs:
                pkgs = item.pkgs[shortName]
            else:
                if not machine.crossCompilation:
                    logging.debug(f" * warning, {item.name} has no package dependency for the current platform")
                continue

            packagesToCheck += pkgs[:]

        packagesToCheck = list(set(packagesToCheck))

        if pkgManager:
            for machine in machines:
                if not machine.toolchainObj.packagesCheck(pkgManager, list(set(toolchainArtifacts[id(machine)])), True):
                    logging.error(" * package requirements not met")
                    return 5

            toInstall = pkgManager.checkMissing(packagesToCheck)
            if toInstall is None:
                logging.error(" * package requirements not met")
                return 5

            if toInstall:
                if not pkgManager.installPackages(toInstall):
                    logging.error(" * error during package installation")
                    return 4

        return 0

    def createBuildPlan(self, itemsToBuild, buildPlan) -> bool:
        ''' computes the ordered build plan, returns False if some targets or dependencies can't be resolved '''
        missing = []

        def addBuildItems(items: T.List[str], buildPlan: T.List[str], provided: T.List[str]):
            for item in items:
                if item in buildPlan + provided:
                    continue

                itemObj = self.getBuildItem(item)
                if itemObj:
                    if itemObj.deps:
                        addBuildItems(itemObj.deps, buildPlan, provided)

                    buildPlan.append(itemObj.name)
                    if itemObj.provides:
                        if isinstance(itemObj.provides, list):
                            provided += itemObj.provides
                        else:
                            provided.append(itemObj.provides)

                elif item not in missing:
                    logging.error(f"unable to find build dependency {item}")
                    missing.append(item)

        plan = []
        provided = []
        addBuildItems(itemsToBuild, plan, provided)
        if missing:
            return False

        for itemStr in plan:
            item = self.getBuildItem(itemStr)
            if item:
                buildPlan.append(item)
            else:
                buildPlan.append(itemStr)
        return True

    def readSource(self, fname: str, include_once: bool, ev: 'Evaluation' = None) -> bool:
        ''' reads and executes an accendino file in the namespace of the given evaluation (the target one by default) '''
        ev = ev or self.targetEval
        fpath = self.findSourceFile(fname, ev)
        if fpath is None:
            logging.error(f'file {fname} not found')
            sys.exit(-1)

        realPath = os.path.realpath(fpath)
        if include_once and realPath in ev.includedFiles:
            logging.debug(f"file '{fpath}' already included")
            return True
        ev.includedFiles.add(realPath)

        ev.includesStack.append(fpath)
        with open(fpath, "rt", encoding="utf8") as f:
            code = compile(f.read(), os.path.basename(fpath), "exec")
            exec(code, {}, ev.context)
        ev.includesStack.pop()
        return True

    def _resolveDeps(self, deps: T.List[T.Any]) -> T.List[str]:
        ''' returns the list of artifact dependencies with the conditional ones applied '''
        newDeps = []
        for dep in deps:
            if isinstance(dep, str):
                newDeps.append(dep)
            elif isinstance(dep, ConditionalDep):
                newDeps = dep.apply(self, newDeps)
            else:
                logging.error(f'don\'t know how to treat artifact dependency with type {type(dep)}')
        return newDeps

    def _finalizeArtifacts(self, ev: Evaluation) -> T.List[DepsBuildArtifact]:
        ''' resolves the conditional dependencies of the artifacts of an evaluation and binds them to its machine '''
        ret = []
        for buildItem in ev.context.get('ARTIFACTS', []):
            buildItem.deps = self._resolveDeps(buildItem.deps)
            buildItem.toolDeps = self._resolveDeps(buildItem.toolDeps)

            newPkg = {}
            for k, v in buildItem.pkgs.items():
                newList = []
                for dep in v:
                    if isinstance(dep, str):
                        newList.append(dep)
                    elif isinstance(dep, ConditionalDep):
                        newList = dep.apply(self, newList)
                    else:
                        logging.error(f'don\'t know how to treat package dependency with type {type(dep)}')

                newPkg[k] = newList
            buildItem.pkgs = newPkg
            buildItem.machine = ev.machine
            ret.append(buildItem)

        return ret

    def finalizeConfig(self) -> bool:
        ''' '''
        self.buildDefs += self._finalizeArtifacts(self.targetEval)

        if not self.targets:
            defaultTargets = self.context.get('DEFAULT_TARGETS', 'ogon')
            if defaultTargets:
                self.targets = defaultTargets.split(",")

        if not self.projectName:
            self.projectName = self.context.get('PROJECT', 'work')

        self.projectDir = pathlib.PurePath(self.workDir, self.projectName)
        if not self.prefix:
            self.prefix = self.projectDir / 'deploy'

        self.sourcesDir = self.projectDir / 'sources'
        self.buildsDir = self.projectDir / 'build'
        self.toolsDir = self.projectDir / 'tools'
        if not self.buildToolsPrefix:
            self.buildToolsPrefix = self.projectDir / 'deploy-build'

        self.targetMachine.prefix = self.prefix
        self.targetMachine.crossPlatformFileChooser = self.context.get('CROSS_PLATFORM_FILE_CHOOSER')
        return True

    @staticmethod
    def _mergeToolDeps(item: DepsBuildArtifact) -> T.List[str]:
        ''' returns the dependencies of item with its tool dependencies, without the ones on itself: an artifact can use
            its own tools when it's built for the build machine (wayland and wayland-scanner for instance)
        '''
        provides = item.provides if isinstance(item.provides, list) else [item.provides]
        selfNames = set([item.name] + provides)
        return item.deps + [d for d in item.toolDeps if d not in item.deps and d not in selfNames]

    def setupBuildMachine(self) -> bool:
        ''' resolves the tool dependencies of the artifacts. Without cross compilation they are plain dependencies.
            When cross compiling, the accendino files are evaluated a second time for the build machine, the
            artifacts of that evaluation are named native:<name>, and tool dependencies point to them.
        '''
        targetItems = self.buildDefs[:]

        if not self.crossCompilation:
            for item in targetItems:
                item.deps = self._mergeToolDeps(item)
            return True

        # artifacts that only exist for the build machine are not built for the target, references to them
        # go to their native: version
        buildOnlyNames = set()
        for item in targetItems:
            if item.buildMachineOnly:
                buildOnlyNames.add(item.name)
                buildOnlyNames.update(item.provides if isinstance(item.provides, list) else [item.provides])

        if buildOnlyNames:
            targetItems = [item for item in targetItems if not item.buildMachineOnly]
            self.buildDefs = targetItems[:]
            for item in targetItems:
                item.toolDeps = item.toolDeps + [d for d in item.deps if d in buildOnlyNames and d not in item.toolDeps]
                item.deps = [d for d in item.deps if d not in buildOnlyNames]
            self.targets = [NATIVE_PREFIX + t if t in buildOnlyNames else t for t in self.targets]

        needed = any(item.toolDeps for item in targetItems) or any(t.startswith(NATIVE_PREFIX) for t in self.targets)
        if not needed:
            return True

        machine = Machine(self.distribId, self.distribVersion, self.distribId, self.localArch, self.localArch)
        machine.prefix = self.buildToolsPrefix
        machine.toolchainObj = getToolchain(self.buildToolchain, self, machine)
        if not machine.toolchainObj:
            logging.error(f"unable to find toolchain {self.buildToolchain} for the build machine")
            return False
        self.buildMachine = machine

        logging.debug(f'evaluating accendino files for the build machine ({machine.distribId}@{machine.arch})')
        ev = Evaluation(machine, True, self.targetMachine)
        ev.toolchainName = self.buildToolchain
        self.nativeEval = ev
        self.newContext(ev)
        ev.context.update(self._platformKeys(ev))
        for f in self.sources:
            if not self.readSource(f, True, ev):
                logging.error(f"error interpreting {f} for the build machine")
                return False

        for item in self._finalizeArtifacts(ev):
            # the build machine is not cross compiling, tools are plain dependencies there
            deps = self._mergeToolDeps(item)
            provides = item.provides if isinstance(item.provides, list) else [item.provides]

            item.name = NATIVE_PREFIX + item.name
            item.deps = [NATIVE_PREFIX + d for d in deps]
            item.toolDeps = []
            item.provides = [NATIVE_PREFIX + p for p in provides]
            self.buildDefs.append(item)

        for item in targetItems:
            item.deps = item.deps + [NATIVE_PREFIX + d for d in item.toolDeps]

        return True


def createWorkTree(config) -> int:
    ''' '''
    dirs = [
        (config.prefix, 'root directory'),
        (config.sourcesDir, 'sources directory'),
        (config.buildsDir, 'builds directory'),
    ]
    if config.buildMachine:
        dirs.append((config.buildToolsPrefix, 'build machine root directory'))

    for dirItem in dirs:
        if not os.path.exists(dirItem[0]):
            logging.debug(f" * creating {dirItem[1]} {dirItem[0]}")
            os.makedirs(dirItem[0])
        else:
            logging.debug(f" * {dirItem[1]} {dirItem[0]} already exists")

        if not os.path.isdir(dirItem[0]):
            logging.error(f"{dirItem[1]} {dirItem[0]} is not a directory")
            return 1

    return 0

_ARGS_CONTINUE, _ARGS_HELP, _ARGS_VERSION, _ARGS_ERROR = range(4)

def treatArgOrOption(config, option, value, fromCmdLine) -> int:
    if not fromCmdLine:
        option = '--' + option

    if option in ('-h', '--help',):
        return _ARGS_HELP

    if option in ('-v', '--version',):
        print(accendino.__version__)
        return _ARGS_VERSION

    if option in ('--prefix',):
        config.prefix = pathlib.PurePath(os.path.abspath(value))
    elif option in ('-d', '--debug',):
        logging.level('debug')
        config.debug = True
    elif option in ('--build-type',):
        config.buildType = value
        if config.buildType not in BUILD_TYPES:
            print(f"invalid build type {config.buildType}")
            return _ARGS_ERROR
    elif option in ('--build-as-debug',):
        config.debugArtifacts.update(v.strip() for v in value.split(',') if v.strip())
    elif option in ('--targets',):
        config.targets = value.split(',')
    elif option in ('--buildWithPowershell',):
        config.buildWithPowershell = True
    elif option in ('--no-packages',):
        config.checkPackages = False
    elif option in ('--build-deps',):
        config.doBuild = False
    elif option in ('--work-dir', ):
        config.workDir = pathlib.PurePath(os.path.abspath(value))
    elif option in ("--resume-from", ):
        config.resumeFrom = value
    elif option in ('--refreshSources',):
        config.refreshSources = True
    elif option in ('--refresh',):
        config.refresh = True
    elif option in ('--options',):
        if not fromCmdLine:
            logging.error("options file can't be given in an options file")
            return _ARGS_ERROR
        config.optionsFile = value
    elif option in ("--targetArch", ):
        value = ARCHS_MAP.get(value, value)
        if not value in ARCHS:
            logging.error(f'arch {value} not yet supported')
            return _ARGS_ERROR
        config.targetArch = value
    elif option in ("--targetDistrib", ):
        if value == 'mingw32':
            config.targetDistrib = 'mingw'
            config.targetArch = 'i686'
            config.toolchain = 'mingw'
        elif value == 'mingw64':
            config.targetDistrib = 'mingw'
            config.targetArch = 'x86_64'
            config.toolchain = 'mingw'
        elif value == 'emscripten':
            config.targetDistrib = 'emscripten'
            config.targetArch = 'wasm32'
            config.toolchain = 'emscripten'
        else:
            config.targetDistrib = value
    elif option in ('--toolchain',):
        config.toolchain = value
    elif option in ('--buildToolsPrefix',):
        config.buildToolsPrefix = pathlib.PurePath(os.path.abspath(value))
    elif option in ('--buildToolchain',):
        config.buildToolchain = value
    elif option in ("--project", ):
        config.projectName = value
    else:
        logging.error(f"unknown option {value}")
        return _ARGS_ERROR

    return _ARGS_CONTINUE


def run(args: T.List[str]) -> int:
    ''' '''
    logging.level("info")

    config = AccendinoConfig()

    opts, extraArgs = getopt.getopt(args[1:], "hdv", [
        "prefix=", "help", "debug", "no-packages", "build-deps", "targets=", "build-type=", "build-as-debug=", "options=",
        "work-dir=", "resume-from=", "project=", "targetDistrib=", "targetArch=", "toolchain=", "buildToolsPrefix=", "buildToolchain=",
        "buildWithPowershell", "version", "refreshSources", "refresh"
    ])

    for option, value in opts:
        argRes = treatArgOrOption(config, option, value, True)
        if argRes in (_ARGS_ERROR, _ARGS_HELP,):
            return doHelp(args[1:], argRes == _ARGS_ERROR)
        if argRes == _ARGS_VERSION:
            return 0

    logging.info("=== accendino ===")

    if config.optionsFile:
        logging.debug(f'reading build options from {config.optionsFile}')
        config.options = configparser.ConfigParser()
        config.options.optionxform = str
        config.options.read(config.optionsFile)

        if 'accendino' in config.options.sections():
            # inject key/values in the accendino section as command line args
            for option, value in config.options['accendino'].items():
                argRes = treatArgOrOption(config, option, value, False)
                if argRes in (_ARGS_ERROR, _ARGS_HELP, _ARGS_VERSION):
                    logging.error(f'invalid item {option}={value} in accendino section')
                    return 1


    config.sources += extraArgs
    if not config.sources: # defaults to build ogon
        logging.info('no source file provided using default ogon.accendino')
        config.sources += ['ogon.accendino']

    (distribId, distribVersion) = detectPlatform()

    if config.targetArch is None:
        config.targetArch = config.localArch

    logging.debug(f"target installation: {distribId} {distribVersion}")
    config.setPlatform(distribId, distribVersion)

    # grab a toolchain
    config.toolchainObj = getToolchain(config.toolchain, config, config.targetMachine)
    if not config.toolchainObj:
        logging.error(f"unable to find toolchain {config.toolchain}")
        return 2

    for f in config.sources:
        if not config.readSource(f, True):
            logging.error(f"error interpreting {f}")
            return 2
    config.finalizeConfig()
    if not config.setupBuildMachine():
        return 2

    for name in config.debugArtifacts:
        if not config.getBuildItem(name):
            logging.warning(f"--build-as-debug: unknown artifact {name}")

    retCode = createWorkTree(config)
    if retCode:
        return retCode

    buildList = []
    for t in config.targets:
        item = config.getBuildItem(t)
        if item:
            buildList.append(item)

    buildPlan = []
    if not config.createBuildPlan(config.targets, buildPlan):
        logging.error("unresolved targets or dependencies, aborting")
        return 7
    if config.debug:
        items = []
        for i in buildPlan:
            items.append(i.name)

        logging.debug(f"build plan: [{', '.join(items)}]")

    if config.checkPackages:
        packagesToCheck = []
        pkgManager = getPkgManager(config.distribId, packagesToCheck)

        retCode = config.treatPlatformPackages(pkgManager, packagesToCheck, buildPlan)
        if retCode:
            return retCode

    logging.debug(f'==> activating toolchain {config.toolchainObj.description}')
    if not config.toolchainObj.activate():
        logging.error('error activating toolchain')
        return 6

    if config.buildMachine:
        logging.debug(f'==> activating build machine toolchain {config.buildMachine.toolchainObj.description}')
        if not config.buildMachine.toolchainObj.activate():
            logging.error('error activating the build machine toolchain')
            return 6

    if not config.checkCrossFiles(buildPlan):
        return 6


    def buildModule(buildItem) -> bool:
        ''' '''
        logging.debug('==> preparing')
        if not buildItem.prepare(config):
            logging.error(f"prepare error for {buildItem.name}")
            return False

        logging.debug('==> building')
        if not buildItem.build(config):
            logging.error(f"build error for {buildItem.name}, check logs in {buildItem.logFile}")
            return False
        return True

    exitCode = 0
    if config.doBuild:
        for item in buildPlan:
            isDepsBuildArtifact = is_exact_instance(item, DepsBuildArtifact)

            extra = ' is only deps' if isDepsBuildArtifact else ''
            logging.info(f' * module {item.name}{extra}')

            if not isDepsBuildArtifact:
                logging.debug('==> init')
                if not item.init(config):
                    logging.error(f"error initializing {item.name}")
                    return 1

                if config.refresh and item in buildList:
                    logging.info(f' * forcing rebuild of {item.name}')
                    item.forceRebuild()

                logging.debug('==> checking out')
                if not item.checkout(config):
                    logging.error(f"checkout error for {item.name}")
                    return 1

            if config.resumeFrom:
                if item.name != config.resumeFrom:
                    continue

                # We've found the item to resume the build from
                config.resumeFrom = None

            if not isDepsBuildArtifact:
                if not buildModule(item):
                    return 1

    logging.info("=== finished ===")
    return exitCode

def main() -> int:
    ''' '''
    return run(sys.argv)

if __name__ == '__main__':
    if platform.python_version_tuple()[0] != '3':
        print("expecting python 3, exiting")
        sys.exit(1)

    sys.exit( main() )
