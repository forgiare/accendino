# Accendino, a complex project builder

## About
_Accendino_ (lighter in italian) was originally an helper script that avoids the burden of following the Ogon installation
instructions and do it for you. But it evolved to a program to build your complicated projects on multiple platforms.

_Accendino_ can also be used to checkout all your project sources if you wish to quickly have a development environment.

You can see the [manual](https://github.com/forgiare/accendino/blob/master/MANUAL.md) or the
[changelog](https://github.com/forgiare/accendino/blob/master/CHANGELOG.md).

## Installing

```console
$ python3 -m venv _v
$ source _v/bin/activate
(_v) $ pip install accendino
```

## Deploying Ogon

Even if _Accendino_ aims to build any of your projects with multiple dependencies, it is still useful to deploy _ogon_.

Please note, that for now _accendino_ doesn't perform system operation required for a working ogon installation
(systemd units, PAM configuration, dbus authorizations). So refer to the ogon build guide to achieve these.

To quicky install all the Ogon stack in `/opt/ogon` in release mode:

```console
# accendino --prefix=/opt/ogon ogon.accendino
```

To quicky install only the Ogon RDP server in `/opt/ogon-dev` in debug mode:

```console
# accendino --prefix=/opt/ogon-dev --build-type=debug --targets=ogon ogon.accendino
```

To install the _forgiare_ version of Ogon in `/opt/forgiare` in debug mode:

```console
# accendino --prefix=/opt/forgiare --build-type=debug forgiare.accendino
```

## Using Accendino for your projects

_Accendino_ is a great tool to build complex projects on multiple platform. In _Accendino_ source files you can:

* pull your sources from git or from local locations;
* express dependencies between your build artifacts;
* list some platform packages that are needed for the build on a given platform. Currently we support `dpkg`, `rpm` and `brew`. And
    of course you can have dynamic lists, because it's very common that on your linux distribution a package has been renamed or
    removed between distro versions;
* the _Accendino_ source file is interpreted as a python file that means that you can code any kind of
    build logic using the python language;
* _Accendino_ provides some useful objects to express builds of artifacts that use `cmake`, `qmake`, `autotools`, `meson`, and if
    unhappy with these you can always specify the commands to invoke (or contribute yours);

See the [manual](https://github.com/forgiare/accendino/blob/master/MANUAL.md) for the documentation of what's available to your source file.


Here's sample pieces of some _Accendino_ files for freerdp. The idea is that on Mac we build some of the
dependent libraries for FreeRDP:

So `freerdp-mac-deps.conf` contain some artifacts definitions:
``` python
# freerdp-mac-deps.conf
...
ARTIFACTS += [
    CMakeBuildArtifact('zlib', [], GitSource('https://github.com/madler/zlib.git', 'v1.3.1')),

    CMakeBuildArtifact('uriparser', [], GitSource('https://github.com/uriparser/uriparser.git', 'uriparser-0.9.8'),
        ['-DURIPARSER_BUILD_DOCS=OFF', '-DURIPARSER_BUILD_TESTS=OFF', '-DURIPARSER_BUILD_TOOLS=OFF']
    ),

    CMakeBuildArtifact('cJSON', [], GitSource('https://github.com/DaveGamble/cJSON.git', 'v1.7.18'),
        ['-DENABLE_CJSON_TEST=OFF', '-DBUILD_SHARED_AND_STATIC_LIBS=OFF']
    ),

    CMakeBuildArtifact('opus', [], GitSource('https://gitlab.xiph.org/xiph/opus.git', 'v1.5.2'),
        ['-DOPUS_BUILD_SHARED_LIBRARY=ON']
    ),

    CMakeBuildArtifact('libusb', [],
        GitSource('https://github.com/libusb/libusb-cmake.git', 'v1.0.26', shallow_submodules=True, recurse_submodules=True),
        ['-DLIBUSB_BUILD_EXAMPLES=OFF', '-DLIBUSB_BUILD_TESTING=OFF', '-DLIBUSB_ENABLE_DEBUG_LOGGING=OFF', '-DLIBUSB_BUILD_SHARED_LIBS=ON']
    ),

    CustomCommandBuildArtifact('openssl', ['zlib'],
        GitSource('https://github.com/openssl/openssl.git', 'openssl-3.2.0'),
        prepare_cmds=[
            ['{srcdir}/config', '--prefix={prefix}', '--libdir={libdir}', 'no-asm', 'no-tests', 'no-docs', 'no-apps', 'zlib']
        ],
        build_target='build_sw', install_target='install_sw'
    ),
    ...
]
```

And in `freerdp.conf` if we're on MacOsX we add these dependencies:
``` python
# freerdp.conf
...
freerdp_deps = []
if checkDistrib('= Darwin'):
    include("freerdp-mac-deps.accendino")
    freerdp_deps += ['zlib', 'openssl', 'libusb']
...

ARTIFACTS += [
    CMakeBuildArtifact(f'freerdp2', freerdp_deps,
        GitSource('https://github.com/FreeRDP/FreeRDP.git', 'stable-2.0'),
        options, provides=provides,
        pkgs = {
            REDHAT_LIKE: freerdp_fedora_redhat_base,
            UBUNTU_LIKE: freerdp_ubuntu_debian_base + freerdp_ubuntu_debian_common
        }
    ),
]
```