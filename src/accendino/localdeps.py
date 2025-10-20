import os
import subprocess
import typing as T
import re

from zenlog import log as logging
from accendino.utils import findInPATH
from accendino.platform import accendinoPlatform


class PackageManagerBase:
    ''' base package manager '''

    def __init__(self, name: str=None) -> None:
        self.name = name
        self.allPackages = {}
        self.debug = True
        self.canInstall = True

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
    ''' dpkg based package manager '''

    def __init__(self) -> None:
        PackageManagerBase.__init__(self, "dpkg")

        pack_re = re.compile(r'ii[^\w]+([^ ]+)[^\w]+([^ ]+)')
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

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = f"apt-get install -y --no-install-recommends {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0


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
            if not findInPATH(p):
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

        cmd = f"{self.chocoPath} install {' '.join(packages)}"
        return os.system(cmd) == 0


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
            logging.error(f'installing [{" ".join(pkgs)}] on {visualName} package manager')
            manager = self.managers[managerName]
            if not manager.installPackages(pkgs):
                return False

        return True



def getPkgManager(distribId, packagesToCheck):
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

    return PackageManager(name, managers)
