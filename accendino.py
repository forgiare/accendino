#! /usr/bin/env python3
import sys
import getopt
import subprocess
import os.path
import platform


class DepsBuildItem(object):
    ''' build item only for dependencies '''
    
    def __init__(self, name, deps, provides=[]):
        self.name = name
        self.deps = deps
        self.provides = provides
        self.pkgDeps = None
    
    def checkout(self, _config):
        return True
    
    def prepare(self, _config):
        return True
    
    def build(self, _config):
        return True
    
    def __str__(self):
        return "<{0}>".format(self.name)


class MakeBasedItem(object):
    ''' a make based package '''
    
    def __init__(self, parallelJobs=True, runInstallDir=None):
        self.parallelJobs = parallelJobs
        self.odir = None
        self.runInstallDir = runInstallDir
        
    def build(self, config):
        cmd = ['make', '-C', self.odir, "all"]
        if self.parallelJobs:
            cmd += ['-j4']
        
        env = self._computeEnv(config, self.extraEnv)
        completedProc = subprocess.run(cmd, env=env)
        if completedProc.returncode != 0:
            print("error compiling")
            return False

        installDir = self.odir
        if self.runInstallDir:
            installDir = os.path.join(self.odir, self.runInstallDir)
        
        cmd = ['make', '-C', installDir, "install"]
        if self.parallelJobs:
            cmd += ['-j4']
        completedProc = subprocess.run(cmd, env=env)
        return completedProc.returncode == 0


class NinjaBasedItem(object):
    ''' a ninja based package '''

    def __init__(self, parallelJobs=True, runInstallDir=None):
        self.parallelJobs = parallelJobs
        self.odir = None
        self.runInstallDir = runInstallDir

    def build(self, config):
        cmd = ['ninja', '-C', self.odir]
        if not self.parallelJobs:
            cmd += ['-j1']

        env = self._computeEnv(config, self.extraEnv)
        completedProc = subprocess.run(cmd, env=env)
        if completedProc.returncode != 0:
            print("error compiling")
            return False

        installDir = self.odir
        if self.runInstallDir:
            installDir = os.path.join(self.odir, self.runInstallDir)

        cmd = ['ninja', '-C', installDir, "install"]
        if not self.parallelJobs:
            cmd += ['-j1']
        completedProc = subprocess.run(cmd, env=env)
        return completedProc.returncode == 0

        
        
class BuildItem(DepsBuildItem):
    ''' general build item '''
    
    def __init__(self, name, deps, gitUri, extraEnv={}, provides=[]):
        DepsBuildItem.__init__(self, name, deps, provides)
        self.gitUri = gitUri
        self.sourceDir = None
        self.buildDir = None
        self.extraEnv = extraEnv
    
    def _ensureWorkDir(self, config):
        self.sourceDir = os.path.join(config.workDir, self.name)
        self.buildDir = os.path.join(config.workDir, self.sourceDir, "build-{0}".format(config.buildType))
        if os.path.exists(self.sourceDir):
            if config.debug:
                print("   ==> refreshing git dir {0}".format(self.buildDir))
            #cmd = ['git', 'pull']
            return True
        else:
            if config.debug:
                print("   ==> checking out repo in {0}".format(self.buildDir))
            cmd = ['git', 'clone', self.gitUri[0], '-b', self.gitUri[1], self.sourceDir]
        retCode = os.system(' '.join(cmd))
        return retCode == 0
    
    def _computeEnv(self, config, extra):
        r = os.environ.copy()
        for k, v in extra.items():
            r[k] = v.format(prefix=config.prefix, libdir=config.libdir)
        return r
    
    def _expandConfigInlist(self, l, config):
        ret = []
        for item in l:
            ret.append(item.format(prefix=config.prefix, libdir=config.libdir))
        return ret
        
    def checkout(self, config):
        return self._ensureWorkDir(config)
    


class CMakeBuildItem(MakeBasedItem, BuildItem):
    ''' cmake based build item '''
    
    def __init__(self, name, deps, gitUri, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[]):
        BuildItem.__init__(self, name, deps, gitUri, extraEnv, provides)
        MakeBasedItem.__init__(self, parallelJobs)
        self.cmakeOpts = cmakeOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config):
        self.odir = self.buildDir

        os.makedirs(self.odir, exist_ok=True)
        os.chdir(self.odir)
        
        cmd = ['cmake', 
               '-DCMAKE_INSTALL_PREFIX={prefix}', 
               '-DCMAKE_PREFIX_PATH={prefix}',
               '-DCMAKE_BUILD_TYPE={0}'.format(config.cmakeBuildType()),
        ]  

        cmd += self.cmakeOpts
        cmd += [self.sourceDir]
        
        cmd = self._expandConfigInlist(cmd, config)
        env = self._computeEnv(config, self.extraEnv)
        completedProc = subprocess.run(cmd, env=env)
        return completedProc.returncode == 0
    


class QMakeBuildItem(MakeBasedItem, BuildItem):
    ''' qmake based build item '''
    
    def __init__(self, name, deps, gitUri, extraEnv={}, provides=[]):
        BuildItem.__init__(self, name, deps, gitUri, extraEnv, provides)
        MakeBasedItem.__init__(self, True)
        self.extraEnv = extraEnv

    def prepare(self, config):
        self.odir = self.buildDir

        os.makedirs(self.odir, exist_ok=True)
        os.chdir(self.odir)
        
        cmd = []
        qtChooser = config.distribId in ['Ubuntu', 'Debian']
        if qtChooser:
            cmd = ['qtchooser', '-qt=qt5', '--run-tool=qmake']
        else:
            cmd = ['qmake-qt5']

        cmd += [
            'ADDITIONAL_RPATHS={prefix}/{libdir}/',
            'PREFIX={prefix}'
        ]
        
        cmd += [self.sourceDir]
        
        env = self._computeEnv(config, self.extraEnv)
        cmd = self._expandConfigInlist(cmd, config)
          
        completedProc = subprocess.run(cmd, env=env)
        return completedProc.returncode == 0
    


class AutogenBuildItem(MakeBasedItem, BuildItem):
    ''' autotools/autogen.sh based build item '''
    
    def __init__(self, name, deps, gitUri, autogenArgs=[], noconfigure=False, isAutogen=True, configureArgs=[], runInstallDir=None, extraEnv={}, provides=[]):
        BuildItem.__init__(self, name, deps, gitUri, extraEnv, provides)
        MakeBasedItem.__init__(self, True, runInstallDir)
        
        self.isAutogen = isAutogen
        self.autogenArgs = autogenArgs
        self.noconfigure = noconfigure
        self.configureArgs = configureArgs
        self.extraEnv = extraEnv

    def prepare(self, config):
        self.odir = self.buildDir

        os.makedirs(self.odir, exist_ok=True)
        os.chdir(self.odir)
        
        if self.isAutogen:
            cmd = [os.path.join(self.sourceDir, "autogen.sh")] + self.autogenArgs
        else:
            cmd = [os.path.join(self.sourceDir, "bootstrap.sh")]

        if self.noconfigure:
            cmd += ["--prefix={prefix}"]

        cmd = self._expandConfigInlist(cmd, config)
                
        env = self._computeEnv(config, self.extraEnv)
        autoGenRunDir = self.noconfigure and self.buildDir or self.sourceDir
        completedProc = subprocess.run(cmd, env=env, cwd=autoGenRunDir)
        if completedProc.returncode != 0:
            print(" * error running autogen.sh")
            return False
        
        if not self.noconfigure:
            cmd = ["../configure", "--prefix={prefix}"] + self.configureArgs
            cmd = self._expandConfigInlist(cmd, config)

            completedProc = subprocess.run(cmd, env=env)
            if completedProc.returncode != 0:
                print(" * error running configure")
                return False
        
        return True


class MesonBuildItem(NinjaBasedItem, BuildItem):
    ''' meson + ninja based build item '''

    def __init__(self, name, deps, gitUri, mesonOpts=[], parallelJobs=True, extraEnv={}, provides=[]):
        BuildItem.__init__(self, name, deps, gitUri, extraEnv, provides)
        MakeBasedItem.__init__(self, parallelJobs)
        self.mesonOpts = mesonOpts
        self.parallelJobs = parallelJobs

    def prepare(self, config):
        self.odir = self.buildDir

        reconfigure = True
        if not os.path.exists(self.odir):
            os.makedirs(self.odir, exist_ok=True)
            reconfigure = False

        os.chdir(self.odir)

        cmd = ['meson',
               '-Dprefix={prefix}',
               '-Dbuildtype={0}'.format(config.mesonBuildType()),
        ]

        if reconfigure:
            cmd += ["--reconfigure"]
        cmd += self.mesonOpts
        cmd += [self.sourceDir]

        cmd = self._expandConfigInlist(cmd, config)
        env = self._computeEnv(config, self.extraEnv)
        completedProc = subprocess.run(cmd, env=env)
        return completedProc.returncode == 0


class PackageManager(object):
    
    def __init__(self, debug=False):
        self.allPackages = []
        self.debug = debug

    def check(self, packages):
        ret = []
        
        if self.debug:
            print(" * checking required {0} packages on system:".format(len(packages)))
            
        for p in packages:
            if p not in self.allPackages:
                if self.debug:
                    print("   {0}: KO".format(p))
                ret.append(p)
            else:
                if self.debug:
                    print("   {0}: OK".format(p))

        return ret

        
class DpkgManager(PackageManager):
    ''' '''
    
    def __init__(self, debug=False):
        PackageManager.__init__(self, debug)
        
        for l in subprocess.Popen(['dpkg', '-l'], stdout=subprocess.PIPE, bufsize=1024).stdout.readlines():
            if not l.startswith(b'ii  '):
                continue
            
            pos = l.find(b' ', 4)
            pkgName = l[4:pos].decode('utf-8')
            
            pos = pkgName.find(':')
            if pos != -1:
                pkgName = pkgName[0:pos]
            self.allPackages.append(pkgName)

        if self.debug:
            print (" * dpkg package manager, got {0} installed packages".format(len(self.allPackages)))
    
    def installPackages(self, packages):
        if self.debug:
            print(" * installing missing packages: {0}".format(" ".join(packages)))
        
        cmd = "apt-get install -y --no-install-recommends {0}".format(" ".join(packages))
        if os.getuid() != 0:
            cmd = "sudo " + cmd
        
        return os.system(cmd) == 0
            

class RpmManager(PackageManager):
    def __init__(self, debug=False):
        PackageManager.__init__(self, debug)

        for l in subprocess.Popen(['rpm', '-qa', '--qf', '%{NAME}\\n'], stdout=subprocess.PIPE, bufsize=1024).stdout.readlines():
            self.allPackages.append(l.decode('utf-8').strip())
        
        if self.debug:
            print (" * RPM package manager, got {0} installed packages".format(len(self.allPackages)))

    def installPackages(self, packages):
        if self.debug:
            print(" * installing missing packages: {0}".format(" ".join(packages)))
        
        cmd = "dnf -y install {0}".format(" ".join(packages))
        if os.getuid() != 0:
            cmd = "sudo " + cmd
        
        return os.system(cmd) == 0
    

def doHelp(args, isError):
    print("usage: {0} [--help] [--prefix=<prefix>] [--debug] [--targets=<targets>] [--build-type=<type>]".format(args[0]))
    print("\t--help: shows this help")
    print("\t--debug: show verbose information of building")
    print("\t--prefix=<prefix>: where to install ogon")
    print("\t--targets=<targets>: a list of comma separated targets to build (by default full-ogon-freerdp2)")
    print("\t--build-type=[release|debug]: type of build (defaults to release)")
    print("\t--sources=<path>: a path to a file containing Accendino definitions")
    if isError:
        return 1

    return 0

def detectPlatform(debug):
    distribId = None
    distribVersion = None

    # try reading LSB file
    try:
        for l in open("/etc/lsb-release", "r").readlines():
            pos = l.find("DISTRIB_ID=")
            if pos == 0:
                distribId = l[len('DISTRIB_ID='):-1]
                continue
            
            pos = l.find('DISTRIB_RELEASE=')
            if pos == 0:
                distribVersion = l[len('DISTRIB_RELEASE='):-1]
                continue
        
        return (distribId, distribVersion)
    except:
        if debug:
            print(" * failed to detect platform using /etc/lsb-release")
    
    # Debian based systems
    try:
        content = open("/etc/debian_version", "r").readline()
        distribId = "Debian"
        tokens = content.split('.', 2)
        distribVersion = "{0:02d}.{0:02d}".format(int(tokens[0]), int(tokens[1]))
        return (distribId, distribVersion)
    except:
        if debug:
            print(" * failed reading /etc/debian_version")
    
    # Fedora based systems       
    try:
        content = open("/etc/fedora-release", "r").readline()
        distribId = "Fedora"
        tokens = content.split(' ', 4)
        distribVersion = tokens[2]
        return (distribId, distribVersion)  
    except:
        if debug:
            print(" * failed reading /etc/fedora-version")
            
    return (distribId, distribVersion) 

def pkgItemsCopy(dest, targetName, srcName):
    for distrib, items in ITEMS_PKG.items():
        if srcName in items:
            if not distrib in dest:
                dest[distrib] = {}
            dest[distrib][targetName] = items[srcName]


BUILD_TYPES = ('release', 'debug',)

FREERDP_opts=['-DWITH_SERVER=ON', '-DWITH_GSTREAMER_1_0=ON', '-DCHANNEL_URBDRC=OFF']
OGON_opts=['-DWITH_OPENH264=on']
EXTRA_ENV={'PKG_CONFIG_PATH': '{prefix}/{libdir}/pkgconfig/:{prefix}/lib/x86_64-linux-gnu/pkgconfig/'}
XOGON_ENV=EXTRA_ENV.copy()
XOGON_ENV.update({'NOCONFIGURE': '10'})
PA_ENV=EXTRA_ENV.copy()
PA_ENV.update({'NOCONFIGURE': 'YES'})


freerdp_ubuntu_debian_base = ['git', 'build-essential', 'cmake']
freerdp_ubuntu_debian_common = ['xsltproc', 'libssl-dev', 'libx11-dev', 'libxext-dev', 'libxinerama-dev', 'libxcursor-dev', 
              'libxdamage-dev', 'libxv-dev', 'libxkbfile-dev', 'libasound2-dev', 'libcups2-dev', 'libxml2', 
              'libxml2-dev', 'libxrandr-dev', 'libgstreamer1.0-dev', 'libgstreamer-plugins-base1.0-dev', 
              'libxi-dev', 'libgstreamer-plugins-base1.0-dev']
ogon_ubuntu_debian_base=['libprotobuf-dev', 'libprotoc-dev', 'protobuf-compiler', 'protobuf-c-compiler',
    'libpam0g-dev', 'libboost-dev', 'libdbus-1-dev', 'automake', 'libpam-systemd', 'ca-certificates',
    'ssl-cert']
xogon_ubuntu_debian_base=['autoconf', 'automake', 'xutils-dev', 'libtool', 'libpixman-1-dev', 'x11proto-bigreqs-dev', 'x11proto-composite-dev',
    'x11proto-dri3-dev', 'x11proto-present-dev', 'x11proto-resource-dev', 'x11proto-scrnsaver-dev', 'x11proto-fonts-dev', 
    'x11proto-xf86dri-dev', 'x11proto-xcmisc-dev', 'x11proto-record-dev', 'xfonts-utils', 'x11-xkb-utils']
xogon_fedora_base = ['autoconf', 'automake', 'libtool', 'pixman-devel', 'libXcomposite-devel', 'libXpresent-devel',
                     'libXres-devel', 'libXScrnSaver-devel', 'xorg-x11-xtrans-devel', 'xorg-x11-server-devel',
                     'xorg-x11-font-utils', 'libXfont-devel', 'xorg-x11-xkb-utils', 'libxshmfence-devel',
                     'mesa-dri-drivers']


freerdp_fedora_redhat_base = ['ninja-build', 'cups-devel', 'dbus-glib-devel', 'dbus-devel', 'systemd-devel',
  'libuuid-devel', 'pulseaudio-libs-devel', 'gcc-c++', 'libXrandr-devel', 'gsm-devel', 'gcc', 'cmake', 
  'openssl-devel', 'libX11-devel', 'libXext-devel', 'libXinerama-devel', 'libXcursor-devel',
  'libXi-devel', 'libXdamage-devel', 'libXv-devel', 'libxkbfile-devel', 'alsa-lib-devel', 
   'glib2-devel', 'libusb-devel']

ITEMS_PKG = {
    'Ubuntu 16.04': {
        'ogon': ogon_ubuntu_debian_base + ['libprotobuf-c-dev'],
    },
    
    'Ubuntu 18.04': {
        'ogon': ogon_ubuntu_debian_base + ['libprotobuf-c-dev'],
    },

    'Ubuntu': {
        'freerdp2': freerdp_ubuntu_debian_base + freerdp_ubuntu_debian_common,
        'ogon': ogon_ubuntu_debian_base + ['libprotobuf-c-dev'],
        'ogon-apps': ['qtbase5-dev', 'qt5-default', 'qttools5-dev', 'qttools5-dev-tools'],
        'ogon-qt-platform':['libxkbcommon-dev', 'libfontconfig1-dev', 'libmtdev-dev', 'libudev-dev', 'libegl1-mesa-dev', 'qt5-qmake', 'qtbase5-private-dev'],
        'ogon-xserver': xogon_ubuntu_debian_base,
        'libxfont': xogon_ubuntu_debian_base + ['libfontenc-dev'],
        'ogon-channels': ['libfuse-dev'],
        'ogon-pulseaudio': ['libsm-dev', 'libxtst-dev', 'libx11-xcb-dev', 'intltool', 'autopoint', 'libltdl-dev',
                            'libcap-dev', 'libjson-c-dev', 'libsndfile1-dev'],
    },

    'Fedora': {
        'freerdp2': freerdp_fedora_redhat_base,        
        'ogon': ['protobuf-devel', 'protobuf-compiler', 'protobuf-c-devel', 'pam-devel', 'boost-devel', 'dbus-devel', 'patch', 'curl', 'unzip'],
        'ogon-apps': ['qt5-qttools-devel'],
        'ogon-qt-platform':['libxkbcommon-devel', 'fontconfig-devel', 'redhat-rpm-config', 'mesa-libgbm-devel', 'wine-fonts', 
                                     'qt5-qtbase-static', 'qt5-qtbase-devel', 'qt5-qtbase-private-devel'],
        'ogon-xserver': xogon_fedora_base + ['intltoolize', 'libXxf86misc-devel'],
        #'libxfont': xogon_ubuntu_debian_base,
        'ogon-channels': ['fuse-devel'],
        'ogon-pulseaudio': ['libSM-devel', 'libXtst-devel', 'libxcb-devel', 'intltool', 'libtool-ltdl-devel',
                            'libcap-devel', 'json-c-devel', 'libsndfile-devel'],
    },

    'Fedora 33': {
        'ogon-xserver': xogon_fedora_base + ['intltool', 'libXxf86misc'],
    }
}
ITEMS_PKG['Debian'] = ITEMS_PKG['Ubuntu']
ITEMS_PKG['RedHat'] = ITEMS_PKG['Fedora']


BUILD_ITEMS = [
    CMakeBuildItem('freerdp2', [], ('https://github.com/FreeRDP/FreeRDP.git', 'stable-2.0'), FREERDP_opts, provides='freerdp'),
    CMakeBuildItem('ogon', ['freerdp'], ('https://github.com/ogon-project/ogon.git', 'master'), OGON_opts, parallelJobs=False),
    CMakeBuildItem('ogon-apps', ['ogon'], ('https://github.com/ogon-project/ogon-apps.git', 'master')),
    QMakeBuildItem('ogon-qt-platform', ['ogon-apps'], ('https://github.com/ogon-project/ogon-platform-qt.git', 'master'), EXTRA_ENV),
    CMakeBuildItem('ogon-greeter', ['ogon-qt-platform', 'ogon'], ('https://github.com/ogon-project/ogon-greeter-qt.git', 'master')),
    
    AutogenBuildItem('libxfont', [], ('https://gitlab.freedesktop.org/xorg/lib/libxfont.git', 'libXfont-1.5-branch'), noconfigure=True),
    
    AutogenBuildItem('ogon-xserver', ['ogon'], ('https://github.com/ogon-project/xserver-ogon.git', 'master'),  
        extraEnv=XOGON_ENV, runInstallDir='hw/xogon',
        configureArgs=['--disable-xfree86-utils', '--disable-linux-acpi', '--disable-linux-apm', '--disable-xorg', '--disable-xvfb',
                       '--disable-xquartz', '--disable-standalone-xpbproxy', '--disable-xwin', '--disable-glamor', '--disable-kdrive',
                       '--disable-xephyr', '--disable-xfake', '--disable-xfbdev', '--disable-kdrive-kbd', '--disable-kdrive-mouse',
                       '--disable-kdrive-evdev', '--with-vendor-web="http://www.ogon-project.com"', '--disable-xquartz', '--disable-xnest',
                       '--disable-xorg', '--enable-xogon', '--disable-xwayland', '--with-xkb-output=/usr/share/X11/xkb/compiled',
                       '--with-xkb-path=/usr/share/X11/xkb', '--with-xkb-bin-directory=/usr/bin/', 
                       'LDFLAGS=-Wl,-rpath={prefix}/{libdir}:{prefix}/lib/x86_64-linux-gnu/']),
    
    CMakeBuildItem('ogon-channels', ['ogon'], ('https://github.com/ogon-project/ogon-channels', 'master')),
    AutogenBuildItem('ogon-pulseaudio', ['ogon'], ('https://github.com/ogon-project/pulseaudio-ogon', 'master'),
        isAutogen=False, extraEnv=PA_ENV,
        configureArgs=['--disable-oss-output', '--enable-oss-wrapper', '--disable-alsa', '--disable-jack', '--disable-xen',
                       '--disable-tests', '--disable-udev', '--enable-ogon', '--disable-glib2', '--disable-avahi',
                       '--disable-ipv6', '--disable-openssl', '--enable-x11', '--disable-systemd-journal', '--disable-systemd-daemon',
                       'LDFLAGS=-Wl,-rpath={prefix}/{libdir}:{prefix}/lib/x86_64-linux-gnu/'],
                     ),
    DepsBuildItem('full-ogon-freerdp2', ['freerdp2', 'ogon-greeter', 'ogon-xserver', 'ogon-channels', 'ogon-pulseaudio']),
]

class AccendinoConfig(object):
    ''' Accendino configuration '''

    def __init__(self):
        self.prefix = '/opt/ogon'
        self.debug = False
        self.buildType = 'release'
        self.workDir = os.path.join(os.getcwd(), 'work')
        self.targets = ['full-ogon-freerdp2']
        self.buildDefs = BUILD_ITEMS
        self.pkgDefs = ITEMS_PKG
        self.distribId = None
        self.distribVersion = None
        self.libdir = 'lib'

    def cmakeBuildType(self):
        if self.buildType == 'release':
            return 'Release'
        elif self.buildType == 'debug':
            return 'Debug'
        raise Exception("{0} build type not supported for cmake".format(self.buildType))

    def mesonBuildType(self):
        if self.buildType in ['release', 'debug']:
            return self.buildType
        raise Exception("{0} build type not supported for meson".format(self.buildType))

    def getBuildItem(self, name):
        for item in self.buildDefs:
            if item.name == name:
                return item
        return None

    def setPlatform(self, distribId, distribVersion):
        # do some internal dependency adjustments
        if distribId == 'Ubuntu' and distribVersion >= "16.04":
            # add custom libxfont to ogon-xserver when it's Ubuntu >= 16.04
            for item in self.buildDefs:
                if item.name.find('ogon-xserver') == 0:
                    item.deps.append("libxfont")

        self.distribId = distribId
        self.distribVersion = distribVersion
        
        if self.distribId in ['Redhat', 'Fedora']:
            self.libdir = 'lib64'

    def treatPlatformPackages(self, buildItems):
        # let's compute platform package requirements
        fullName = self.distribId + " " + self.distribVersion
        exactPkgs = self.pkgDefs.get(fullName, {})
        distribPkgs = self.pkgDefs.get(self.distribId, {})
        packagesToCheck = []
        for item in buildItems:
            if isinstance(item, str):
                continue
            if item.name in exactPkgs:
                pkgs = exactPkgs[item.name]
            elif item.name in distribPkgs:
                pkgs = distribPkgs[item.name]
            else:
                if self.debug:
                    print(" * warning, {0} has no package dependency".format(item.name))
                continue

            packagesToCheck += pkgs
            item.pkgDeps = pkgs

        if self.distribId in ['Ubuntu', 'Debian']:
            pkgManager = DpkgManager(self.debug)
        elif self.distribId in ['Fedora', 'RedHat']:
            pkgManager = RpmManager(self.debug)

        toInstall = pkgManager.check(packagesToCheck)
        if len(toInstall):
            if not pkgManager.installPackages(toInstall):
                print (" * error during package installation")
                sys.exit(4)

    def createBuildPlan(self, itemsToBuild, buildPlan):
        def isInBuildPlan(plan, name):
            for i in plan:
                if isinstance(i, str):
                    if i == name:
                        return True
                    continue
                
                if i.name == name:
                    return True
            return False
            
        for item in itemsToBuild:
            if isInBuildPlan(buildPlan, item.name):
                continue

            depsToBuild = []
            for dep in item.deps:
                depItem = self.getBuildItem(dep)
                if depItem:
                    depsToBuild.append(depItem)
                else:
                    if self.debug:
                        print("unable to find build dependency {0}".format(dep))
            self.createBuildPlan(depsToBuild, buildPlan)
            buildPlan.append(item)

            if item.provides:
                if isinstance(item.provides, str):
                    buildPlan.append(item.provides)
                else:
                    buildPlan += item.provides

    def readSources(self, fname):
        fileConfig = {}
        with open(fname, "r") as f:
            code = compile(f.read(), os.path.basename(fname), "exec")
            exec(code, {}, fileConfig)
    
        self.buildDefs += fileConfig.get('BUILD_ITEMS', [])

        for dist, distValue in fileConfig.get('ITEMS_PKG', {}).items():
            if dist not in self.pkgDefs:
                self.pkgDefs[dist] = {}

            for builditem, deps in distValue.items():
                self.pkgDefs[dist][builditem] = deps
                
        defaultTargets = fileConfig.get('DEFAULT_TARGETS', None)
        if defaultTargets:
            self.targets = defaultTargets.split(",")


     
def main(args):
    print("=== accendino OGON installer ===")
    config = AccendinoConfig()
    
    def debugLog(v):
        if config.debug:
            print(v)
        
    opts, _extraArgs = getopt.getopt(args[1:], "hd", ["prefix=", "help", "debug", "targets=", "build-type=", "sources="])
    for option, value in opts:
        if option in ('-h', '--help',):
            return doHelp()
        elif option in ('--prefix',):
            config.prefix = value
        elif option in ('-d', '--debug',):
            config.debug = True
        elif option in ('--build-type',):
            config.buildType = value
            if config.buildType not in BUILD_TYPES:
                print("invalid build type {0}".format(config.buildType))
                return doHelp(args, True)
        elif option in ('--targets',):
            config.targets = value.split(',')
        elif option in ('--sources',):
            config.readSources(value)
            
    
    if not os.path.exists(config.prefix):
        debugLog(" * creating root directory {0}".format(config.prefix))
        os.makedirs(config.prefix)
    else:
        debugLog(" * root directory {0} already exists".format(config.prefix))
    
    if not os.path.isdir(config.prefix):
        print("prefix {0} is not a directory".format(config.prefix))
        return 1
    
    (distribId, distribVersion) = detectPlatform(config.debug)
    debugLog(" * target installation: {0} {1}".format(distribId, distribVersion))
    
    buildList = []
    for t in config.targets:
        buildList.append( config.getBuildItem(t) )

    config.setPlatform(distribId, distribVersion)
    buildPlan = []
    config.createBuildPlan(buildList, buildPlan)
    if config.debug:
        items = []
        for i in buildPlan:
            if isinstance(i, str):
                items.append('(' + i + ')')
            else:
                items.append(i.name)

        print(" * build plan: {0}".format(", ".join(items)))

    config.treatPlatformPackages(buildPlan)

    
    def buildModule(buildItem):
        debugLog(' * module {0}'.format(buildItem.name))
        debugLog('   ==> checking out')
        if not buildItem.checkout(config):
            print("checkout error for {0}".format(buildItem.name))
            return False

        debugLog('   ==> preparing')
        if not buildItem.prepare(config):
            print("prepare error for {0}".format(buildItem.name))
            return False
            
        debugLog('   ==> building')
        if not buildItem.build(config):
            print("build error for {0}".format(buildItem.name))
            return False
        return True

    for item in buildPlan:
        if isinstance(item, str):
            continue
        if not buildModule(item):
            break

    print("=== finished, OGON installed ===")
    return 0


if __name__ == '__main__':
    if platform.python_version_tuple()[0] != '3':
        print("expecting python 3, exiting")
        sys.exit(1)
        
    sys.exit( main(sys.argv) )
    
