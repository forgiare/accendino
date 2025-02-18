import os
import subprocess
import pickle
import pathlib
import typing as T

from zenlog import log as logging
from accendino.sources import Source
from accendino.utils import mergePkgDeps, treatPackageDeps, doMingwCrossDeps


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
BUILT_FILE = 'accentino.built'

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
        self.builtFile = None

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

    def _createEnvFileWin32(self, env: T.Dict[str, str], keys: T.List[str]) -> None:
        with open(self.buildDir / 'setEnv.ps1', 'wt', encoding='utf8') as f:
            f.write(f'# environment variables for artifact {self.name}\n')
            for k in keys:
                f.write(f'$env:{k} = "{env[k]}"\n')


    def _computeEnv(self, config, extra: T.Dict[str, str], createEnvFile: bool=False) -> T.Dict[str, str]:
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

        return r

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
                path = self._expandConfigInString(path, config)

                completedProc = subprocess.run(cmd, env=env, cwd=path, stdout=flog, stderr=flog)
                if completedProc.returncode != 0:
                    self.showLogs(f"error {cmddoc} with {' '.join(cmd)}:")
                    return False

        return True

    def _createPrepareFileUnix(self, config) -> None:
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

    def _createPrepareFileWin32(self, config) -> None:
        with open(self.buildDir / "prepare.bat", "wt", encoding='utf8') as f:
            f.write(f'rem\nrem prepare commands for artifact {self.name}\nrem\n\n')
            lastDir = None
            for cmd, path, cmddoc in self.prepare_cmds:
                f.write(f'rem {cmddoc}\n')

                path = self._expandConfigInString(path, config)
                if lastDir != path:
                    f.write(f'cd "{path}"\n')

                cmd = self._expandConfigInlist(cmd, config)
                f.write(f'{" ".join(cmd)}\n\n')

                lastDir = path

    def prepare(self, config) -> bool:
        os.makedirs(self.buildDir, exist_ok=True)

        env = self._computeEnv(config, self.extraEnv, config.debug)

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

        if config.debug:
            scriptBuilder = self._createPrepareFileWin32 if config.distribId in ('Windows',) else self._createPrepareFileUnix
            scriptBuilder(config)

        if self.runCommands(self.prepare_cmds, env, config):
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

    def build(self, config) -> bool:
        if os.path.isfile(self.builtFile):
            logging.debug(f'artifact {self.name} already built')
            return True

        env = self._computeEnv(config, self.extraEnv)
        return self.runCommands(self.build_cmds, env, config) and self.createBuiltFile()


    def setMakeNinjaCommands(self, config, cmd='ninja', build_target='all', install_target='install', parallelJobs=True,
                            runInstallDir='{builddir}') -> None:
        ''' configure build commands base on make or ninja '''
        if cmd in ('ninja', 'make',):
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
        elif cmd in ('nmake',):
            self.build_cmds = [
                ([cmd, build_target], '{builddir}', 'building'),
                ([cmd, install_target], '{builddir}', 'installing'),
            ]


class CustomCommandBuildArtifact(BuildArtifact):
    ''' an artifact that have is configured with a special command '''

    def __init__(self, name: str, deps, srcObj: Source, extraEnv={}, provides: T.List[str] = [], pkgs={}, prepare_src_cmds=[], prepare_cmds=[],
                 builder='make', build_target='all', install_target='install') -> None:
        '''
            @param name: name of the build artifact
            @param deps: list of dependencies to other build artifacts
            @param srcObj: Source object for checking out code
            @param extraEnv: extra environment variable to use when running commands
            @param provides: list of provided build artifacts
            @param pkgs: required platform packages
        '''
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv=extraEnv, provides=provides, pkgs=pkgs)

        self.builder = builder
        self.build_target = build_target
        self.install_target = install_target

        for cmd in prepare_src_cmds:
            self.prepare_cmds.append((cmd, '{srcdir}', f'preparing sources {name}'))

        for cmd in prepare_cmds:
            self.prepare_cmds.append((cmd, '{builddir}', f'preparing build tree {name}'))


    def prepare(self, config) -> bool:
        self.setMakeNinjaCommands(config, self.builder, parallelJobs=self.parallelJobs, build_target=self.build_target,
                                  install_target=self.install_target)
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
        extra = {
            'Ubuntu|Debian|Redhat|Fedora|Arch|FreeBSD|Darwin': ['cmake']
        }
        doMingwCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], ['cmake', 'ninja-build'], extra)
        pkgs = mergePkgDeps(pkgs, extra)

        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)
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
            'Redhat|Fedora': ['qt5-qtbase-devel'],
            'FreeBSD': ['qt5-qmake'],
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
            'Arch|Darwin|FreeBSD': ['autoconf', 'automake', 'libtool'],
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
        extra = {
            'Ubuntu|Debian|Redhat|Fedora': ['meson', 'ninja-build'],
            'Arch|FreeBSD|Darwin': ['meson', 'ninja'],
        }
        doMingwCrossDeps(['Ubuntu', 'Debian', 'Redhat', 'Fedora'], ['meson', 'ninja-build'], extra)

        pkgs = mergePkgDeps(pkgs, extra)
        BuildArtifact.__init__(self, name, deps, srcObj, extraEnv, provides, pkgs)
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
