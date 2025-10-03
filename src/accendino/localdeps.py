import os
import subprocess
import typing as T
import re

from zenlog import log as logging
from accendino.utils import findInPATH
from accendino.platform import accendinoPlatform


class PackageManager:
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


class DpkgManager(PackageManager):
    ''' dpkg based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "dpkg")

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


class RpmManager(PackageManager):
    ''' rpm based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "rpm")

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

class BrewManager(PackageManager):
    ''' brew based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "brew")
        for l in subprocess.Popen(['brew', 'list', '--formulae', '--versions'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * {self.name} package manager: got {len(self.allPackages)} installed packages")


    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        cmd = f"brew install {' '.join(packages)}"
        return os.system(cmd) == 0


class InPathSubManager(PackageManager):
    ''' package manager that checks for programs in PATH '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "inPath")
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

class ChocoSubManager(PackageManager):
    ''' Chocolatey based package manager '''

    def __init__(self, chocoPath: str) -> None:
        PackageManager.__init__(self, "chocolatey")
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


class WindowsManager(PackageManager):
    ''' windows based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "windows")

        self.choco = None
        chocoPath = findInPATH("choco.exe")
        if chocoPath:
            self.choco = ChocoSubManager(chocoPath)

        self.msys2 = None
        if accendinoPlatform.msys2path:
            self.msys2 = Msys2Manager(accendinoPlatform.msys2path)

        self.inPath = InPathSubManager()

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        chocoPkgs = []
        msys2Pkgs = []
        inPathPkgs = []

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
                    (manager, package) = alter.strip().split('/', 2)

                    targets = {
                        'choco': self.choco,
                        'msys2': self.msys2,
                        'path': self.inPath,
                    }

                    if not manager in targets:
                        logging.error(f'unknown sub package manager "{manager}"')
                        return None

                    target = targets.get(manager, None)
                    if target:
                        if len(target.checkMissing([package])) == 0:
                            found = True
                            break
                        if target.canInstall and not cand:
                            cand = alter

                if not found:
                    if cand:
                        logging.debug(f'{p} not found, pushing {cand} for installation')
                        ret.append(cand)
                    else:
                        logging.error(f'can\'t find any alternative for {p}')
                        return None

            else:
                (manager, package) = p.split('/', 2)
                if manager == 'choco':
                    chocoPkgs.append(package)
                elif manager == 'msys2':
                    msys2Pkgs.append(package)
                elif manager == 'path':
                    inPathPkgs.append(package)
                else:
                    logging.error(f'unknown sub package manager "{manager}"')
                    return None

        if chocoPkgs:
            if not self.choco:
                logging.error("some choco packages where requested but Chocolatey is not installed")
                return None

            for p in self.choco.checkMissing(chocoPkgs):
                ret.append(f'choco/{p}')

        if msys2Pkgs:
            if not self.msys2:
                logging.error("some msys2 packages where requested but msys2 is not installed, perhaps try 'choco install msys2'")
                return None

            for p in self.msys2.checkMissing(msys2Pkgs):
                ret.append(f'msys2/{p}')

        if inPathPkgs:
            for p in inPathPkgs:
                if not p.endswith('.exe'):
                    p += '.exe'

                if not findInPATH(p):
                    logging.error(f'{p} not found in PATH')
                    return None

        return ret

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * {self.name}, installing missing packages: {' '.join(packages)}")

        chocoPkgs = []
        msys2Pkgs = []

        for p in packages:
            if p.startswith('choco/'):
                chocoPkgs.append(p[6:])
            elif p.startswith('msys2/'):
                msys2Pkgs.append(p[6:])

        if chocoPkgs:
            if not self.choco:
                logging.error("some choco packages where requested but Chocolatey is not installed")
                return None

            if not self.choco.installPackages(chocoPkgs):
                return False

        if msys2Pkgs:
            if not self.msys2:
                logging.error("some msys2 packages where requested but msys2 is not installed (try 'choco install msys2' ?)")
                return None

            if not self.msys2.installPackages(msys2Pkgs):
                return False

        return True

class PacmanManager(PackageManager):
    ''' Pacman based package manager for Arch or msys2 '''

    def __init__(self, name: str = 'pacman') -> None:
        PackageManager.__init__(self, name)
        for l in self.executePipe(['pacman', '-Q']).stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * ${self.name} package manager: got {len(self.allPackages)} installed packages")

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

class PkgManager(PackageManager):
    ''' pkg based package manager for FreeBSD '''

    def __init__(self) -> None:
        PackageManager.__init__(self, "pkg")

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
