#! /usr/bin/env python3
import sys
import getopt
import os.path
import platform
import pathlib
import typing as T
from zenlog import log as logging

import accendino

from accendino.builditems import BuildArtifact, AutogenBuildArtifact, CMakeBuildArtifact, DepsBuildArtifact, \
    MesonBuildArtifact, QMakeBuildArtifact, CustomCommandBuildArtifact
from accendino.localdeps import BrewManager, DpkgManager, RpmManager
from accendino.sources import GitSource
from accendino.utils import ConditionalDep, DepsAdjuster, checkVersionCondition, checkAccendinoVersion


def doHelp(args, is_error) -> int:
    ''' '''
    print(f"usage: {args[0]} [--help] [--prefix=<prefix>] [--debug] [--targets=<targets>] [--build-type=<type>] <file>")
    print("\t--help: shows this help")
    print("\t--version: prints the version")
    print("\t--debug: show verbose information of building")
    print("\t--prefix=<prefix>: where to install")
    print("\t--targets=<targets>: a list of comma separated targets to build (by default full-ogon-freerdp2)")
    print("\t--build-type=[release|debug]: type of build (defaults to release)")
    print("\t--work-dir=<path>: a path to the working directory where sources are checked out and built")
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
            logging.debug(" * failed to detect platform using /etc/lsb-release")

        # Debian based systems
        try:
            content = open("/etc/debian_version", "rt", encoding='utf8').readline()
            distrib_id = "Debian"
            tokens = content.split('.', 2)
            distrib_version = f"{int(tokens[0]):02d}.{int(tokens[1]):02d}"
            return (distrib_id, distrib_version)
        except:
            logging.debug(" * failed reading /etc/debian_version")

        # Fedora based systems
        try:
            content = open("/etc/fedora-release", "rt", encoding='utf8').readline()
            distrib_id = "Fedora"
            tokens = content.split(' ', 4)
            distrib_version = tokens[2]
            return (distrib_id, distrib_version)
        except:
            logging.debug(" * failed reading /etc/fedora-version")

    elif plat_system in ("Windows", "Darwin",):
        distrib_id = plat_system
        if plat_system == "Windows":
            distrib_version = platform.win32_ver()[0]
        else:
            distrib_version = platform.mac_ver()[0]

    return (distrib_id, distrib_version)


BUILD_TYPES = ('release', 'debug',)


class AccendinoConfig:
    ''' Accendino configuration '''

    def __init__(self) -> None:
        ''' '''
        self.prefix = '/opt/ogon'
        self.debug = False
        self.buildType = 'release'
        self.workDir = os.path.join(os.getcwd(), 'work')
        self.sourcesDir = os.path.join(self.workDir, 'sources')
        self.buildsDir = os.path.join(self.workDir, 'build')
        self.targets = None
        self.buildDefs = []
        self.distribId = None
        self.distribVersion = None
        self.checkPackages = True
        self.libdir = 'lib'
        self.resumeFrom = None
        self.projectName = None
        self.maxJobs = 5

        #
        # populate a search path that has:
        #   * first paths provided in ACCENDINO_PATH,
        #   * then in the accendino pocket
        self.pocketSearchPaths = os.environ.get('ACCENDINO_PATH', '').split(':') + \
            [ os.path.join(pathlib.Path(__file__).parent, 'pocket') ]

        def includeFn(fname) -> bool:
            ''' '''
            searchPaths = ['.', 'pocket'] + self.pocketSearchPaths
            if fname.startswith('.'):
                searchPaths = []

            for p in searchPaths:
                fpath = os.path.join(p, fname)
                if os.path.exists(fpath) and os.path.isfile(fpath):
                    logging.debug(f"including file '{fpath}'")
                    return self.readSources([fpath])

            logging.error(f'unable to find {fname} in pockets')
            return False

        def pickDeps(name: str) -> T.List[T.Any]:
            ''' '''
            targets = self.context.get("ARTIFACTS", [])
            for t in targets:
                if t.name == name:
                    return t.deps[:]
            return None

        def pickPkgDeps(name: str, extra = None, override : bool = False) -> T.Dict[str, T.List[str]]:
            ''' '''
            ret = None
            targets = self.context.get("ARTIFACTS", [])
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

        self.sources = []
        self.context = {
            'ARTIFACTS': [],
            'DEFAULT_TARGETS': None,
            'GitSource': GitSource,
            'DepsBuildArtifact': DepsBuildArtifact,
            'CMakeBuildArtifact': CMakeBuildArtifact,
            'QMakeBuildArtifact': QMakeBuildArtifact,
            'AutogenBuildArtifact': AutogenBuildArtifact,
            'MesonBuildArtifact': MesonBuildArtifact,
            'CustomCommandBuildArtifact': CustomCommandBuildArtifact,
            'BuildArtifact': BuildArtifact,
            'include': includeFn,
            'checkDistrib': checkDistrib,
            'pickDeps': pickDeps,
            'pickPkgDeps': pickPkgDeps,
            'logging': logging,
            'DepsAdjuster': DepsAdjuster,
            'accendinoVersion': accendino.__version__,
            'UBUNTU_LIKE': 'Debian|Ubuntu',
            'REDHAT_LIKE': 'Fedora|Redhat',
            'checkAccendinoVersion': checkAccendinoVersionFn,
        }

    def cmakeBuildType(self) -> str:
        ''' '''
        if self.buildType == 'release':
            return 'Release'

        if self.buildType == 'debug':
            return 'Debug'

        raise Exception(f"{self.buildType} build type not supported for cmake")

    def mesonBuildType(self) -> str:
        ''' '''
        if self.buildType in ['release', 'debug']:
            return self.buildType
        raise Exception(f"{self.buildType} build type not supported for meson")

    def getBuildItem(self, name) -> BuildArtifact:
        ''' '''
        for item in self.buildDefs:
            if item.name == name or name in item.provides:
                return item
        return None

    def setPlatform(self, distribId, distribVersion) -> None:
        self.distribId = distribId
        self.distribVersion = distribVersion

        self.context['distribId'] = distribId
        self.context['distribVersion'] = distribVersion

        if self.distribId in ['Redhat', 'Fedora']:
            self.libdir = 'lib64'

    def treatPlatformPackages(self, buildItems) -> None:
        ''' '''
        # let's compute platform package requirements
        fullName = self.distribId + " " + self.distribVersion
        packagesToCheck = []

        for item in buildItems:
            if isinstance(item, str):
                continue

            if fullName in item.pkgs:
                pkgs = item.pkgs[fullName]
            elif self.distribId in item.pkgs:
                pkgs = item.pkgs[self.distribId]
            else:
                logging.warning(f" * warning, {item.name} has no package dependency for the current platform")
                continue

            packagesToCheck += pkgs[:]

        packagesToCheck = list(set(packagesToCheck))

        if self.distribId in ('Ubuntu', 'Debian', ):
            pkgManager = DpkgManager()
        elif self.distribId in ('Fedora', 'RedHat', ):
            pkgManager = RpmManager()
        elif self.distribId in ('Windows',):
            pkgManager = None
        elif self.distribId in ('Darwin',):
            pkgManager = BrewManager()

        if pkgManager:
            toInstall = pkgManager.check(packagesToCheck)
            if toInstall:
                if not pkgManager.installPackages(toInstall):
                    logging.error(" * error during package installation")
                    sys.exit(4)

    def createBuildPlan(self, itemsToBuild, buildPlan) -> None:
        ''' '''

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

                else:
                    logging.error(f"unable to find build dependency {item}")

        plan = []
        provided = []
        addBuildItems(itemsToBuild, plan, provided)

        for itemStr in plan:
            item = self.getBuildItem(itemStr)
            if item:
                buildPlan.append(item)
            else:
                buildPlan.append(itemStr)


    def readSources(self, fnames: T.List[str]) -> bool:
        ''' '''
        for fname in fnames:
            with open(fname, "rt", encoding="utf8") as f:
                code = compile(f.read(), os.path.basename(fname), "exec")
                exec(code, {}, self.context)

        return True

    def finalizeConfig(self) -> bool:
        ''' '''
        #
        for buildItem in self.context.get('ARTIFACTS', []):
            newDeps = []
            for dep in buildItem.deps:
                if isinstance(dep, str):
                    newDeps.append(dep)
                elif isinstance(dep, ConditionalDep):
                    newDeps = dep.apply(self, newDeps)
                else:
                    logging.error(f'don\'t know how to treat artifact dependency with type {type(dep)}')
            buildItem.deps = newDeps

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

            self.buildDefs.append(buildItem)

        if not self.targets:
            defaultTargets = self.context.get('DEFAULT_TARGETS', 'ogon')
            if defaultTargets:
                self.targets = defaultTargets.split(",")

        if not self.projectName:
            self.projectName = self.context.get('PROJECT', None)

        if self.projectName:
            self.sourcesDir = os.path.join(self.workDir, self.projectName, 'sources')
            self.buildsDir = os.path.join(self.workDir, self.projectName, 'build')
        else:
            self.sourcesDir = os.path.join(self.workDir, 'sources')
            self.buildsDir = os.path.join(self.workDir, 'build')

        return True


def createWorkTree(config) -> int:
    ''' '''
    dirs = [
        (config.prefix, 'root directory'),
        (config.sourcesDir, 'sources directory'),
        (config.buildsDir, 'builds directory'),
    ]

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



def run(args: T.List[str]) -> int:
    ''' '''
    logging.level("info")

    config = AccendinoConfig()

    opts, extraArgs = getopt.getopt(args[1:], "hdv", [
        "prefix=", "help", "debug", "no-packages", "targets=", "build-type=",
        "work-dir=", "resume-from=", "project=", "version"
    ])

    for option, value in opts:
        if option in ('-h', '--help',):
            return doHelp(args[1:], False)

        if option in ('-v', '--version',):
            print(accendino.__version__)
            return 0

        if option in ('--prefix',):
            config.prefix = value
        elif option in ('-d', '--debug',):
            logging.level('debug')
            config.debug = True
        elif option in ('--build-type',):
            config.buildType = value
            if config.buildType not in BUILD_TYPES:
                print(f"invalid build type {config.buildType}")
                return doHelp(args, True)
        elif option in ('--targets',):
            config.targets = value.split(',')
        elif option in ('--no-packages'):
            config.checkPackages = False
        elif option in ('--work-dir', ):
            config.workDir = value
            config.buildsDir = os.path.join(value, 'build')
            config.sourcesDir = os.path.join(value, 'sources')
        elif option in ("--resume-from", ):
            config.resumeFrom = value
        elif option in ("--project", ):
            config.projectName = value
        else:
            logging.error(f"unknown option {value}")

    logging.info("=== accendino, as OGON installer ===")

    config.sources += extraArgs
    if not config.sources: # defaults to build ogon
        logging.info(' * no source file provided using default ogon.conf')
        config.sources += ['ogon.conf']

    (distribId, distribVersion) = detectPlatform()
    logging.debug(f" * target installation: {distribId} {distribVersion}")
    config.setPlatform(distribId, distribVersion)

    config.readSources(config.sources)
    config.finalizeConfig()

    retCode = createWorkTree(config)
    if retCode:
        return retCode

    buildList = []
    for t in config.targets:
        item = config.getBuildItem(t)
        if item:
            buildList.append(item)

    buildPlan = []
    config.createBuildPlan(config.targets, buildPlan)
    if config.debug:
        items = []
        for i in buildPlan:
            items.append(i.name)

        logging.debug(f" * build plan: {' '.join(items)}")

    if config.checkPackages:
        config.treatPlatformPackages(buildPlan)


    def buildModule(buildItem) -> bool:
        ''' '''
        logging.info(f' * module {buildItem.name}')
        logging.debug('   ==> checking out')
        if not buildItem.checkout(config):
            logging.error(f"checkout error for {buildItem.name}")
            return False

        logging.debug('   ==> preparing')
        if not buildItem.prepare(config):
            logging.error(f"prepare error for {buildItem.name}")
            return False

        logging.debug('   ==> building')
        if not buildItem.build(config):
            logging.error(f"build error for {buildItem.name}, check logs in {buildItem.logFile}")
            return False
        return True

    exitCode = 0
    for item in buildPlan:
        if config.resumeFrom:
            if item.name != config.resumeFrom:
                continue

            # We've found the item to resume the build from
            config.resumeFrom = None

        if not buildModule(item):
            return 1

    logging.info("=== finished, OGON installed ===")
    return exitCode

def main() -> int:
    ''' '''
    return run(sys.argv)

if __name__ == '__main__':
    if platform.python_version_tuple()[0] != '3':
        print("expecting python 3, exiting")
        sys.exit(1)

    sys.exit( main() )
