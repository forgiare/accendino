import os
import pathlib
import shutil
import subprocess
import typing as T
import re
import urllib.parse

from zenlog import log as logging
from accendino.utils import findInPATH
from accendino.platform import accendinoPlatform


# list of the packages kept in a package cache directory, can be used as a CI cache key
PACKAGES_CACHE_MANIFEST = 'accendino-packages.txt'

class PackageManagerBase:
    ''' base package manager '''

    # the manager can keep the packages it installs in a cache directory (see setCacheDir())
    supportsCache = False

    def __init__(self, name: str=None) -> None:
        self.name = name
        self.allPackages = {}
        self.debug = True
        self.canInstall = True
        self.cacheDir: T.Optional[pathlib.Path] = None

    def setCacheDir(self, cacheDir: str) -> None:
        ''' sets the directory where the manager keeps the packages it installs, to install them again from there
            (when it is restored from a CI cache for instance). Only for the managers with supportsCache
        '''
        self.cacheDir = pathlib.Path(cacheDir)

    def writeCacheManifest(self, entries: T.List[str]) -> None:
        ''' writes the manifest of the cache directory, the list of the cached packages (one entry per line) '''
        content = ''.join(f'{e}\n' for e in entries)
        manifest = self.cacheDir / PACKAGES_CACHE_MANIFEST
        if not manifest.exists() or manifest.read_text(encoding='utf8') != content:
            manifest.write_text(content, encoding='utf8')

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        ret = []

        logging.debug(f" * {self.name}: checking required {len(packages)} package(s) on system")

        for p in packages:
            if p not in self.allPackages:
                logging.debug(f"   {p}: missing")
                ret.append(p)

        return ret

    def installPackages(self, _packages: T.List[str]) -> bool:
        logging.error(f"{self.name}, not implemented")
        return False




class DpkgManager(PackageManagerBase):
    ''' dpkg based package manager. With a cache directory the downloaded packages are kept there, and installed again
        from there without downloading them nor updating the package index
    '''

    supportsCache = True

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "dpkg")
        self.indexUpdated = False
        self._loadInstalled()
        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")

    def _loadInstalled(self) -> None:
        pack_re = re.compile(r'ii[^\w]+([^ ]+)[^\w]+([^ ]+)')
        self.allPackages = {}
        for l in subprocess.Popen(['dpkg', '-l'], stdout=subprocess.PIPE, bufsize=1024).stdout.readlines():
            matches = pack_re.match(l.decode('utf8'))
            if not matches:
                continue

            pkgName = matches.group(1)
            pos = pkgName.find(':')
            if pos != -1:
                pkgName = pkgName[0:pos]

            version = matches.group(2)
            self.allPackages[pkgName] = version

    @staticmethod
    def _runAsRoot(cmd: T.List[str]) -> bool:
        if os.getuid() != 0:
            cmd = ['sudo'] + cmd
        logging.debug(f'running {" ".join(cmd)}')
        return subprocess.run(cmd, check=False).returncode == 0

    def _aptOptions(self) -> T.List[str]:
        if not self.cacheDir:
            return []
        # the _apt user that downloads in a sandbox may not be able to write in the cache directory
        return ['-o', f'Dir::Cache::Archives={self.cacheDir}', '-o', 'APT::Keep-Downloaded-Packages=true',
                '-o', 'APT::Sandbox::User=root']

    @staticmethod
    def _debInfo(path: pathlib.Path) -> T.Optional[T.Tuple[str, str, str]]:
        ''' returns (package, version, arch) from the name of a deb file stored by apt (<pkg>_<version>_<arch>.deb with
            the version url encoded) '''
        tokens = path.stem.split('_')
        if path.suffix != '.deb' or len(tokens) != 3:
            return None
        return (tokens[0], urllib.parse.unquote(tokens[1]), tokens[2])

    def _cachedDebs(self) -> T.List[pathlib.Path]:
        ''' returns the deb files of the cache directory for packages that are not installed '''
        if not self.cacheDir or not self.cacheDir.is_dir():
            return []

        ret = []
        for f in sorted(self.cacheDir.glob('*.deb')):
            info = self._debInfo(f)
            if info and info[0] not in self.allPackages:
                ret.append(f)
        return ret

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        if self.cacheDir:
            # apt fails when its archives directory doesn't exist
            os.makedirs(self.cacheDir / 'partial', exist_ok=True)

        baseCmd = ['apt-get', 'install', '-y', '--no-install-recommends'] + self._aptOptions()
        ok = False

        debs = self._cachedDebs()
        if debs:
            # packages from the cache, installed without downloading anything so without a package index update. The
            # requested packages are given too, if one isn't in the cache this fails and we do a regular install
            logging.debug(f' * installing from the {len(debs)} packages of the cache {self.cacheDir}')
            ok = self._runAsRoot(baseCmd + ['--no-download'] + [str(f) for f in debs] + packages)
            if not ok:
                logging.info(' * unable to install from the packages cache, doing a regular install')

        if not ok:
            if self.cacheDir and not self.indexUpdated:
                if not self._runAsRoot(['apt-get', 'update']):
                    return False
                self.indexUpdated = True
            ok = self._runAsRoot(baseCmd + packages)

        if not ok:
            return False

        self._loadInstalled()
        if self.cacheDir:
            self._updateCache()
        return True

    def _installedVersions(self) -> T.Set[T.Tuple[str, str]]:
        p = subprocess.run(['dpkg-query', '-W', '-f', '${Package} ${Version}\\n'], stdout=subprocess.PIPE, text=True, check=False)
        return {tuple(l.split(' ', 1)) for l in p.stdout.splitlines() if ' ' in l}

    def _updateCache(self) -> None:
        ''' after an install: gives the cache directory back to the user (apt ran as root), removes the packages that are
            not installed (older versions...) so that the cache doesn't grow, and writes the manifest of the cache '''
        cacheDir = self.cacheDir
        if not cacheDir.is_dir():
            return

        if os.getuid() != 0:
            self._runAsRoot(['chown', '-R', f'{os.getuid()}:{os.getgid()}', str(cacheDir)])

        # apt's lock and partial download directory are not worth caching
        for f in ('lock', 'partial'):
            path = cacheDir / f
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()

        installed = self._installedVersions()
        kept = []
        for f in sorted(cacheDir.glob('*.deb')):
            info = self._debInfo(f)
            if info and (info[0], info[1]) in installed:
                kept.append(info)
            else:
                logging.debug(f' * pruning {f.name} from the packages cache')
                f.unlink()

        self.writeCacheManifest([' '.join(info) for info in kept])


class RpmManager(PackageManagerBase):
    ''' rpm based package manager '''

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "rpm")

        for l in subprocess.Popen(['rpm', '-qa', '--qf', '%{NAME} %{VERSION}\\n'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = f"dnf -y install {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0

class BrewManager(PackageManagerBase):
    ''' brew based package manager '''

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "brew")
        for l in subprocess.Popen(['brew', 'list', '--formulae', '--versions'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")


    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = f"brew install {' '.join(packages)}"
        return os.system(cmd) == 0


class InPathSubManager(PackageManagerBase):
    ''' package manager that checks for programs in PATH '''

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "inPath")
        self.canInstall = False

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        ret = []
        for p in packages:
            if findInPATH(p) is None:
                ret.append(p)

        return ret

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.error(f'InPathSubManager can\'t install {" ".join(packages)}')
        return False

class ChocoManager(PackageManagerBase):
    ''' Chocolatey based package manager '''

    def __init__(self, chocoPath: str) -> None:
        PackageManagerBase.__init__(self, "chocolatey")
        self.chocoPath = chocoPath

        for l in subprocess.Popen([chocoPath, 'list', '--no-color', '-r'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            l = l.decode('utf-8').strip()

            # output looks like:
            #     chocolatey|2.5.1
            #     nasm|2.16.3
            if not l:
                continue

            tokens = l.split('|', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = [self.chocoPath, "install", "-y"] + packages
        p = subprocess.run(cmd)
        return p.returncode == 0


class PacmanManager(PackageManagerBase):
    ''' Pacman based package manager for Arch or msys2 '''

    def __init__(self, name: str = 'pacman') -> None:
        PackageManagerBase.__init__(self, name)
        for l in self.executePipe(['pacman', '-Q']).stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")

    def executePipe(self, cmd: T.List[str]):
        logging.debug(f"executing {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1024)

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = []
        if not accendinoPlatform.isWindows:
            if os.getuid() != 0:
                cmd.append("sudo")

        cmd += ['pacman', '-S', '--noprogressbar', '--noconfirm', ' '.join(packages)]
        p = self.executePipe(cmd)
        out, _err = p.communicate()

        if p.returncode != 0:
            logging.error(f"error installing {' '.join(packages)}, errorCode={p.returncode}: {out}")
            return False

        return True


class Msys2Manager(PacmanManager):
    ''' '''
    def __init__(self, path) -> None:
        self.msysShellPath = path
        PacmanManager.__init__(self, "msys2")

    def executePipe(self, cmd: T.List[str]):
        newCmd = [self.msysShellPath, '-defterm', '-no-start', '-mingw64', '-here', '-c', " ".join(cmd)]
        return PacmanManager.executePipe(self, newCmd)

class PkgManager(PackageManagerBase):
    ''' pkg based package manager for FreeBSD '''

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "pkg")

        for l in subprocess.Popen(['pkg', 'info'], stdout=subprocess.PIPE, bufsize=1024) \
                    .stdout.readlines():
            v = l.decode('utf-8').strip().split(' ', 2)[0]
            pos = v.rfind('-')
            name = v[0:pos]
            version = v[pos+1:]
            self.allPackages[name] = version

        logging.debug(f" * ${self.name} package manager: got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = f"pkg install -y {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0

class PackageManager(PackageManagerBase):

    def __init__(self, name, managers):
        PackageManagerBase.__init__(self, name)
        self.managers = managers

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        packagesPerManager = {}
        ret = []

        for p in packages:
            alternatives = p.split('|')

            if len(alternatives) > 1:
                #
                # handle syntax with "choco/nasm|nuget/nasm2|path/nasm.exe" that would check for
                #  nasm with choco, then nasm2 with nuget and finally nasm.exe in the path
                #
                found = False
                cand = None

                for alter in alternatives:
                    tokens = alter.strip().split('/', 2)
                    if len(tokens) == 1:
                        # no sub manager set, using default
                        manager = ''
                        package = tokens[0]
                    else:
                        (manager, package) = tokens

                    managerObj = self.managers.get(manager, None)
                    if managerObj:
                        if len(managerObj.checkMissing([package])) == 0:
                            found = True
                            break
                        if managerObj.canInstall and not cand:
                            cand = alter

                if not found:
                    if cand:
                        logging.debug(f'{p} not found, pushing {cand} for installation')
                        ret.append(cand)
                    else:
                        logging.error(f'can\'t find any alternative for {p}')
                        return None

            else:
                tokens = p.strip().split('/', 2)
                if len(tokens) == 1:
                    package = tokens[0]
                    manager = ''
                else:
                    (manager, package) = tokens

                if manager in packagesPerManager:
                    packagesPerManager[manager].append(package)
                else:
                    packagesPerManager[manager] = [package]

        helpMsg = {
            '': "no default manager set",
            'choco': "some choco packages where requested but Chocolatey is not installed",
            'msys2': "some msys2 packages where requested but msys2 is not installed, perhaps try 'choco install msys2'",
        }

        for managerName, pkgs in packagesPerManager.items():
            managerObj = self.managers.get(managerName, None)
            # no sub manager set, using default
            if managerObj is None:
                msg = helpMsg.get(managerName, None)
                if msg:
                    logging.error(msg)
                else:
                    logging.error(f"no manager {managerName} set to install {pkgs}")
                return None

            toInstall = managerObj.checkMissing(pkgs)

            if toInstall and not managerObj.canInstall:
                logging.error(f"missing items for manager {managerName}, but it can't install {pkgs}")
                return None

            for p in toInstall:
                if not managerName:
                    ret.append(p)
                else:
                    ret.append(f"{managerName}/{p}")

        return ret

    def setCacheDir(self, cacheDir: str) -> None:
        ''' each sub manager able to cache packages has its own directory in cacheDir, named after the manager '''
        PackageManagerBase.setCacheDir(self, cacheDir)
        for manager in self.managers.values():
            if manager.supportsCache:
                manager.setCacheDir(self.cacheDir / manager.name)
            elif manager.canInstall:
                logging.warning(f'the {manager.name} package manager can\'t cache packages, installing without cache')

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        packagesPerManager = {}
        for p in packages:
            tokens = p.split('/', 2)
            if len(tokens) == 1:
                managerName = ''
                package = tokens[0]
            else:
                (managerName, package) = tokens

            if managerName not in self.managers:
                logging.error(f"{managerName} not registered")
                return False

            if managerName in packagesPerManager:
                packagesPerManager[managerName].append(p)
            else:
                packagesPerManager[managerName] = [ package ]


        for managerName, pkgs in packagesPerManager.items():
            visualName = managerName and managerName or 'default'
            logging.info(f'installing [{" ".join(pkgs)}] on {visualName} package manager')
            manager = self.managers[managerName]
            if not manager.installPackages(pkgs):
                return False

        return True



def getPkgManager(distribId, packagesToCheck, cacheDir: T.Optional[str] = None):
    ''' returns the package manager of the distribution
        @param distribId: the distribution
        @param packagesToCheck: packages to check, the manager may add some
        @param cacheDir: where the managers that can do it keep the packages they install (see setCacheDir())
    '''
    managers = {'path': InPathSubManager()}
    name = 'unknown'
    if distribId in ('Ubuntu', 'Debian', ):
        name = 'dpkg'
        managers[''] = DpkgManager()
    elif distribId in ('Fedora', 'RedHat', ):
        name = 'rpm'
        managers[''] = RpmManager()
    elif distribId in ('Windows',):
        name = 'windows'
        chocoPath = findInPATH("choco.exe")
        if chocoPath:
            managers['choco'] = ChocoManager(chocoPath)

        if accendinoPlatform.msys2path:
            managers['msys2'] = Msys2Manager(accendinoPlatform.msys2path)
        packagesToCheck.append('path/powershell.exe')

    elif distribId in ('Darwin',):
        name = 'brew'
        managers[''] = BrewManager()
    elif distribId in ('FreeBSD',):
        name = 'pkg'
        managers[''] = PkgManager()
    elif distribId in ('Arch',):
        name = 'pacman'
        managers[''] = PacmanManager()

    ret = PackageManager(name, managers)
    if cacheDir:
        ret.setCacheDir(cacheDir)
    return ret
