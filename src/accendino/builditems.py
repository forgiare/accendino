import os
import subprocess
import typing as T

from zenlog import log as logging
from accendino.sources import Source
from accendino.utils import mergePkgDeps, treatPackageDeps
import pickle
import accendino

class BuildStepDump:
    def __init__(self):
        self.gitCommit = None
        self.env = None
        self.args = None

PREPARE_DUMP_FILE = 'prepare.dump'

class DepsBuildArtifact:
    ''' basic build artifact only for dependencies and platform packages '''

    def __init__(self, name, deps=[], provides=[], pkgs={}) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
        '''
        self.name = name
        self.deps = deps
        self.provides = provides
        self.pkgs = treatPackageDeps(pkgs)

    def checkout(self, _config) -> bool:
        return True

    def prepare(self, _config) -> bool:
        return True

    def build(self, _config) -> bool:
        return True

    def __str__(self) -> str:
        return f"<{self.name}>"



class BuildArtifact(DepsBuildArtifact):
    ''' general build artifact '''

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[]) -> None:
        '''
            'commands list' are list of tuple(command, running_directory, command_description).
                * command is the list passed to subprocess.execute().
                * running_directory where to run the command (you can use {srcdir}, {builddir} they will be
                  replaced by their values).
                * command_description is used for logging and error reporting

            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param prepare_cmds: a command list of commands to run to prepare the build tree.
            @param build_cmds: a command list of commands to run to do the build and install
        '''
        if srcObj:
            pkgs = mergePkgDeps(pkgs, srcObj.pkgDeps)

        DepsBuildArtifact.__init__(self, name, deps, provides, pkgs)
        self.srcObj = srcObj
        self.sourceDir = None
        self.buildDir = None
        self.extraEnv = extraEnv
        self.logFile = None
        self.prepare_cmds = prepare_cmds[:]
        self.build_cmds = build_cmds[:]
        self.parallelJobs = True
        self.prepareStateFile = None

    def _computeEnv(self, config, extra) -> T.Dict[str, str]:
        r = os.environ.copy()

        # add a PKG_CONFIG_PATH
        r['PKG_CONFIG_PATH'] = f'{config.prefix}/{config.libdir}/pkgconfig'

        for k, v in extra.items():
            r[k] = v.format(prefix=config.prefix, libdir=config.libdir)
        return r

    def _expandConfigInString(self, item: str, config) -> str:
        values = {
            'prefix': config.prefix,
            'libdir': config.libdir,
            'srcdir': self.sourceDir,
            'builddir': self.buildDir
        }
        return item.format(**values)

    def _expandConfigInlist(self, l: T.List[str], config) -> T.List[str]:
        ret = []
        for item in l:
            ret.append( self._expandConfigInString(item, config) )

        return ret

    def checkout(self, config) -> bool:
        self.sourceDir = os.path.join(config.sourcesDir, self.name)

        self.buildDir = os.path.join(config.buildsDir, self.name, f"{config.targetDistrib}-{config.targetArch}-{config.buildType}")
        os.makedirs(self.buildDir, exist_ok=True)

        self.logFile = os.path.join(self.buildDir, 'build.log')
        self.prepareStateFile = os.path.join(self.buildDir, PREPARE_DUMP_FILE)

        with open(self.logFile, "at", encoding='utf8') as flog:
            return self.srcObj.checkout(self.sourceDir, flog)


    def showLogs(self, header) -> None:
        logging.error(header)
        print (open(self.logFile, "rt", encoding='utf8').read())

    def showLogOnError(self, retcode) -> bool:
        if retcode != 0:
            self.showLogs("error during execute:")
            return False
        return True

    def execute(self, cmd, env, cwd=None) -> bool:
        with open(self.logFile, "at", encoding='utf8') as flog:
            completedProc = subprocess.run(cmd, env=env, cwd=cwd, stdout=flog, stderr=flog)

        return self.showLogOnError(completedProc.returncode)

    def runCommands(self, runItems, env, config) -> bool:
        with open(self.logFile, "at", encoding='utf8') as flog:
            for cmd, path, cmddoc in runItems:
                cmd = self._expandConfigInlist(cmd, config)
                logging.debug(f'{cmddoc}: {' '.join(cmd)}')
                path = self._expandConfigInString(path, config)

                completedProc = subprocess.run(cmd, env=env, cwd=path, stdout=flog, stderr=flog)
                if completedProc.returncode != 0:
                    self.showLogs(f"error {cmddoc} with {' '.join(cmd)}:")
                    return False

        return True

    def prepare(self, config) -> bool:
        os.makedirs(self.buildDir, exist_ok=True)

        env = self._computeEnv(config, self.extraEnv)

        dump = BuildStepDump()
        dump.env = env.copy()
        dump.args = self.prepare_cmds

        dump2 = None
        if os.path.exists(self.prepareStateFile):
            try:
                with open(self.prepareStateFile, 'rb') as f:
                    dump2 = pickle.load(f)
            except:
                logging.info(f"prepare state file {self.prepareStateFile} exists but we couldn't read it")

        # do the comparison by hand
        dumpsEnvEqual = dump2 != None
        if dumpsEnvEqual:
            for k in dump2.env.keys():
                if dump.env[k] != dump2.env[k]:
                    dumpsEnvEqual = False

        if dumpsEnvEqual and dump.args == dump2.args:
            logging.debug(f"{self.name} is already prepared")
            return True

        if self.runCommands(self.prepare_cmds, env, config):
            try:
                with open(self.prepareStateFile, 'wb') as f:
                    pickle.dump(dump, f)
            except Exception as e:
                logging.info(f"unable to save prepare state file {self.prepareStateFile}: {e}")
            return True

        return False

    def build(self, config) -> bool:
        env = self._computeEnv(config, self.extraEnv)
        return self.runCommands(self.build_cmds, env, config)

    def setMakeNinjaCommands(self, config, cmd='ninja', build_target='all', install_target='install', parallelJobs=True,
                            runInstallDir='{builddir}') -> None:
        ''' configure build commands base on make or ninja '''
        maxJobs = 0
        if parallelJobs:
            maxJobs = config.maxJobs

        if maxJobs == 0:
            concurrentArgs = '-j'
        else:
            concurrentArgs = f'-j{maxJobs}'

        self.build_cmds = [
            ([cmd, '-C', '{builddir}', concurrentArgs, build_target], '{builddir}', 'building'),
            ([cmd, '-C', runInstallDir, concurrentArgs, install_target], '{builddir}', 'installing'),
        ]


class CustomCommandBuildArtifact(BuildArtifact):
    ''' an artifact that have is configured with a special command '''

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, prepare_src_cmds=[], prepare_cmds=[],
                 build_target='all', install_target='install') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
        '''
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv=extraEnv, provides=provides, pkgs=pkgs)

        self.build_target = build_target
        self.install_target = install_target

        for cmd in prepare_src_cmds:
            self.prepare_cmds.append((cmd, '{srcdir}', f'preparing sources {name}'))

        for cmd in prepare_cmds:
            self.prepare_cmds.append((cmd, '{builddir}', f'preparing build tree {name}'))


    def prepare(self, config) -> bool:
        self.setMakeNinjaCommands(config, 'make', parallelJobs=self.parallelJobs, build_target=self.build_target, install_target=self.install_target)
        return BuildArtifact.prepare(self, config)


class CMakeBuildArtifact(BuildArtifact):
    ''' cmake based build item '''

    def __init__(self, name: str, deps, srcObj: Source, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={}) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param cmakeOpts:
            @param parallelJobs:
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian|Redhat|Fedora': ['cmake']
        })
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)
        self.cmakeOpts = cmakeOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config) -> bool:
        cmake_cmd = ['cmake']

        if config.crossCompilation:
            cmake_cmd.append(f'-DCMAKE_TOOLCHAIN_FILE={config.getCrossPlatformFile("cmake", config.targetDistrib, config.targetArch)}')

        cmake_cmd += [
               '-DCMAKE_PREFIX_PATH={prefix}/lib/cmake;{prefix}/lib',
               f'-DCMAKE_BUILD_TYPE={config.cmakeBuildType()}',
               '-DCMAKE_INSTALL_PREFIX={prefix}',
               '-S', '{srcdir}',
               '-B', '{builddir}'
        ]

        cmake_cmd += self.cmakeOpts

        self.prepare_cmds = [
            (cmake_cmd, '{builddir}', 'running cmake')
        ]

        self.build_cmds = [
            (['cmake', '--build', '{builddir}'], '{builddir}', 'building'),
            (['cmake', '--install', '{builddir}'], '{builddir}', 'installing'),
        ]
        return BuildArtifact.prepare(self, config)



class QMakeBuildArtifact(BuildArtifact):
    ''' qmake + make based build item '''

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['qt5-qmake'],
            'Redhat|Fedora': ['qt5-qtbase-devel']
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)

        # needed to avoid some g++ link errors on Fedora
        self.extraEnv = extraEnv.copy()

        self.extraEnv.update({
            'RPM_ARCH': 'bla',
            'RPM_PACKAGE_RELEASE': 'bla',
            'RPM_PACKAGE_VERSION': 'bla',
            'RPM_PACKAGE_NAME': 'bla'
        })

    def prepare(self, config) -> bool:
        cmd = []
        qtChooser = config.distribId in ('Ubuntu', 'Debian', )
        if qtChooser:
            cmd = ['qtchooser', '-qt=qt5', '--run-tool=qmake']
        else:
            cmd = ['qmake-qt5']

        cmd += [
            'ADDITIONAL_RPATHS={prefix}/{libdir}/',
            'PREFIX={prefix}',
            '{srcdir}'
        ]

        self.prepare_cmds = [
            (cmd, '{builddir}', 'running qmake')
        ]

        self.setMakeNinjaCommands(config, 'make', parallelJobs=self.parallelJobs)
        return BuildArtifact.prepare(self, config)



class AutogenBuildArtifact(BuildArtifact):
    ''' autotools/autogen.sh + make based build item '''

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, autogenArgs=[], noconfigure=False,
                 isAutogen=True, bootstrapScript='bootstrap.sh', configureArgs=[], runInstallDir='{builddir}') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param autogenArgs:
            @param noconfigure:
            @param isAutogen:
            @param bootstrapScript:
            @param configureArgs:
            @param runInstallDir:
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['make', 'build-essential', 'automake', 'autoconf', 'libtool'],
            'Fedora|Redhat': ['make', 'autoconf', 'automake', 'libtool'],
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)

        self.isAutogen = isAutogen
        self.autogenArgs = autogenArgs
        self.noconfigure = noconfigure
        self.configureArgs = configureArgs
        self.bootstrapScript = bootstrapScript
        self.runInstallDir = runInstallDir

    def prepare(self, config) -> bool:
        if self.isAutogen:
            cmd = [os.path.join(self.sourceDir, "autogen.sh")] + self.autogenArgs
        else:
            cmd = [os.path.join(self.sourceDir, self.bootstrapScript)]

        autoGenRunDir = '{srcdir}'
        if self.noconfigure:
            cmd += ["--prefix={prefix}"]
            autoGenRunDir = '{builddir}'

        self.prepare_cmds = [
            (cmd, autoGenRunDir, 'running autogen/bootstrap')
        ]

        if not self.noconfigure:
            cmd = [ os.path.join(self.sourceDir, "configure"), "--prefix={prefix}"] + self.configureArgs
            self.prepare_cmds.append(
                (cmd, '{builddir}', 'running configure')
            )

        self.setMakeNinjaCommands(config, 'make', parallelJobs=self.parallelJobs, runInstallDir=self.runInstallDir)
        return BuildArtifact.prepare(self, config)


class MesonBuildArtifact(BuildArtifact):
    ''' meson + ninja based build item '''

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, mesonOpts=[], parallelJobs=True) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param mesonOpts:
            @param parallelJobs:
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian|Redhat|Fedora': ['meson', 'ninja-build']
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)
        self.mesonOpts = mesonOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config) -> bool:
        reconfigure = True
        if not os.path.exists(self.buildDir):
            os.makedirs(self.buildDir.odir, exist_ok=True)
            reconfigure = False

        cmd = ['meson', 'setup',
               '-Dprefix={prefix}',
               f'-Dbuildtype={config.mesonBuildType()}',
        ]

        if config.crossCompilation:
            cmd += ['--cross-file', config.getCrossPlatformFile('meson', config.targetDistrib, config.targetArch)]

        if reconfigure:
            cmd += ["--reconfigure"]
        cmd += self.mesonOpts
        cmd += [self.sourceDir]

        self.prepare_cmds = [
            (cmd, '{builddir}', 'running meson')
        ]

        self.setMakeNinjaCommands(config, 'ninja', parallelJobs=self.parallelJobs)
        return BuildArtifact.prepare(self, config)
