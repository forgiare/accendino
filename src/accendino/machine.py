#
#  Copyright (C) 2026 David Fort <contact@hardening-consulting.com>
#
''' the machine build artifacts are built for '''
import typing as T

# prefix of the names of the artifacts built for the build machine when cross compiling
NATIVE_PREFIX = 'native:'


class Machine:
    ''' A machine that build artifacts are built for. The build commands always run on the local machine
        (distribId/distribVersion), the produced binaries are for targetDistrib/arch with the given toolchain
        and are installed in prefix.
    '''

    def __init__(self, distribId: str, distribVersion: str, targetDistrib: str, arch: str, localArch: str) -> None:
        '''
            @param distribId: the local distribution, where the build runs
            @param distribVersion: version of the local distribution
            @param targetDistrib: the distribution the binaries are built for
            @param arch: the architecture the binaries are built for
            @param localArch: the architecture of the local machine
        '''
        self.distribId = distribId
        self.distribVersion = distribVersion
        self.targetDistrib = targetDistrib
        self.arch = arch
        self.crossCompilation = (distribId != targetDistrib) or (localArch != arch)
        self.libdir = 'lib64' if distribId in ('Redhat', 'Fedora',) else 'lib'

        # set once the toolchain has been created
        self.toolchainObj = None

        # set once the accendino files have been read
        self.prefix = None
        # CROSS_PLATFORM_FILE_CHOOSER of the accendino files, overrides the cross files of the toolchain
        self.crossPlatformFileChooser: T.Optional[T.Callable[[str, 'Machine'], T.Optional[str]]] = None

    def packageKeys(self) -> T.Tuple[str, str]:
        ''' returns the keys used to look up platform packages, the short one (Ubuntu, Fedora->mingw@x86_64, ...)
            and the long one with the distribution version (Ubuntu 24.04, Fedora 40->mingw@x86_64, ...)
        '''
        shortName = f"{self.distribId}"
        longName = f"{self.distribId} {self.distribVersion}"
        if self.targetDistrib != self.distribId:
            # cross compiling adjusting the searched names
            shortName += f'->{self.targetDistrib}@{self.arch}'
            longName += f'->{self.targetDistrib}@{self.arch}'
        return (shortName, longName)

    def getCrossPlatformFile(self, builder: str) -> T.Optional[str]:
        ''' returns the cross file (cmake toolchain file, meson cross file, ...) for the given builder: the one of
            crossPlatformFileChooser if it returns one, the one of the toolchain otherwise
            @param builder: the builder, cmake or meson
            @return the path of the cross file, None if there's none
        '''
        if self.crossPlatformFileChooser:
            ret = self.crossPlatformFileChooser(builder, self)
            if ret:
                return str(ret)

        return self.toolchainObj.crossFile(builder) if self.toolchainObj else None
