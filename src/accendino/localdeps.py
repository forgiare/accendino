import os
import subprocess
import typing as T
import re

from zenlog import log as logging
from accendino.utils import findInPATH


class PackageManager:
    ''' base package manager '''

    def __init__(self) -> None:
        self.allPackages = {}
        self.debug = True

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        ret = []

        logging.debug(f" * checking required {len(packages)} package(s) on system:")

        for p in packages:
            if p not in self.allPackages:
                logging.debug(f"   {p}: missing")
                ret.append(p)

        return ret

    def installPackages(self, _packages: T.List[str]) -> bool:
        logging.error("not implemented")
        return False


class DpkgManager(PackageManager):
    ''' dpkg based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)

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

        logging.debug(f" * dpkg package manager, got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"apt-get install -y --no-install-recommends {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0


class RpmManager(PackageManager):
    ''' rpm based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)


        for l in subprocess.Popen(['rpm', '-qa', '--qf', '%{NAME} %{VERSION}\\n'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * RPM package manager, got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"dnf -y install {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0

class BrewManager(PackageManager):
    ''' brew based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)
        for l in subprocess.Popen(['brew', 'list', '--formulae', '--versions'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * Brew package manager, got {len(self.allPackages)} installed packages")


    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"brew install {' '.join(packages)}"
        return os.system(cmd) == 0


class InPathSubManager(PackageManager):
    ''' package manager that checks for programs in PATH '''

    def __init__(self) -> None:
        PackageManager.__init__(self)

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
        PackageManager.__init__(self)
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

        logging.debug(f" * choco package manager, got {len(self.allPackages)} installed packages")

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"{self.chocoPath} install {' '.join(packages)}"
        return os.system(cmd) == 0


class WindowsManager(PackageManager):
    ''' windows based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)

        self.choco = None
        chocoPath = findInPATH("choco.exe")
        if chocoPath:
            self.choco = ChocoSubManager(chocoPath)

        self.inPath = InPathSubManager()

    def checkMissing(self, packages: T.List[str]) -> T.List[str]:
        chocoPkgs = []
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

                    if manager == 'choco':
                        if self.choco:
                            if len(self.choco.checkMissing([package])) == 0:
                                found = True
                                break
                            if not cand:
                                cand = alter
                    elif manager == 'path':
                        fpath = package
                        if not fpath.endswith('.exe'):
                            fpath += '.exe'

                        if findInPATH(fpath):
                            found = True
                            break
                    else:
                        logging.error(f'unknown sub package manager "{manager}"')

                if not found:
                    if cand:
                        logging.debug(f'evaluating {p} not found, pushing {cand} for installation')
                        ret.append(cand)
                    else:
                        logging.error(f'can\'t find any alternative in {p}')
                        return None

            else:
                (manager, package) = p.split('/', 2)
                if manager == 'choco':
                    chocoPkgs.append(package)
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

        if inPathPkgs:
            for p in inPathPkgs:
                if not p.endswith('.exe'):
                    p += '.exe'

                if not findInPATH(p):
                    logging.error(f'{p} not found in PATH')
                    return None

        return ret

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        chocoPkgs = []

        for p in packages:
            if p.startswith('choco/'):
                chocoPkgs.append(p[6:])

        if chocoPkgs:
            if not self.choco:
                logging.error("some choco packages where requested but Chocolatey is not installed")
                return None

            if not self.choco.installPackages(chocoPkgs):
                return False
        return False

class PacmanManager(PackageManager):
    ''' Pacman based package manager for Arch '''

    def __init__(self) -> None:
        PackageManager.__init__(self)
        for l in subprocess.Popen(['pacman', '-Q'], stdout=subprocess.PIPE, bufsize=1024) \
                    .stdout.readlines():
            tokens = l.decode('utf-8').strip().split(' ', 2)
            self.allPackages[tokens[0]] = tokens[1]

        logging.debug(f" * pacman package manager, got {len(self.allPackages)} installed packages")


    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"pacman -S {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0

class PkgManager(PackageManager):
    ''' pkg based package manager for FreeBSD '''

    def __init__(self) -> None:
        PackageManager.__init__(self)

        for l in subprocess.Popen(['pkg', 'info'], stdout=subprocess.PIPE, bufsize=1024) \
                    .stdout.readlines():
            v = l.decode('utf-8').strip().split(' ', 2)[0]
            pos = v.rfind('-')
            name = v[0:pos]
            version = v[pos+1:]
            self.allPackages[name] = version

    def installPackages(self, packages: T.List[str]) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"pkg install -y {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0
