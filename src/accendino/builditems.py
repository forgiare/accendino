import os
import subprocess
import pickle
import pathlib
import typing as T

from zenlog import log as logging
from accendino.sources import Source
from accendino.utils import mergePkgDeps, treatPackageDeps, doMingwCrossDeps, RunInShell


class BuildStepDump:
    def __init__(self):
        self.gitCommit = None
        self.env = None
        self.args = None

    def __eq__(self, other) -> bool:
        if self.gitCommit != other.gitCommit:
            return False

        # check environment
        for k in self.env.keys():
            if not k in other.env:
                return False

            if self.env[k] != other.env.get(k, None):
                return False

        if len(self.args) != len(other.args):
            return False

        # check commands
        i = 0
        for (cmds1, dir1, comment1) in self.args:
            (cmds2, dir2, comment2) = other.args[i]

            if dir1 != dir2 or comment1 != comment2:
                return False

            if isinstance(cmds1, RunInShell):
                cmds1 = cmds1.expand()

            if isinstance(cmds2, RunInShell):
                cmds1 = cmds1.expand()

            if len(cmds2) != len(cmds2):
                return False

            j = 0
            for s1 in cmds1:
                # check commands by stringify them for a correct NativePath comparison
                if not isinstance(s1, str):
                    s1 = str(s1)

                s2 = cmds2[j]
                if not isinstance(s2, str):
                    s2 = str(s2)

                if s1 != s2:
                    return False
                j += 1

            i += 1

        return True

PREPARE_DUMP_FILE = 'accendino.prepared'
BUILT_FILE = 'accentino.built'


class DepsBuildArtifact:
    ''' basic build artifact only for dependencies and platform packages '''

    def __init__(self, name, deps=[], provides=[], pkgs={}, toolchainArtifacts='c') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        self.name = name
        self.deps = deps
        self.provides = provides
        self.pkgs = treatPackageDeps(pkgs)
        self.prepareStateFile = None
        self.builtFile = None
        if isinstance(toolchainArtifacts, str):
            self.toolchainArtifacts = toolchainArtifacts.split(',')
        else:
            self.toolchainArtifacts = toolchainArtifacts

    def checkout(self, _config) -> bool:
        return True

    def prepare(self, _config) -> bool:
        return True

    def build(self, _config) -> bool:
        return True

    def __str__(self) -> str:
        return f"<{self.name}>"

WIN_PREPARE_SCRIPT = 'prepare.ps1'
WIN_BUILD_SCRIPT = 'build.ps1'

class BuildArtifact(DepsBuildArtifact):
    ''' general build artifact '''

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[],
                 toolchainArtifacts='c') -> None:
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
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        if srcObj:
            pkgs = mergePkgDeps(pkgs, srcObj.pkgDeps)

        DepsBuildArtifact.__init__(self, name, deps, provides, pkgs, toolchainArtifacts)
        self.srcObj = srcObj
        self.sourceDir = None
        self.buildDir = None
        self.extraEnv = extraEnv
        self.logFile = None
        self.prepare_cmds = prepare_cmds[:]
        self.build_cmds = build_cmds[:]
        self.parallelJobs = True
        self.needsMsys2 = False

    def _updatePATHlike(self, config, env: T.Dict[str, str], key: str, preExtra: T.List[str] = [],
                        postExtra: T.List[str] = [], sep: str = ':') -> None:
        ''' updates an env variable that is like PATh or PKG_CONFIG_PATH '''
        value = env.get(key, None)
        if value:
            l = value.split(sep)
        else:
            l = []

        ret = []
        for item in preExtra + l + postExtra:
            item = self._expandConfigInString(item, config)
            if item not in ret:
                ret.append(item)

        if len(ret) > 0:
            env[key] = sep.join(ret)


    def _createEnvFileUnix(self, env: T.Dict[str, str], keys: T.List[str]) -> None:
        with open(self.buildDir / 'setEnv.sh', 'wt', encoding='utf8') as f:
            f.write(f'# environment variables for artifact {self.name}\n')
            for k in keys:
                f.write(f'export {k}="{env[k]}"\n')

    def _pushPowerShellEnv(self, f, env: T.Dict[str, str], keys: T.List[str]) -> None:
        f.write(f'# environment variables for artifact {self.name}\n')
        for k in keys:
            f.write(f"$env:{k} = '{env[k]}'\n")

        f.write('\n')

    def _createEnvFileWin32(self, env: T.Dict[str, str], keys: T.List[str]) -> None:
        with open(self.buildDir / 'setEnv.ps1', 'wt', encoding='utf8') as f:
            self._pushPowerShellEnv(f, env, keys)

            if self.needsMsys2:
                f.write("$env:MSYS2_PATH_TYPE = 'inherit'\n")


    def _computeEnv(self, config, extra: T.Dict[str, str], createEnvFile: bool=False) -> T.Tuple[T.Dict[str, str], T.List[str]]:
        r = os.environ.copy()
        r.update(extra)

        # add a PKG_CONFIG_PATH
        xkeys = list(extra.keys()) + ['PKG_CONFIG_PATH']
        self._updatePATHlike(config, r, 'PKG_CONFIG_PATH', ['{prefix_posix}/{libdir}/pkgconfig'])
        if not config.crossCompilation:
            # adds the target bin directory
            self._updatePATHlike(config, r, 'PATH', [pathlib.PurePath(config.prefix, 'bin')], sep=os.pathsep)
            xkeys.append('PATH')

        if createEnvFile:
            fileDumper = self._createEnvFileWin32 if config.distribId in ('Windows', ) else self._createEnvFileUnix
            fileDumper(r, xkeys)

        return (r, xkeys)

    def _expandConfigInString(self, item: str, config) -> str:
        if not isinstance(item, str):
            item = str(item)

        values = {
            'libdir': config.libdir,
            'prefix': config.prefix,
            'prefix_posix': config.prefix.as_posix(),
            'srcdir': self.sourceDir,
            'srcdir_posix': self.sourceDir.as_posix(),
            'builddir': self.buildDir,
            'builddir_posix': self.buildDir.as_posix()
        }
        return item.format(**values)

    def _expandConfigForPath(self, item: str, _config):
        knownPaths = {
            '{srcdir}': self.sourceDir,
            '{srcdir_posix}': self.sourceDir.as_posix(),
            '{builddir}': self.buildDir,
            '{builddir_posix}': self.buildDir.as_posix(),
        }
        return knownPaths.get(item, item)

    def _expandConfigInlist(self, l: T.List[str], config) -> T.List[str]:
        ret = []
        for item in l:
            ret.append( self._expandConfigInString(item, config) )

        return ret

    def checkout(self, config) -> bool:
        self.sourceDir = config.sourcesDir / self.name

        self.buildDir = config.buildsDir / self.name / f"{config.targetDistrib}-{config.targetArch}-{config.buildType}"
        os.makedirs(self.buildDir, exist_ok=True)

        self.logFile = self.buildDir / 'build.log'
        self.prepareStateFile = self.buildDir / PREPARE_DUMP_FILE
        self.builtFile = self.buildDir / BUILT_FILE

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
                logging.debug(f'{cmddoc}: {" ".join(cmd)}')
                path = pathlib.Path(self._expandConfigForPath(path, config))

                completedProc = subprocess.run(cmd, env=env, cwd=path, stdout=flog, stderr=flog)
                if completedProc.returncode != 0:
                    self.showLogs(f"error {cmddoc} with {' '.join(cmd)}:")
                    return False

        return True

    def _createPrepareFileUnix(self, config, _env, _xkeys) -> None:
        with open(self.buildDir / "prepare.sh", "wt", encoding='utf8') as f:
            f.write(f'# prepare commands for artifact {self.name}\n\n')
            lastDir = None
            for cmd, path, cmddoc in self.prepare_cmds:
                f.write(f'# {cmddoc}\n')

                path = self._expandConfigInString(path, config)
                if lastDir != path:
                    f.write(f'cd "{path}"\n')

                cmd = self._expandConfigInlist(cmd, config)
                f.write('"')
                f.write('" "'.join(cmd))
                f.write('"\n\n')

                lastDir = path

    def _createPrepareFileWin32(self, config, env, xkeys) -> None:
        with open(self.buildDir / WIN_PREPARE_SCRIPT, "wt", encoding='utf8') as f:
            f.write("$PSDefaultParameterValues['*:Encoding'] = 'utf8'\n")
            if self.needsMsys2:
                f.write("$Env:MSYS2_PATH_TYPE = 'inherit'\n")

            self._pushPowerShellEnv(f, env, xkeys)

            toolchainContent = config.toolchainObj.prepareItems()
            if toolchainContent:
                f.write(f'# added by toolchain {config.toolchainObj.description}\n')
                f.write(toolchainContent)
                f.write('\n')

            f.write(f'#\n# prepare commands for artifact {self.name}\n#\n\n')
            lastDir = None
            for cmd, path, cmddoc in self.prepare_cmds:
                f.write(f'# {cmddoc}\n')

                path = self._expandConfigInString(path, config)
                if lastDir != path:
                    f.write(f'cd "{path}"\n')

                cmd = self._expandConfigInlist(cmd, config)
                cmdStr = "' '".join(cmd)
                f.write(f"& '{cmdStr}'\n\n")

                lastDir = path

    def needsRebuildFromDepsUpdates(self, config):
        if not self.builtFile or not os.path.exists(self.builtFile):
            return False

        self_mtime = os.stat(self.builtFile).st_mtime

        for dep in self.deps:
            artifact = config.getBuildItem(dep)
            if artifact and artifact.builtFile and os.path.exists(artifact.builtFile):
                mtime = os.stat(artifact.builtFile).st_mtime
                if self_mtime < mtime:
                    logging.debug(f'rebuilding {self.name} because of {artifact.name} has a more recent build')
                    return True
        return False


    def prepare(self, config) -> bool:
        os.makedirs(self.buildDir, exist_ok=True)

        if self.needsRebuildFromDepsUpdates(config):
            # some of our deps have been updated, let's rebuild
            if os.path.exists(self.prepareStateFile):
                os.remove(self.prepareStateFile)

            if os.path.exists(self.builtFile):
                os.remove(self.builtFile)

        (env, xkeys) = self._computeEnv(config, self.extraEnv, config.debug)

        dump = BuildStepDump()
        dump.env = env.copy()
        dump.args = self.prepare_cmds

        dumpOnDisk = None
        if os.path.exists(self.prepareStateFile):
            try:
                with open(self.prepareStateFile, 'rb') as f:
                    dumpOnDisk = pickle.load(f)
            except:
                logging.info(f"prepare state file {self.prepareStateFile} exists but we couldn't read it")

        if dumpOnDisk and dump == dumpOnDisk:
            logging.debug(f"{self.name} is already prepared")
            return True

        if os.path.exists(self.builtFile):
            os.remove(self.builtFile)

        scriptBuilder = self._createPrepareFileWin32 if config.distribId in ('Windows',) else self._createPrepareFileUnix
        scriptBuilder(config, env, xkeys)

        ret = False
        if config.distribId in ('Windows', ):
            logging.debug(f'running powershell .\\{WIN_PREPARE_SCRIPT}')
            ret = self.execute(['powershell', '-ExecutionPolicy', 'Unrestricted', '-File', f'.\\{WIN_PREPARE_SCRIPT}'], env, self.buildDir)
        else:
            ret = self.runCommands(self.prepare_cmds, env, config)

        if ret:
            try:
                with open(self.prepareStateFile, 'wb') as f:
                    pickle.dump(dump, f)
            except Exception as e:
                logging.info(f"unable to save prepare state file {self.prepareStateFile}: {e}")
            return True

        return False

    def createBuiltFile(self) -> bool:
        try:
            with open(self.builtFile, "wt", encoding='utf8') as f:
                f.write('built')

            return True
        except:
            logging.error(f"unable to create built file {self.builtFile} for artifact {self.name}")
            return False

    def _createWin32BuildScript(self, config, env: T.Dict[str, str], xkeys) -> bool:
        with open(self.buildDir / WIN_BUILD_SCRIPT, "wt", encoding='utf8') as f:
            f.write("$PSDefaultParameterValues['*:Encoding'] = 'utf8'\n")
            if self.needsMsys2:
                f.write("$Env:MSYS2_PATH_TYPE = 'inherit'\n")

            self._pushPowerShellEnv(f, env, xkeys)

            toolchainItem = config.toolchainObj.prepareItems()
            if toolchainItem:
                f.write(f'# toolchain setup for {config.toolchainObj.description}\n{toolchainItem}\n')

            lastPath = None
            for cmd, path, cmddoc in self.build_cmds:
                f.write(f'# {cmddoc}\n')

                path = pathlib.Path(self._expandConfigForPath(path, config))
                if lastPath != path:
                    f.write(f'cd {path}\n')
                    lastPath = path

                cmd = self._expandConfigInlist(cmd, config)
                cmdStr = "' '".join(cmd)
                f.write(f"& '{cmdStr}'\n\n")

            return True


    def build(self, config) -> bool:
        if os.path.isfile(self.builtFile):
            logging.debug(f'artifact {self.name} already built')
            return True

        (env, xkeys) = self._computeEnv(config, self.extraEnv)

        if config.distribId in ('Windows',):
            if not self._createWin32BuildScript(config, env, xkeys):
                return False

            logging.debug(f'running powershell .\\{WIN_BUILD_SCRIPT}')
            cmd = ['powershell', '-ExecutionPolicy', 'Unrestricted', '-File', f'.\\{WIN_BUILD_SCRIPT}']
            return self.execute(cmd, env, self.buildDir) and self.createBuiltFile()

        return self.runCommands(self.build_cmds, env, config) and self.createBuiltFile()


    def setMakeNinjaCommands(self, config, cmd='ninja', build_target='all', install_target='install', parallelJobs=True,
                            runInstallDir='{builddir}') -> None:
        ''' configure build commands base on make or ninja '''
        if cmd in ('ninja', 'make', 'makeMsys2',):
            maxJobs = 0
            if parallelJobs:
                maxJobs = config.maxJobs

            if maxJobs == 0:
                concurrentArgs = '-j'
            else:
                concurrentArgs = f'-j{maxJobs}'

            if cmd == 'makeMsys2':
                self.build_cmds = [
                    (RunInShell(['make', '-C', '{builddir_posix}', concurrentArgs, build_target]).expand(), '{builddir_posix}', 'building'),
                    (RunInShell(['make', '-C', '{builddir_posix}', concurrentArgs, install_target]).expand(), '{builddir_posix}', 'installing'),
                ]
            else:
                self.build_cmds = [
                    ([cmd, '-C', '{builddir}', concurrentArgs, build_target], '{builddir}', 'building'),
                    ([cmd, '-C', runInstallDir, concurrentArgs, install_target], '{builddir}', 'installing'),
                ]
        elif cmd in ('nmake',):
            self.build_cmds = [
                ([cmd, build_target], '{builddir}', 'building'),
                ([cmd, install_target], '{builddir}', 'installing'),
            ]


class CustomCommandBuildArtifact(BuildArtifact):
    ''' an artifact that is configured with a special command '''

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides: T.List[str] = [], pkgs={}, prepare_src_cmds=[], prepare_cmds=[],
                 builder='make', build_target='all', install_target='install', toolchainArtifacts='c') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param prepare_src_cmds: the list of commands to prepare the source directory
            @param prepare_cmds: the list of commands to prepare the build directory
            @param builder: which builder to use can be ninja, make or nmake
            @param build_target: target to build
            @param install_target: install to build
            @param toolchainArtifacts: artifacts that we need from the toolchain

        '''
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv=extraEnv, provides=provides, pkgs=pkgs, toolchainArtifacts=toolchainArtifacts)

        self.builder = builder
        self.build_target = build_target
        self.install_target = install_target

        for cmd in prepare_src_cmds:
            if isinstance(cmd, RunInShell):
                cmd = cmd.expand()
                self.needsMsys2 = True
            self.prepare_cmds.append((cmd, '{srcdir}', f'preparing sources {name}'))

        for cmd in prepare_cmds:
            if isinstance(cmd, RunInShell):
                cmd = cmd.expand()
                self.needsMsys2 = True

            self.prepare_cmds.append((cmd, '{builddir}', f'preparing build tree {name}'))

        if builder == 'makeMsys2':
            self.needsMsys2 = True


    def prepare(self, config) -> bool:
        self.setMakeNinjaCommands(config, self.builder, parallelJobs=self.parallelJobs, build_target=self.build_target,
                                  install_target=self.install_target)
        return BuildArtifact.prepare(self, config)


class CMakeBuildArtifact(BuildArtifact):
    ''' cmake based build item '''

    def __init__(self, name: str, deps, srcObj: Source, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={},
                 toolchainArtifacts='c') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param cmakeOpts:
            @param parallelJobs:
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        extra = {
            'Ubuntu|Debian|Redhat|Fedora|Arch|FreeBSD|Darwin': ['cmake']
        }
        doMingwCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], ['cmake', 'ninja-build'], extra)
        pkgs = mergePkgDeps(pkgs, extra)

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts)
        self.cmakeOpts = cmakeOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config) -> bool:
        cmake_cmd = ['cmake']

        if config.crossCompilation:
            fname = config.getCrossPlatformFile("cmake", config.distribId, config.targetDistrib, config.targetArch)
            cmake_cmd.append(f'-DCMAKE_TOOLCHAIN_FILE={fname}')

        #  f'-DCMAKE_BUILD_TYPE={config.cmakeBuildType()}',
        cmake_cmd += [
               '-DCMAKE_PREFIX_PATH={prefix_posix}/lib/cmake;{prefix_posix}/lib',
                f'-DCMAKE_CONFIGURATION_TYPES={config.cmakeBuildType()}',
               '-DCMAKE_INSTALL_PREFIX={prefix_posix}',
               '-S', '{srcdir}',
               '-B', '{builddir}'
        ]

        cmake_cmd += self.cmakeOpts

        self.prepare_cmds = [
            (cmake_cmd, '{builddir}', 'running cmake')
        ]

        self.build_cmds = [
            (['cmake', '--build', '{builddir}', '--config', config.cmakeBuildType()], '{builddir}', 'building'),
            (['cmake', '--install', '{builddir}'], '{builddir}', 'installing'),
        ]
        return BuildArtifact.prepare(self, config)



class QMakeBuildArtifact(BuildArtifact):
    ''' qmake + make based build item '''

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, toolchainArtifacts='c++') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['qt5-qmake'],
            'Redhat|Fedora': ['qt5-qtbase-devel'],
            'FreeBSD': ['qt5-qmake'],
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts)

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
                 isAutogen=True, bootstrapScript='bootstrap.sh', configureArgs=[], runInstallDir='{builddir}', toolchainArtifacts='c') -> None:
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
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['make', 'build-essential', 'automake', 'autoconf', 'libtool'],
            'Fedora|Redhat': ['make', 'autoconf', 'automake', 'libtool'],
            'Arch|Darwin|FreeBSD': ['autoconf', 'automake', 'libtool'],
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts)

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

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, mesonOpts=[], parallelJobs=True,
                 toolchainArtifacts='c') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param mesonOpts:
            @param parallelJobs:
            @param toolchainArtifacts: artifacts that we need from the toolchain
        '''
        extra = {
            'Ubuntu|Debian|Redhat|Fedora': ['meson', 'ninja-build'],
            'Arch|FreeBSD|Darwin': ['meson', 'ninja'],
        }
        doMingwCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], ['meson', 'ninja-build'], extra)

        pkgs = mergePkgDeps(pkgs, extra)
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts)
        self.mesonOpts = mesonOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config) -> bool:
        reconfigure = os.path.exists(self.buildDir / 'meson-info')

        cmd = ['meson', 'setup',
               '-Dprefix={prefix}',
               f'-Dbuildtype={config.mesonBuildType()}',
        ]

        if config.crossCompilation:
            cmd += ['--cross-file', config.getCrossPlatformFile('meson',  config.distribId, config.targetDistrib, config.targetArch)]

        if reconfigure:
            cmd += ["--reconfigure"]
        cmd += self.mesonOpts
        cmd += [self.sourceDir]

        self.prepare_cmds = [
            (cmd, '{builddir}', 'running meson configure')
        ]

        self.build_cmds = [
            (['meson', 'compile'], '{builddir}', 'building'),
            (['meson', 'install'], '{builddir}', 'installing'),
        ]

        return BuildArtifact.prepare(self, config)
