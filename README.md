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

To quickly install only the Ogon RDP server in `/opt/ogon-dev` in debug mode:

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
* list some platform packages that are needed for the build on a given platform. Currently we support `dpkg`, `rpm`, `pacman`, `pkg`, `chocolatey` and `brew`. And
    of course you can have dynamic lists, because it's very common that on your linux distribution a package has been renamed or
    removed between distro versions;
* the _Accendino_ source file is interpreted as a python file that means that you can code any kind of
    build logic using the python language;
* _Accendino_ provides some useful objects to express builds of artifacts that use `cmake`, `qmake`, `autotools`, `meson`, and if
    unhappy with these you can always specify the commands to invoke (or contribute yours);

See the [manual](https://github.com/forgiare/accendino/blob/master/MANUAL.md) for the documentation of what's available to your source file.


Here's some sample pieces of _Accendino_ files for freerdp with the file to build the ffmpeg dependency or
use system provided packages:

```python
# ffmpeg.accendino
ffmpeg_pkgDeps = {
    UBUNTU_LIKE: ['libavcodec-dev', 'libavfilter-dev', 'libavformat-dev', 'libavutil-dev', 'libswscale-dev',
                      'libavdevice-dev', 'libpostproc-dev'],
    REDHAT_LIKE: ['libavcodec-free-devel', 'libswscale-free-devel'],
}
ffmpeg_fromSources = False

if targetDistribId in ('mingw', 'Windows', 'Darwin',):
    ffmpeg_fromSources = True

if ffmpeg_fromSources:
    extraArgs = []
    if crossCompilation:
        extraArgs.append('--enable-cross-compile')
        if targetDistribId == 'mingw':
            flags = {
                'i686': ['--arch=i686', '--target-os=mingw32', '--cross-prefix=i686-w64-mingw32-'],
                'x86_64': ['--arch=x86_64', '--target-os=mingw64', '--cross-prefix=x86_64-w64-mingw32-']
            }
            extraArgs += flags.get(targetArch, [])
            extraArgs.append('--disable-mediafoundation')

    if targetDistribId == 'Darwin':
        extraArgs += ['--enable-shared', '--disable-static',
            '--enable-swscale', '--disable-asm', '--disable-libxcb',
            '--disable-xlib', '--enable-avcodec',
        ]

    nasmForAll = {
        'Darwin': ['nasm'],
        'Windows': ['choco/nasm|path/nasm'],
    }

    for distrib in ('Ubuntu', 'Debian', 'Redhat', 'Fedora',):
        nasmForAll[f'{distrib}'] = ['nasm']
        nasmForAll[f'{distrib}->mingw@x86_64'] = ['nasm']

    ARTIFACTS += [
        CustomCommandBuildArtifact('ffmpeg', [],
            GitSource('https://github.com/FFmpeg/FFmpeg.git', 'n7.1'),
            prepare_cmds=[
                [NativePath('{srcdir}', 'configure'), '--prefix={prefix}', '--disable-doc', '--disable-programs', '--disable-securetransport'] + extraArgs
            ],
            pkgs=nasmForAll,
            provides=['ffmpeg-artifact']
        ),
    ]

else:
    ARTIFACTS += [
        DepsBuildArtifact('ffmpeg-artifact', [], pkgs=ffmpeg_pkgDeps)
    ]
```



