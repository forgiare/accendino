import pathlib
import subprocess
import json
import typing as T
from zenlog import log as logging
from accendino.localdeps import PackageManager
from accendino.utils import treatPackageDeps


class IToolChain:
    ''' Abstract toolchain '''

    def __init__(self, name, config):
        self.name = name
        self.description = name
        self.artifactRequires = {}
        self.config = config

    def packagesCheck(self, packageManager: PackageManager, artifacts: T.List[str], doInstall: bool) -> bool:
        '''
            checks that the toolchain have the necessary packages for the given toolchain artifacts
            @param packageManager: the manager for local package
            @param artifacts: a list of toolchain artifacts
            @param doInstall: tell if we should install missing packages
            @return if the operation was successful
        '''
        config = self.config
        shortName = f"{config.distribId}"
        longName = f"{config.distribId} {config.distribVersion}"
        if config.targetDistrib != config.distribId:
            # cross compiling adjusting the searched names
            shortName += f'->{config.targetDistrib}@{config.targetArch}'
            longName += f'->{config.targetDistrib}@{config.targetArch}'

        toCheck = []
        for artifact in artifacts:
            pkgRequires = self.artifactRequires.get(artifact)
            if pkgRequires:
                v = pkgRequires.get(longName, None)
                if v is None:
                    v = pkgRequires.get(shortName, [])
                if v:
                    toCheck += v

        toInstall = packageManager.checkMissing(toCheck)
        if len(toInstall) and doInstall:
            return packageManager.installPackages(toInstall)

        return True

    def activate(self) -> bool:
        ''' Activates the toolchain, eventually doing some setup
            @return if the operation was successful
        '''
        return True

    def prepareItems(self) -> str:
        ''' returns some content to put in scripts to activate this toolchain
            @return the string content
        '''
        return ''

KNOWN_VS_FLAVORS = ('msvc', 'clang')

class VsToolChain(IToolChain):
    ''' Toolchain using visual studio '''

    def __init__(self, config, flavor='msvc'):
        IToolChain.__init__(self, 'MsvcToolChain', config)
        self.artifactRequires = {
            'c': {
                'Windows': ['choco/vswhere|path/vswhere.exe'],
            },
            'c++': {
                'Windows': ['choco/vswhere|path/vswhere.exe'],
            },
        }
        self.installationPath = None
        self.installationName = None
        self.setvarsPath = None
        self.setvarsPs1Path = None
        self.flavor = flavor

    def activate(self) -> bool:
        config = self.config
        if self.flavor == 'msvc':
            archsEquiv = {
                "x86_64": "x86.x64",
                "arm64": "ARM64"
            }

            component = f'Microsoft.VisualStudio.Component.VC.Tools.{archsEquiv.get(config.targetArch, "x86.x64")}'
        elif self.flavor == 'clang':
            component = 'Microsoft.VisualStudio.Component.VC.Llvm.Clang'
        else:
            logging.error(f'unknown VS flavor {self.flavor}')
            return False

        cmd = ['vswhere', '-latest', '-products', '*', '-requires', component, '-utf8', '-nocolor', '-format', 'json']
        logging.debug(f' * retrieving VS config by executing {" ".join(cmd)}')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        content, _err = p.communicate()

        if p.returncode != 0:
            logging.error(f'error running vswhere, returnCode={p.returncode}')
            return False

        # returned output has an extra array struct it's like
        # [ {'instanceId': '8889553d', 'installDate': '2024-01-23T08:00:18Z', ... } ]
        #
        props = json.loads(content.decode('utf8'))[0]
        if not 'installationName' in props:
            logging.error('installationName not in vswhere output')
            return False

        self.installationName = props['installationName']

        if not 'installationPath' in props:
            logging.error('installationPath not in vswhere output')
            return False

        self.installationPath = pathlib.PurePath(props['installationPath'])
        self.setvarsPath = self.installationPath / "Common7" / "Tools" / "VsDevCmd.bat"
        self.setvarsPs1Path = self.installationPath / "Common7" / "Tools" / "Launch-VsDevShell.ps1"
        return True

    def prepareItems(self) -> str:
        VSDEVCMD_ARCHS = {
            "x86_64": "amd64",
        }

        config = self.config
        return f"& '{self.setvarsPs1Path}' -Arch {VSDEVCMD_ARCHS.get(config.targetArch, config.targetArch)} -SkipAutomaticLocation\n"


class GccToolChain(IToolChain):
    ''' Toolchain with GCC '''

    def __init__(self, config):
        IToolChain.__init__(self, 'Gcc', config)
        self.artifactRequires = {
            'c': treatPackageDeps({
                'Debian|Ubuntu|Fedora|Redhat': ['gcc'],
                'Ubuntu->mingw@i686': ['gcc-mingw-w64-i686-posix'],
                'Ubuntu->mingw@x86_64': ['gcc-mingw-w64-x86-64-posix'],
                'Fedora->mingw@i686': ['mingw32-gcc', 'mingw32-crt'],
                'Fedora->mingw@x86_64': ['mingw64-gcc', 'mingw64-crt'],
            }),
            'c++': treatPackageDeps({
                'Debian|Ubuntu': ['g++'],
                'Fedora|Redhat': ['gcc-c++'],
            })
        }


class ClangToolChain(IToolChain):
    ''' Toolchain with clang '''

    def __init__(self, config):
        IToolChain.__init__(self, 'ClangToolChain', config)
        self.artifactRequires = {
            'c': treatPackageDeps({
                'Debian|Ubuntu|Fedora|Redhat': ['clang']
            }),
            'c++': treatPackageDeps({
                'Debian|Ubuntu|Fedora|Redhat': ['clang']
            })
        }


class DefaultToolChain(IToolChain):
    ''' Toolchain that does some smart default depending '''

    def __init__(self, config):
        IToolChain.__init__(self, 'default', config)
        self.testObjs = []
        self.selectedObj = None

        if config.distribId == 'Windows':
            self.testObjs.append(VsToolChain(config, 'msvc'))
        else:
            self.testObjs.append(GccToolChain(config))
            self.testObjs.append(ClangToolChain(config))

    def packagesCheck(self, packageManager: PackageManager, artifacts: T.List[str], doInstall: bool) -> bool:
        logging.debug(' * autodetecting with default toolchain manager')
        for o in self.testObjs:
            logging.debug(f' * testing artifacts=[{", ".join(artifacts)}] against toolchain {o.name}')
            if o.packagesCheck(packageManager, artifacts, doInstall):
                logging.debug(f' * using {o.name} toolchain')
                self.selectedObj = o
                self.description = o.name
                return True
        return False

    def activate(self) -> bool:
        return self.selectedObj.activate()

    def prepareItems(self) -> str:
        return self.selectedObj.prepareItems()


TOOLCHAINS = {
    'default': DefaultToolChain,
    'gcc': GccToolChain,
    'clang': ClangToolChain,
    'vs': VsToolChain,
    'none': IToolChain,
}

def getToolchain(name: str, config):
    ret = None
    if name in TOOLCHAINS:
        ctor = TOOLCHAINS[name]
        ret = ctor(config)

    elif name.startswith('vs/'):
        flavor = name[3:]
        ret = VsToolChain(config, flavor)

    return ret
