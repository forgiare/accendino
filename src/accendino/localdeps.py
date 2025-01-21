import os
import subprocess
import typing as T

from zenlog import log as logging


class PackageManager:
    ''' base package manager '''

    def __init__(self) -> None:
        self.allPackages = []
        self.debug = True

    def check(self, packages) -> T.List[str]:
        ret = []

        logging.debug(f" * checking required {len(packages)} packages on system:")

        for p in packages:
            if p not in self.allPackages:
                logging.debug(f"   {p}: KO")
                ret.append(p)
            else:
                logging.debug(f"   {p}: OK")

        return ret


class DpkgManager(PackageManager):
    ''' dpkg based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)

        for l in subprocess.Popen(['dpkg', '-l'], stdout=subprocess.PIPE, bufsize=1024).stdout.readlines():
            if not l.startswith(b'ii  '):
                continue

            pos = l.find(b' ', 4)
            pkgName = l[4:pos].decode('utf-8')

            pos = pkgName.find(':')
            if pos != -1:
                pkgName = pkgName[0:pos]
            self.allPackages.append(pkgName)

        logging.debug(f" * dpkg package manager, got {len(self.allPackages)} installed packages")

    def installPackages(self, packages) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"apt-get install -y --no-install-recommends {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0


class RpmManager(PackageManager):
    ''' rpm based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)


        for l in subprocess.Popen(['rpm', '-qa', '--qf', '%{NAME}\\n'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            self.allPackages.append(l.decode('utf-8').strip())

        logging.debug(f" * RPM package manager, got {len(self.allPackages)} installed packages")

    def installPackages(self, packages) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        cmd = f"dnf -y install {' '.join(packages)}"
        if os.getuid() != 0:
            cmd = "sudo " + cmd

        return os.system(cmd) == 0

class BrewManager(PackageManager):
    ''' brew based package manager '''

    def __init__(self) -> None:
        PackageManager.__init__(self)
        for l in subprocess.Popen(['brew', 'list', '--formulae', '-1'], stdout=subprocess.PIPE, bufsize=1024) \
                            .stdout.readlines():
            self.allPackages.append(l.decode('utf-8').strip())

        logging.debug(f" * Brew package manager, got {len(self.allPackages)} installed packages")


    def installPackages(self, packages) -> bool:
        logging.debug(f" * installing missing packages: {' '.join(packages)}")

        logging.error("not implemented")
        return False
