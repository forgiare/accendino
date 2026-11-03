import os
import subprocess
import pickle
import pathlib
import typing as T
import urllib.request

from zenlog import log as logging
from accendino.sources import Source
from accendino.utils import mergePkgDeps, treatPackageDeps, doCrossDeps, RunInShell, as_msys2_path, \
    pkgConfigDirs


# environment variables that change from one shell session to another (typically a new SSH
# connection) without any impact on the build, they're ignored when checking for env drift
VOLATILE_ENV_VARS = {
    'SSH_CLIENT', 'SSH_CONNECTION', 'SSH_TTY', 'SSH_AUTH_SOCK', 'SSH_AGENT_PID',
    'PWD', 'OLDPWD', 'SHLVL', '_', 'TERM_SESSION_ID', 'WINDOWID', 'XDG_SESSION_ID',
    'SESSIONNAME', 'CLIENTNAME',
}

class BuildStepDump:
    def __init__(self):
        self.gitCommit = None
        self.env = None
        self.args = None

    def __eq__(self, other) -> bool:
        if self.gitCommit != other.gitCommit:
            return False

        # check environment
        keys = set(self.env.keys()) | set(other.env.keys())
        for k in keys - VOLATILE_ENV_VARS:
            if self.env.get(k, None) != other.env.get(k, None):
                logging.debug(f'environment variable {k} has changed since last prepare')
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
                cmds2 = cmds2.expand()

            if len(cmds1) != len(cmds2):
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
BUILT_FILE = 'accendino.built'


class DepsBuildArtifact:
    ''' basic build artifact only for dependencies and platform packages '''

    def __init__(self, name, deps=[], provides=[], pkgs={}, toolchainArtifacts='c', toolDeps=[], buildMachineOnly=False) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param toolchainArtifacts: artifacts that we need from the toolchain
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
        '''
        self.name = name
        self.deps = deps
        self.toolDeps = list(toolDeps)
        self.buildMachineOnly = buildMachineOnly
        self.provides = provides
        self.pkgs = treatPackageDeps(pkgs)
        self.prepareStateFile = None
        self.builtFile = None
        # the Machine this artifact is built for, set when the configuration is finalized
        self.machine = None
        if isinstance(toolchainArtifacts, str):
            self.toolchainArtifacts = toolchainArtifacts.split(',')
        else:
            self.toolchainArtifacts = toolchainArtifacts

    def init(self, _config) -> bool:
        return True

    def checkout(self, _config) -> bool:
        return True

    def prepare(self, _config) -> bool:
        return True

    def build(self, _config) -> bool:
        return True

    def exportedEnv(self, _config) -> T.Dict[str, str]:
        ''' environment variables given to the artifacts depending on this one (directly or not), PATH like variables
            (PATH, CMAKE_PREFIX_PATH, PKG_CONFIG_LIBDIR, ...) are prepended to their value
        '''
        return {}

    def forceRebuild(self) -> None:
        for f in (self.prepareStateFile, self.builtFile):
            if f and os.path.exists(f):
                os.remove(f)

    def __str__(self) -> str:
        return f"<{self.name}>"

WIN_PREPARE_SCRIPT = 'prepare.ps1'
WIN_BUILD_SCRIPT = 'build.ps1'

class BuildArtifact(DepsBuildArtifact):
    ''' general build artifact '''

    # how the builds go through ccache with --ccache: 'launcher' (the builder sets it up), 'cc' (CC and CXX are prefixed
    # with ccache), 'env' (just the ccache settings, the build commands use ccache if they want), None (no ccache)
    ccacheMode = None

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[],
                 toolchainArtifacts='c', skipToolchainEnv=False, toolDeps=[], buildMachineOnly=False) -> None:
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
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
            @param skipToolchainEnv: do not grab env variable from the toolchain
        '''
        if srcObj:
            pkgs = mergePkgDeps(pkgs, srcObj.pkgDeps)

        DepsBuildArtifact.__init__(self, name, deps, provides, pkgs, toolchainArtifacts, toolDeps, buildMachineOnly)
        self.srcObj = srcObj
        self.sourceDir = None
        self.buildDir = None
        self.buildType = None
        self.extraEnv = extraEnv
        self.logFile = None
        self.prepare_cmds = prepare_cmds[:]
        # if set, saved in the prepare state instead of prepare_cmds (that may depend on the build directory state)
        self.prepareDumpCmds = None
        self.build_cmds = build_cmds[:]
        self.parallelJobs = True
        self.needsMsys2 = False
        self.skipToolchainEnv = skipToolchainEnv

    def _updatePATHlike(self, config, env: T.Dict[str, str], key: str, preExtra: T.List[str] = [],
                        postExtra: T.List[str] = [], sep: str = ':') -> None:
        ''' updates an env variable that is like PATH or PKG_CONFIG_PATH '''
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

    def _pushShellEnv(self, f, env: T.Dict[str, str], keys: T.List[str]) -> None:
        f.write(f'# environment variables for artifact {self.name}\n')
        for k in keys:
            f.write(f"export {k}='{env[k]}'\n")

        f.write('\n')

    def _createEnvFileWin32(self, env: T.Dict[str, str], keys: T.List[str]) -> None:
        with open(self.buildDir / 'setEnv.ps1', 'wt', encoding='utf8') as f:
            self._pushPowerShellEnv(f, env, keys)

    def _updateEnvMap(self, config, base: T.Dict[str, str], extra: T.Dict[str, str]) -> T.Dict[str, str]:
        for k, v in extra.items():
            if not isinstance(v, str):
                v = str(v)

            if k in ('PATH', 'CMAKE_PREFIX_PATH',):
                self._updatePATHlike(config, base, k, v.split(os.pathsep), sep=os.pathsep)
            elif k in ('PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR',):
                self._updatePATHlike(config, base, k, v.split(':'))
            else:
                base[k] = v

    def _computeEnv(self, config, extra: T.Dict[str, str], createEnvFile: bool=False) -> T.Tuple[T.Dict[str, str], T.List[str]]:
        r = os.environ.copy()
        xkeys = []

        # PKG_CONFIG_PATH takes precedence over PKG_CONFIG_LIBDIR in pkg-config's
        # search order, so an inherited PKG_CONFIG_PATH from the host environment
        # would make system .pc files win over the ones in the deploy directory
        # that we set up below via PKG_CONFIG_LIBDIR. Drop it so PKG_CONFIG_LIBDIR
        # is the sole source of truth, and if some PKG_CONFIG_PATH where set it is
        # put back right after all our entries.
        orig_pkg_config_path = r.pop('PKG_CONFIG_PATH', None)

        if self.needsMsys2:
            r['MSYS2_PATH_TYPE'] = 'inherit'
            xkeys.append('MSYS2_PATH_TYPE')

        # start by updating the base environment with what's comes from the toolchain
        if not self.skipToolchainEnv:
            toolchainEnv = self.machine.toolchainObj.extraEnv(self.toolchainArtifacts)
            if toolchainEnv:
                self._updateEnvMap(config, r, toolchainEnv)
                xkeys += toolchainEnv.keys()

        # add a PKG_CONFIG_LIBDIR
        xkeys.append('PKG_CONFIG_LIBDIR')
        pkg_config_path = ':'.join(pkgConfigDirs('{prefix_posix}', '{libdir}', self.machine.targetDistrib, self.machine.arch,
                                                 orig_pkg_config_path, self.machine.crossCompilation))

        xx = {
            'PKG_CONFIG_LIBDIR': pkg_config_path,
        }

        # adds the target bin directory to the PATH
        if not self.machine.crossCompilation:
            xx['PATH'] = pathlib.PurePath(self.machine.prefix, 'bin')
            xkeys.append('PATH')
        elif config.buildMachine:
            # cross compiling with tools built for the build machine: make them found and runnable
            buildMachine = config.buildMachine
            xx['PATH'] = pathlib.PurePath(buildMachine.prefix, 'bin')
            xx['CMAKE_PROGRAM_PATH'] = pathlib.PurePath(buildMachine.prefix, 'bin').as_posix()
            xkeys += ['PATH', 'CMAKE_PROGRAM_PATH']

            # shared libraries of tools are found with the PATH on Windows
            libPathVar = None
            if buildMachine.distribId == 'Darwin':
                libPathVar = 'DYLD_LIBRARY_PATH'
            elif buildMachine.distribId != 'Windows':
                libPathVar = 'LD_LIBRARY_PATH'
            if libPathVar:
                libDir = pathlib.PurePath(buildMachine.prefix, buildMachine.libdir).as_posix()
                r[libPathVar] = os.pathsep.join([libDir] + ([r[libPathVar]] if r.get(libPathVar) else []))
                xkeys.append(libPathVar)

        self._updateEnvMap(config, r, xx)

        ccacheEnv = self._ccacheEnv(config, r)
        if ccacheEnv:
            self._updateEnvMap(config, r, ccacheEnv)
            xkeys += ccacheEnv.keys()

        for depEnv in self._depsExportedEnv(config):
            self._updateEnvMap(config, r, depEnv)
            xkeys += depEnv.keys()

        # finally add the user provided extra env
        self._updateEnvMap(config, r, extra)

        xkeys += extra.keys()
        xkeys = list( set(xkeys) )

        if createEnvFile:
            fileDumperFn = self._createEnvFileWin32 if self.machine.distribId in ('Windows', ) else self._createEnvFileUnix
            fileDumperFn(r, xkeys)

        return (r, xkeys)

    def _ccacheEnv(self, config, env: T.Dict[str, str]) -> T.Dict[str, str]:
        ''' returns the environment variables to compile through ccache, given the environment computed so far '''
        if not config.ccache or not self.ccacheMode:
            return {}

        ret = dict(config.ccacheEnv)
        if self.machine.targetDistrib == 'emscripten':
            # emcc runs clang through the wrapper, ccache knows clang better than emcc
            ret['EM_COMPILER_WRAPPER'] = 'ccache'
        elif self.ccacheMode == 'cc':
            for k in ('CC', 'CXX'):
                if env.get(k) and not env[k].startswith('ccache '):
                    ret[k] = f'ccache {env[k]}'
        return ret

    def _depsExportedEnv(self, config) -> T.List[T.Dict[str, str]]:
        ''' returns the environments exported by the dependencies of this artifact, and their dependencies '''
        ret = []
        seen = set()
        todo = list(self.deps)
        while todo:
            item = config.getBuildItem(todo.pop(0))
            if not item or item.name in seen:
                continue

            seen.add(item.name)
            todo += item.deps
            env = item.exportedEnv(config)
            if env:
                ret.append(env)
        return ret

    def _expandConfigInString(self, item: str, config) -> str:
        if not isinstance(item, str):
            item = str(item)

        values = {
            'libdir': self.machine.libdir,
            'prefix': self.machine.prefix,
            'prefix_posix': self.machine.prefix.as_posix(),
            'prefix_msys2': as_msys2_path(self.machine.prefix),
            'build_prefix': config.toolsPrefix,
            'build_prefix_posix': config.toolsPrefix.as_posix(),
            'srcdir': self.sourceDir,
            'srcdir_posix': self.sourceDir.as_posix(),
            'builddir': self.buildDir,
            'builddir_posix': self.buildDir.as_posix()
        }
        return item.format(**values)

    def _expandConfigForPath(self, item: str, _config):
        values = {
            'srcdir': self.sourceDir,
            'srcdir_posix': self.sourceDir.as_posix(),
            'builddir': self.buildDir,
            'builddir_posix': self.buildDir.as_posix(),
        }
        return item.format(**values)

    def _expandConfigInlist(self, l: T.List[str], config) -> T.List[str]:
        ret = []
        for item in l:
            ret.append( self._expandConfigInString(item, config) )

        return ret

    def init(self, config) -> bool:
        # artifacts for the build machine are named native:<name>, their directories native-<name>
        dirBaseName = self.name.replace(':', '-')
        self.sourceDir = config.sourcesDir / dirBaseName

        self.buildType = config.buildType
        if self.name in config.debugArtifacts or config.debugArtifacts.intersection(self.provides):
            self.buildType = 'debug'

        dirName = f"{self.machine.targetDistrib}-{self.machine.toolchainObj.description}-{self.machine.arch}-{self.buildType}"
        self.buildDir = config.buildsDir / dirName / dirBaseName

        os.makedirs(self.buildDir, exist_ok=True)

        self.logFile = self.buildDir / 'build.log'
        self.prepareStateFile = self.buildDir / PREPARE_DUMP_FILE
        self.builtFile = self.buildDir / BUILT_FILE
        return True

    def checkout(self, config) -> bool:
        with open(self.logFile, "at", encoding='utf8') as flog:
            ok = self.srcObj.checkout(self.sourceDir, flog, config.refreshSources)

        if ok and config.refreshSources and self.srcObj.refreshed:
            logging.info(f'source of {self.name} was refreshed, forcing a rebuild')
            for f in (self.prepareStateFile, self.builtFile):
                if f and os.path.exists(f):
                    os.remove(f)

        return ok


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

    def _createPrepareFileUnix(self, config, env, xkeys) -> None:
        with open(self.buildDir / "prepare.sh", "wt", encoding='utf8') as f:
            f.write(f'# prepare commands for artifact {self.name}\n\n')

            self._pushShellEnv(f, env, xkeys)

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

            self._pushPowerShellEnv(f, env, xkeys)

            toolchainContent = self.machine.toolchainObj.prepareItems()
            if toolchainContent:
                f.write(f'# added by toolchain {self.machine.toolchainObj.description}\n')
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
                f.write(f"& '{cmdStr}'\nif ($LastExitCode -ne 0) {{\n\tExit $LastExitCode\n}}\n")

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
                    logging.debug(f'rebuilding {self.name} because {artifact.name} has a more recent build')
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
        dump.args = self.prepare_cmds if self.prepareDumpCmds is None else self.prepareDumpCmds

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

        scriptBuilder = self._createPrepareFileWin32 if self.machine.distribId in ('Windows',) else self._createPrepareFileUnix
        scriptBuilder(config, env, xkeys)

        ret = False
        if self.machine.distribId in ('Windows', ) and config.buildWithPowershell:
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

            self._pushPowerShellEnv(f, env, xkeys)

            toolchainItem = self.machine.toolchainObj.prepareItems()
            if toolchainItem:
                f.write(f'# toolchain setup for {self.machine.toolchainObj.description}\n{toolchainItem}\n')

            lastPath = None
            for cmd, path, cmddoc in self.build_cmds:
                f.write(f'# {cmddoc}\n')

                path = pathlib.Path(self._expandConfigForPath(path, config))
                if lastPath != path:
                    f.write(f'cd {path}\n')
                    lastPath = path

                cmd = self._expandConfigInlist(cmd, config)
                cmdStr = "' '".join(cmd)
                f.write(f"& '{cmdStr}'\nif ($LastExitCode -ne 0) {{\n\tExit $LastExitCode\n}}\n")

            return True


    def build(self, config) -> bool:
        if os.path.isfile(self.builtFile):
            logging.debug(f'artifact {self.name} already built')
            return True

        (env, xkeys) = self._computeEnv(config, self.extraEnv)

        if self.machine.distribId in ('Windows',) and config.buildWithPowershell:
            if not self._createWin32BuildScript(config, env, xkeys):
                return False

            logging.debug(f'running powershell .\\{WIN_BUILD_SCRIPT}')
            cmd = ['powershell', '-ExecutionPolicy', 'Unrestricted', '-File', f'.\\{WIN_BUILD_SCRIPT}']
            return self.execute(cmd, env, self.buildDir) and self.createBuiltFile()

        return self.runCommands(self.build_cmds, env, config) and self.createBuiltFile()


    def setMakeNinjaCommands(self, config, cmd='ninja', build_targets='all', install_targets='install', parallelJobs=True,
                            runInstallDir='{builddir}') -> None:
        ''' configure build commands base on make or ninja '''

        if build_targets:
            if isinstance(build_targets, str):
                build_targets = build_targets.split(',')

        if install_targets:
            if isinstance(install_targets, str):
                install_targets = install_targets.split(',')

        if cmd in ('ninja', 'make', 'makeMsys2',):
            if not parallelJobs:
                concurrentArgs = '-j1'
            elif config.maxJobs == 0:
                concurrentArgs = '-j'
            else:
                concurrentArgs = f'-j{config.maxJobs}'

            if cmd == 'makeMsys2':
                for target in build_targets:
                    self.build_cmds.append( (RunInShell(['make', '-C', '{builddir_posix}', concurrentArgs, target]).expand(),
                            '{builddir_posix}', 'building'))

                for target in install_targets:
                    self.build_cmds.append( (RunInShell(['make', '-C', '{builddir_posix}', concurrentArgs, target]).expand(),
                                  '{builddir_posix}', 'installing'))

            else:
                for target in build_targets:
                    self.build_cmds.append( ([cmd, '-C', '{builddir}', concurrentArgs, target], '{builddir}', 'building'))

                for target in install_targets:
                    self.build_cmds.append(([cmd, '-C', runInstallDir, concurrentArgs, target], '{builddir}', 'installing'))

        elif cmd in ('nmake',):
            for target in build_targets:
                self.build_cmds.append( ([cmd, target], '{builddir}', 'building'))

            for target in install_targets:
                self.build_cmds.append( ([cmd, target], '{builddir}', 'installing') )


class CustomCommandBuildArtifact(BuildArtifact):
    ''' an artifact that is configured with a special command '''

    ccacheMode = 'env'

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides: T.List[str] = [], pkgs={}, prepare_src_cmds=[], prepare_cmds=[],
                 builder='make', build_target='all', install_target='install', toolchainArtifacts='c', skipToolchainEnv=False,
                 toolDeps=[], buildMachineOnly=False) -> None:
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
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
            @param skipToolchainEnv: do not grab env variable from the toolchain
        '''
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv=extraEnv, provides=provides, pkgs=pkgs,
                               toolchainArtifacts=toolchainArtifacts, skipToolchainEnv=skipToolchainEnv, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)

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
        self.setMakeNinjaCommands(config, self.builder, parallelJobs=self.parallelJobs, build_targets=self.build_target,
                                  install_targets=self.install_target)
        return BuildArtifact.prepare(self, config)


class CMakeBuildArtifact(BuildArtifact):
    ''' cmake based build item '''

    ccacheMode = 'launcher'

    def __init__(self, name: str, deps, srcObj: Source, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={},
                 toolchainArtifacts='c', cmakeProjectDir='{srcdir}', toolDeps=[], buildMachineOnly=False) -> None:
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
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
            @param cmakeProjectDir: directory containing the CMakeLists.txt, when it's not at the root of the sources
                    (a project shipped as an accendino asset to build or install a prebuilt distribution for instance)
        '''
        extra = {
            'Ubuntu|Debian|Redhat|Fedora|Arch|FreeBSD|Darwin': ['cmake']
        }
        doCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], ['cmake', 'ninja-build', 'make'], extra)
        pkgs = mergePkgDeps(pkgs, extra)

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)
        self.cmakeOpts = cmakeOpts
        self.parallelJobs = parallelJobs
        self.cmakeProjectDir = cmakeProjectDir

    def prepare(self, config) -> bool:
        cmakeBuildType = config.cmakeBuildType(self.buildType)
        cmake_cmd = ['cmake']

        if self.machine.crossCompilation:
            fname = self.machine.getCrossPlatformFile("cmake")
            cmake_cmd.append(f'-DCMAKE_TOOLCHAIN_FILE={fname}')

        # CMAKE_BUILD_TYPE is used by single-config generators (Makefiles, Ninja), CMAKE_CONFIGURATION_TYPES
        # by multi-config ones (Visual Studio)
        cmake_cmd += [
               '-DCMAKE_PREFIX_PATH={prefix_posix}/lib/cmake;{prefix_posix}/lib',
                f'-DCMAKE_BUILD_TYPE={cmakeBuildType}',
                f'-DCMAKE_CONFIGURATION_TYPES={cmakeBuildType}',
               '-DCMAKE_INSTALL_PREFIX={prefix_posix}',
               '-S', self.cmakeProjectDir,
               '-B', '{builddir}'
        ]

        if config.ccache and self.machine.targetDistrib != 'emscripten':
            cmake_cmd += ['-DCMAKE_C_COMPILER_LAUNCHER=ccache', '-DCMAKE_CXX_COMPILER_LAUNCHER=ccache']

        cmake_cmd += self.cmakeOpts

        self.prepare_cmds = [
            (cmake_cmd, '{builddir}', 'running cmake')
        ]

        # --parallel is translated by cmake to the generator's own option (-j for make/ninja, /m for msbuild);
        # without it make based generators build serially
        concurrentArgs = ['--parallel', '1']
        if self.parallelJobs:
            concurrentArgs = ['--parallel', f'{config.maxJobs}'] if config.maxJobs else ['--parallel']

        self.build_cmds = [
            (['cmake', '--build', '{builddir}', '--config', cmakeBuildType] + concurrentArgs, '{builddir}', 'building'),
            (['cmake', '--install', '{builddir}', '--config', cmakeBuildType], '{builddir}', 'installing'),
        ]

        if self.machine.targetDistrib == 'emscripten':
            # install(TARGETS) doesn't install the .wasm module of executables
            script = config.crossFileDir / 'emscripten-install-wasm.cmake'
            self.build_cmds.append((['cmake', '-DBUILD_DIR={builddir}', '-P', str(script)], '{builddir}', 'installing wasm modules'))
        return BuildArtifact.prepare(self, config)



class QMakeBuildArtifact(BuildArtifact):
    ''' qmake + make based build item '''

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, toolchainArtifacts='c++', toolDeps=[],
                 buildMachineOnly=False) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param toolchainArtifacts: artifacts that we need from the toolchain
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['qt5-qmake'],
            'Redhat|Fedora': ['qt5-qtbase-devel'],
            'FreeBSD': ['qt5-qmake'],
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)

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
        qtChooser = self.machine.distribId in ('Ubuntu', 'Debian', )
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

    ccacheMode = 'cc'

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, autogenArgs=[], noconfigure=False,
                 isAutogen=True, bootstrapScript='bootstrap.sh', configureArgs=[], runInstallDir='{builddir}', toolchainArtifacts='c',
                 toolDeps=[], buildMachineOnly=False) -> None:
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
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
        '''
        pkgs = mergePkgDeps(pkgs, {
            'Ubuntu|Debian': ['make', 'build-essential', 'automake', 'autoconf', 'libtool'],
            'Fedora|Redhat': ['make', 'autoconf', 'automake', 'libtool'],
            'Arch|Darwin|FreeBSD': ['autoconf', 'automake', 'libtool'],
        })

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)

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

    ccacheMode = 'cc'

    def __init__(self, name, deps, srcObj: Source, extraEnv={}, provides=[], pkgs={}, mesonOpts=[], parallelJobs=True,
                 toolchainArtifacts='c', mesonVersion: str = 'system', toolDeps=[], buildMachineOnly=False) -> None:
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
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
            @param mesonVersion: the meson version to use
        '''
        extra = {
            'Ubuntu|Debian|Redhat|Fedora': ['ninja-build'],
            'Arch|FreeBSD|Darwin': ['ninja'],
        }

        crossDeps = ['ninja-build']

        if mesonVersion == 'system':
            extra['Ubuntu|Debian|Redhat|Fedora'].append('meson')
            extra['Arch|FreeBSD|Darwin'].append('meson')

            crossDeps.append('meson')

        doCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], crossDeps, extra)

        pkgs = mergePkgDeps(pkgs, extra)
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)
        self.mesonOpts = mesonOpts
        self.parallelJobs = parallelJobs
        self.mesonVersion = mesonVersion
        self.mesonPath = 'meson'

    def init(self, config) -> bool:
        if not BuildArtifact.init(self, config):
            return False

        if self.mesonVersion == 'system':
            return True

        mesonRootDir = config.toolsDir / f'meson-{self.mesonVersion}'

        self.mesonPath = mesonRootDir / 'bin' / 'meson'
        if os.path.exists(mesonRootDir) and os.path.exists(self.mesonPath):
            logging.debug(f"meson {self.mesonVersion} already installed")
        else:
            mesonVersionString = 'meson'
            if self.mesonVersion != 'latest':
                mesonVersionString = f'meson=={self.mesonVersion}'

            env = os.environ.copy()
            cmds = [
                (['python', '-m', 'venv', mesonRootDir], '.', f'creating venv for {mesonVersionString}'),
                ([mesonRootDir / 'bin' / 'pip', 'install', mesonVersionString], '.', f'installing {mesonVersionString}'),
            ]
            if not self.runCommands(cmds, env, config):
                return False

        version = self.mesonVersion
        if version == 'latest':
            p = subprocess.run([str(self.mesonPath), '--version'], stdout=subprocess.PIPE, text=True, check=False)
            version = p.stdout.strip() or version
        config.registerTool(f'meson-{self.mesonVersion}', version)
        return True

    def _writeNativeFile(self, config) -> str:
        ''' writes the meson native file used when cross compiling, so that dependency(..., native: true) looks in the
            build machine prefix and the system, not in the target directories of PKG_CONFIG_LIBDIR. Returns its path
        '''
        buildMachine = config.buildMachine
        if buildMachine:
            prefix = pathlib.PurePath(buildMachine.prefix).as_posix()
            dirs = pkgConfigDirs(prefix, buildMachine.libdir, buildMachine.targetDistrib, buildMachine.arch,
                                 os.environ.get('PKG_CONFIG_PATH'))
        else:
            prefix = None
            dirs = pkgConfigDirs(None, 'lib', config.distribId, config.localArch, os.environ.get('PKG_CONFIG_PATH'))

        def mesonList(items: T.List[str]) -> str:
            return '[' + ', '.join(f"'{i}'" for i in items) + ']'

        content = '# generated by accendino, settings of the build machine\n\n'
        content += "[binaries]\npkg-config = 'pkg-config'\n\n"
        content += f'[properties]\npkg_config_libdir = {mesonList(dirs)}\n'
        if prefix:
            content += f'\n[built-in options]\ncmake_prefix_path = {mesonList([prefix])}\n'

        # only rewrite when it changes, meson regenerates the build when its native file is touched
        path = self.buildDir / 'accendino-native.ini'
        if not os.path.exists(path) or pathlib.Path(path).read_text(encoding='utf8') != content:
            with open(path, 'wt', encoding='utf8') as f:
                f.write(content)
        return str(path)

    def prepare(self, config) -> bool:
        cmd = [self.mesonPath, 'setup',
               '-Dprefix={prefix}',
               f'-Dbuildtype={config.mesonBuildType(self.buildType)}',
        ]

        if self.machine.crossCompilation:
            cmd += ['--cross-file', self.machine.getCrossPlatformFile('meson'),
                    '--native-file', self._writeNativeFile(config)]

        # always given (meson accepts it on a new build directory) so that the prepare state is the same for all runs
        cmd += ["--reconfigure"]

        # build both static and shared libraries unless the artifact asks for something else, emscripten
        # has no shared libraries
        if not any(opt.startswith(('-Ddefault_library=', '--default-library')) for opt in self.mesonOpts):
            cmd += ['-Ddefault_library=static' if self.machine.targetDistrib == 'emscripten' else '-Ddefault_library=both']
        cmd += self.mesonOpts
        cmd += [self.sourceDir]

        self.prepare_cmds = [
            (cmd, '{builddir}', 'running meson configure')
        ]
        self.prepareDumpCmds = self.prepare_cmds[:]

        # meson keeps the found dependencies when reconfiguring, look them up again (a dependency may have been rebuilt)
        if os.path.exists(self.buildDir / 'meson-info'):
            self.prepare_cmds.insert(0, ([self.mesonPath, 'configure', '--clearcache'], '{builddir}', 'clearing meson cache'))

        concurrentArgs = ['-j', '1']
        if self.parallelJobs:
            concurrentArgs = ['-j', f'{config.maxJobs}'] if config.maxJobs else []

        self.build_cmds = [
            ([self.mesonPath, 'compile'] + concurrentArgs, '{builddir}', 'building'),
            ([self.mesonPath, 'install'], '{builddir}', 'installing'),
        ]

        return BuildArtifact.prepare(self, config)


RUST_ARCHS = {
    'x86_64': 'x86_64',
    'i686': 'i686',
    'arm64': 'aarch64',
    'wasm32': 'wasm32',
}

def rustTriple(targetDistrib: str, arch: str, toolchainName: str = None) -> str:
    ''' returns the rust target triple for a distribution and an architecture
        @param targetDistrib: the target distribution (Ubuntu, Fedora, mingw, Windows, Darwin, FreeBSD, emscripten, ...)
        @param arch: the accendino architecture (x86_64, i686, arm64, wasm32)
        @param toolchainName: the toolchain, used to choose between the gnu and msvc ABIs on Windows
        @return the rust triple
    '''
    rustArch = RUST_ARCHS.get(arch, arch)
    if targetDistrib == 'emscripten':
        return 'wasm32-unknown-emscripten'
    if targetDistrib == 'mingw' or (targetDistrib == 'Windows' and toolchainName == 'mingw'):
        return f'{rustArch}-pc-windows-gnullvm' if rustArch == 'aarch64' else f'{rustArch}-pc-windows-gnu'
    if targetDistrib == 'Windows':
        return f'{rustArch}-pc-windows-msvc'
    if targetDistrib == 'Darwin':
        return f'{rustArch}-apple-darwin'
    if targetDistrib == 'FreeBSD':
        return f'{rustArch}-unknown-freebsd'
    return f'{rustArch}-unknown-linux-gnu'


class CargoBuildArtifact(BuildArtifact):
    ''' rust / cargo based build item '''

    ccacheMode = 'env'

    def __init__(self, name, deps, srcObj: Source, cargoOpts=[], features=[], noDefaultFeatures=False, capi=False, locked=False,
                 parallelJobs=True, extraEnv={}, provides=[], pkgs={}, toolchainArtifacts='c', cargoProjectDir='{srcdir}',
                 rustVersion: str = 'system', toolDeps=[], buildMachineOnly=False) -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param cargoOpts: extra arguments given to cargo install (or cargo cinstall)
            @param features: cargo features to enable
            @param noDefaultFeatures: disable the default features of the crate
            @param capi: the crate is a library exposing a C API, built and installed with cargo-c (headers, libraries
                    and pkg-config files) instead of installing its binaries with cargo install
            @param locked: build with the versions of Cargo.lock (--locked)
            @param parallelJobs: build with parallel jobs
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
            @param toolchainArtifacts: artifacts that we need from the toolchain (the C compiler is used for linking and
                    by the crates compiling C code)
            @param cargoProjectDir: directory of the Cargo.toml of the crate to build, by default the root of the sources
                    (give the directory of the crate for a workspace member)
            @param rustVersion: the rust toolchain to use: 'system' for the one of the platform packages, otherwise a rustup
                    toolchain ('stable', 'nightly', '1.85.0', ...) installed in the tools directory
            @param toolDeps: dependencies to artifacts used as tools during the build, built for the build machine when
                             cross compiling
            @param buildMachineOnly: a tool only built for the build machine, when cross compiling deps to it go to native:
        '''
        extra = {}
        if rustVersion == 'system':
            capiPkgs = ['cargo-c'] if capi else []
            extra = {
                'Ubuntu|Debian': ['cargo', 'rustc'] + capiPkgs,
                'Fedora|Redhat': ['cargo', 'rust'] + capiPkgs,
                'Arch|FreeBSD|Darwin': ['rust'] + capiPkgs,
            }
            doCrossDeps(['Ubuntu', 'Debian'], ['cargo', 'rustc'] + capiPkgs, extra)
            doCrossDeps(['Fedora', 'Redhat'], ['cargo', 'rust'] + capiPkgs, extra)

            # the rust std of the mingw targets
            for key, stdPkg in (('Fedora->mingw@x86_64', 'rust-std-static-x86_64-pc-windows-gnu'),
                                ('Fedora->mingw@i686', 'rust-std-static-i686-pc-windows-gnu'),
                                ('Ubuntu->mingw@x86_64', 'libstd-rust-dev-windows'),
                                ('Debian->mingw@x86_64', 'libstd-rust-dev-windows')):
                extra[key] = extra.get(key, []) + [stdPkg]

        pkgs = mergePkgDeps(pkgs, extra)
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs, toolchainArtifacts=toolchainArtifacts, toolDeps=toolDeps,
                               buildMachineOnly=buildMachineOnly)
        self.cargoOpts = cargoOpts
        self.features = features
        self.noDefaultFeatures = noDefaultFeatures
        self.capi = capi
        self.locked = locked
        self.parallelJobs = parallelJobs
        self.cargoProjectDir = cargoProjectDir
        self.rustVersion = rustVersion
        self.userExtraEnv = extraEnv
        # set in init() when using a rust toolchain installed with rustup
        self.rustEnv = {}

    def rustTarget(self) -> T.Optional[str]:
        ''' returns the rust target triple when cross compiling, None otherwise '''
        if not self.machine.crossCompilation:
            return None
        return rustTriple(self.machine.targetDistrib, self.machine.arch, self.machine.toolchainObj.description)

    def init(self, config) -> bool:
        if not BuildArtifact.init(self, config):
            return False

        if self.rustVersion == 'system':
            return True

        # rustup and its toolchains in the tools directory, shared by all the cargo artifacts
        rustDir = pathlib.Path(config.toolsDir, 'rust')
        cargoHome = rustDir / 'cargo'
        rustupHome = rustDir / 'rustup'
        exe = '.exe' if config.distribId == 'Windows' else ''
        rustup = cargoHome / 'bin' / f'rustup{exe}'

        env = os.environ.copy()
        env['CARGO_HOME'] = str(cargoHome)
        env['RUSTUP_HOME'] = str(rustupHome)

        if not rustup.exists():
            hostTriple = rustTriple(config.distribId, config.localArch)
            url = f'https://static.rust-lang.org/rustup/dist/{hostTriple}/rustup-init{exe}'
            os.makedirs(rustDir, exist_ok=True)
            rustupInit = rustDir / f'rustup-init{exe}'
            logging.debug(f'downloading {url}')
            try:
                urllib.request.urlretrieve(url, rustupInit)
            except Exception as e:
                logging.error(f'unable to download rustup-init from {url}: {e}')
                return False
            rustupInit.chmod(0o755)

            cmd = [str(rustupInit), '-y', '--no-modify-path', '--profile', 'minimal', '--default-toolchain', 'none']
            ok = self.runCommands([(cmd, '.', 'installing rustup')], env, config)
            rustupInit.unlink(missing_ok=True)
            if not ok:
                return False

        # rustup does nothing for an installed toolchain (except for channels like stable that get updated)
        cmds = [([str(rustup), 'toolchain', 'install', '--profile', 'minimal', '--no-self-update', self.rustVersion], '.',
                 f'installing rust {self.rustVersion}')]
        target = self.rustTarget()
        if target:
            cmds.append(([str(rustup), 'target', 'add', '--toolchain', self.rustVersion, target], '.', f'adding rust target {target}'))
        if not self.runCommands(cmds, env, config):
            return False

        self.rustEnv = {
            'CARGO_HOME': str(cargoHome),
            'RUSTUP_HOME': str(rustupHome),
            'RUSTUP_TOOLCHAIN': self.rustVersion,
            'PATH': str(cargoHome / 'bin'),
        }

        p = subprocess.run([str(rustup), 'toolchain', 'list'], env=env, stdout=subprocess.PIPE, text=True, check=False)
        config.registerTool('rust', ' '.join(line.split()[0] for line in p.stdout.splitlines() if line.strip()))
        return True

    def prepare(self, config) -> bool:
        target = self.rustTarget()

        extraEnv = dict(self.rustEnv)
        if target:
            # let the pkg-config crate find the libraries of the target
            extraEnv['PKG_CONFIG_ALLOW_CROSS'] = '1'
            # CC is the target compiler, crates compiling C code in build scripts for the build machine use HOST_CC
            if config.distribId != 'Windows':
                extraEnv.update({'HOST_CC': 'cc', 'HOST_CXX': 'c++'})
        extraEnv.update(self.userExtraEnv)
        self.extraEnv = extraEnv

        manifest = os.path.join(self.cargoProjectDir, 'Cargo.toml')
        targetOpts = ['--target', target] if target else []
        if self.locked:
            targetOpts += ['--locked']

        self.prepare_cmds = [
            (['cargo', 'fetch', '--manifest-path', manifest] + targetOpts, '{builddir}', 'fetching crates')
        ]

        profile = 'dev' if self.buildType == 'debug' else 'release'
        opts = ['--target-dir', '{builddir}/target', '--profile', profile] + targetOpts
        if self.features:
            opts += ['--features', ','.join(self.features)]
        if self.noDefaultFeatures:
            opts += ['--no-default-features']
        if not self.parallelJobs:
            opts += ['-j', '1']
        elif config.maxJobs:
            opts += ['-j', f'{config.maxJobs}']

        if self.capi:
            cmd = ['cargo', 'cinstall', '--manifest-path', manifest, '--prefix', '{prefix_posix}',
                   '--libdir', '{libdir}']
        else:
            # --force reinstalls when the sources changed without a version bump, --no-track doesn't put cargo
            # bookkeeping files in the prefix
            cmd = ['cargo', 'install', '--path', self.cargoProjectDir, '--root', '{prefix}', '--force', '--no-track']

        self.build_cmds = [
            (cmd + opts + self.cargoOpts, '{builddir}', 'building and installing')
        ]
        return BuildArtifact.prepare(self, config)
