# Accendino manual

## Command line invocation

_Accendino_ accepts the following command line arguments:

* `--prefix=<dir>`: the directory where to install generated items
* `-h|--help`: show an help message
* `-v|--version`: display the version
* `--debug`: show extra debugging message during build
* `--no-packages`: don't do any platform packages checks
* `--build-deps`: don't build artifact just do platform packages checks and installation
* `--targets=<targets>`: a coma separated list of targets to build
* `--build-type=<build type>`: kind of build, can be `release` or `debug`
* `--build-as-debug=<artifacts>`: a coma separated list of artifacts (by name or by a name they provide) to build
  in debug mode whatever the `--build-type` is. Can be given multiple times, the lists are merged
* `--work-dir=<dir>`: the top directory where projects will be stored, current directory by default
* `--resume-from=<target>`: resume the build starting at this target
* `--refreshSources`: force updating git sources to their upstream branch, and rebuild any artifact whose
  source actually changed (along with everything depending on it)
* `--refresh`: force rebuilding the requested targets (the ones passed via `--targets`, or the default
  ones), even if they were already built
* `--project=<name>`: sets a project name (used to store all items of this project in the same tree), "work" by default
* `--options=<path>`: path to an ini file containing build options
* `--targetDistrib=<distrib>`: cross compile for another platform: `mingw32` / `mingw64` (Windows binaries built with
  mingw) or `emscripten` (WebAssembly for the browser or node, see [Building for emscripten](#building-for-emscripten)).
  These also set the target arch and the toolchain
* `--targetArch=<arch>`: the target architecture (`i686`, `x86_64`, `arm64` or `wasm32`), the local one by default.
  `aarch64` is accepted for `arm64`, see [Building for the other macOS architecture](#building-for-the-other-macos-architecture)
* `--toolchain=<name>`: the toolchain to use: `default` (autodetected), `gcc`, `clang`, `vs`, `vs/<flavor>`, `mingw`
  or `emscripten`
* `--buildToolsPrefix=<path>`: when cross compiling, where the tools built for the build machine are installed
  (`deploy-build` in the project directory by default), see [Tools for the build machine](#tools-for-the-build-machine)
* `--buildToolchain=<name>`: when cross compiling, the toolchain that builds tools for the build machine (`default`)
* `<accendino file>`: the name of the root _Accendino_ file to load

_Accendino_ uses the `ACCENDINO_PATH` env variable that contains a PATH like period separated string of location where
to search for accendino source files.

## Accendino workflow

Here's the steps performed by _Accendino_ when building:

1. the command line is parsed and the build options file is read, the `[accendino]` section of the options file
    can give command line arguments
2. we determine the platform on which we're running, that gives us which package manager is in use on this platform,
    and the target machine: the local one, or the one of `--targetDistrib` / `--targetArch` when cross compiling
3. we determine the toolchain to use for the target
4. the _Accendino_ source files are read, possibly reading the included files
5. the targets to build are determined either by what's provided on the command line or with `DEFAULT_TARGETS` given
    in the _Accendino_ source file
6. tool dependencies are resolved: without cross compilation `toolDeps` are merged into `deps`. When cross compiling
    and some artifacts have `toolDeps` (or a `native:` target is requested), a toolchain is chosen for the build
    machine (`--buildToolchain`) and the _Accendino_ source files are read a second time for the build machine,
    that adds `native:<name>` artifacts installed in `--buildToolsPrefix`, see
    [Tools for the build machine](#tools-for-the-build-machine)
7. _Accendino_ creates a build plan, that's a sequence of artifacts to build where each artifact comes after its
    dependencies, `native:` artifacts included
8. given the build plan _Accendino_ checks which platform packages are needed (for the target and for the build
    machine) and try to install the ones which are missing
9. the toolchains are activated, the target one and the one of the build machine if any
10. then it's the build step: for each artifact of the build plan, _Accendino_ will
    * checkout the source code of the build artifact
    * run commands to prepare the source directory
    * run commands to prepare the build directory, unless the commands and the environment are the same as the
      ones of the previous run (they're saved in `accendino.prepared` in the build directory)
    * build and install, unless the artifact was already built (`accendino.built` in the build directory) and none
      of its dependencies was rebuilt since

If a `--resume-from` argument is given we start the build plan from the provided build artifact. `--refresh` forces
the rebuild of the requested targets, and `--refreshSources` the rebuild of the artifacts whose git sources changed;
in both cases the artifacts depending on them are rebuilt too.

## Build options files
A build options file is an ini file containing options for the build, the `accendino` section of the file is
injected to the command line argument parser of _Accendino_, that means that options that you may provide on the command
line can also be passed via this build options file. So for instance:

```ini
[accendino]
prefix=/opt/install-there
build-type=debug

....

```

Otherwise the conventions in _Accendino_ files are:

* to have a section per built item and provide options there
* the `fromSources` options forces this artifact to be built from sources instead of using platform packages

For instance with this file:
```ini
[libusb]
fromSources=on

[ffmpeg]
fromSources=on
with_x264=on
```

`libusb` and `ffmpeg` will be built from sources. And we require to have the support of `x264` in ffmpeg.

When cross compiling, the [artifacts for the build machine](#tools-for-the-build-machine) first look for an option in a
`native:<section>` section, then in `<section>`. With this file, `libusb` is built from sources for the build
machine only:
```ini
[native:libusb]
fromSources=on
```


## Custom source file
_Accendino_ is there to pull your sources and build a your software with complex dependencies, to achieve this you
ship a _source_ file that is a python script listing new dependencies and packages to build. The [forgiare](https://github.com/forgiare/accendino/blob/master/forgiare.conf)
file give an example of such capacity, it will substitute the official _ogon_ repo with last changes from the _forgiare_ project.

_Accendino_ reads a source file and interprets it as a python file and when done it will search for these variables:

* `DEFAULT_TARGETS : str` : contains the default build artifacts to build when no target is given on the command line (coma separated string)
* `ARTIFACTS : List[Any]` : contains a list of build artifacts
* `PROJECT : str` : an optional project name, it allows to store all the build items (sources and binaries) in a specific directory. Like the `--project` command line argument
* `CROSS_PLATFORM_FILE_CHOOSER : Callable` : an optional function with the signature `(builder: str, machine: Machine) -> str`
     that returns the path of the cross compilation file for the given `builder` (`cmake` or `meson` for now) when cross
     compiling for `machine` (it has `distribId`, `targetDistrib`, `arch`, `toolchainObj`, ...). When it's not defined or
     returns `None`, the cross file of the toolchain is used: the `mingw` toolchain has cross files for Debian/Ubuntu
     (shipped with _Accendino_) and Fedora/Redhat (the ones of the distribution), the `emscripten` toolchain has its own and
     the `clang` toolchain (the default on macOS) has the ones to build for the other macOS architecture.
     A cross compilation without cross file stops before building

When interpreting the source file _Accendino_ provides some useful variables and functions to the source file:

### Variables

* `accendinoVersion : str`: the version of _Accendino_
* `buildType : str`: the kind of build usually contains `debug` or `release`
* `distribId : str`: the local distribution id can be `Debian`, `Ubuntu`, `redhat`, `Fedora`, `Windows`, `Darwin` (for MacOsX)
* `distribVersion : str`: the version associated with the distribution in `distribId`
* `targetArch : str`: the destination architecture `x86_64`, `i686`, `arm64` (also on Linux where the
  system calls it `aarch64`), `wasm32`
* `targetDistribId : str`: the destination target id can be `Debian`, `Ubuntu`, `redhat`, `Fedora`, `Windows`, `Darwin`, `mingw` or `emscripten`
* `toolchain : str`: name of the toolchain
* `crossCompilation : bool`: tells if the build is any kind of cross compilation
* `libdir : str`: the library directory to use for this distribution (typically `lib` or `lib64`)
* `buildingTools : bool`: `True` when the files are evaluated for the build machine, to build tools used when cross
  compiling (see [Tools for the build machine](#tools-for-the-build-machine))
* `toolsForDistribId : str`, `toolsForArch : str`: when `buildingTools` is `True`, the target the tools are built for
  (`mingw` and `x86_64` for instance), `None` otherwise
* `UBUNTU_LIKE  : str`: contains `Debian|Ubuntu` a shortcut for dpkg based distributions
* `REDHAT_LIKE : str`: contains `Fedora|Redhat` a shortcut for rpm based distributions

### Platform version condition

_Accendino_ implements some version comparison conditions with the format `<operator> <distribId> <version>`, we
have these operators available:

* `=` or `==`: true if exact match, `version` is optional for this operator
* `!` or `!=`: true if different from, `version` is optional for this operator
* `<`, `<=`, `>` or `>=`: version comparison operators

Some examples:

* `= Fedora`: match if we're running on Fedora
* `== Ubuntu 18.04`: match if we're running on Ubuntu 18.04
* `>= Debian 12.00`: match if we're running on Debian 12.0 and later

### Functions

* `stdGitSourceFromOptions(key: str, url: str, tag: str = 'master') -> Source`: creates a `GitSource` by looking at options ini file in the `key`
    section for `url` and `tag` keys, and otherwise use the provided ones in `url` and `tag`. That allows to give a default location for the Git source
    that can be overriden by the option ini file. For instance with this option file:
    ```
    [toto]
    url=https://mygit.selfhosted.com/toto.git
    tag=specialTag
    ```
    and `stdGitSourceFromOptions('toto', 'https://git.toto.org/toto/git', 'master')`, you'll get a git source from your repo and on your tag;
* `stdBuildFromSourceTest(key: str, lokals, default_option: bool) -> bool`: returns if an artifact should built from sources. For that this function
    first look in the local variables provided in `lokals` and look for `key + '_forceBuild'` and see if it's true. That allows an accendino file to set a 
    `wayland_forceBuild` variable that will be caught in `wayland.accendino` to force a build from sources. The function then look at a `fromSources` key in the
    option ini file in the section `key`;
* `checkAccendinoVersion(cond: str) -> bool`: checks if you're running on a given _Accendino_ version. The condition is something like `<op> <version>` with `op`
    than can be `=`, `==`, `!`, `!=`, `<`, `<=`, `>` or `>=`. And `version` is the version string with 3 digits. For example: `cond='>= 0.5.1'`;
* `checkDistrib(cond : str) -> bool`: checks if the current distribution matches the [platform version condition](#platform-version-condition)
    given in `cond`;
* `getOption(opt: str, defaultValue) -> bool|str`: look for a build option in the build option file. The format for `opt` is `<section>.<variable>` so for instance
  `ffmpeg.fromSources` will look in the `ffmpeg` section of the INI file and will look for the `fromSources` variable. If the variable or the section are missing the
  default value is returned;
* `include(name : str, include_once: bool = True) -> bool`: allows to include another _Accendino_ source file. _Accendino_ will search for this file in the following
    locations: `.`, `pocket`, paths given in the `ACCENDINO_PATH` env variable, and finally in the pockets directory of _Accendino_. If `include_once` is set to `True`
    the file is just included once;
* `pickDeps(name : str) -> List[str]`: returns a copy of the artifact dependencies of the build artifact named `name`.
    This is useful if you define a build artifact that is just the variant of another one;
* `pickPkgDeps(name : str, extra = None, override : bool = False) -> Dict[str, List[str]]`: returns a copy
    of the package dependencies of the `name` build artifact. `extra` packages definitions are added to the result.
    `override` is true, the extra entries overrides the existing values instead of being added .For instance with
    `source deps={'Fedora': ['pack1'], 'Ubuntu': ['pack2'] }` and `extra={'Ubuntu': ['pack3']}` with `override=True`
    you have `{'Fedora': ['pack1'], 'Ubuntu': ['pack3'] }`).
    With `override=False`(the default) you have `{'Fedora': ['pack1'], 'Ubuntu': ['pack2', 'pack3'] }`). This is useful if you define a build
    artifact that is just the variant of another one;
* `mergePkgDeps(d1 : Dict[str, List[str]], d2 : Dict[str, List[str]]) -> Dict[str, List[str]]`: merges two [platform packages dependencies](#platform-packages-dependencies)
    dictionaries together, concatenating the package lists of keys present in both. For instance with `d1={'Ubuntu': ['pack1']}` and `d2={'Ubuntu': ['pack2'], 'Fedora': ['pack3']}`
    you get `{'Ubuntu': ['pack1', 'pack2'], 'Fedora': ['pack3']}`;
* `abort(msg: str = None) -> None`: immediately stops the whole _Accendino_ run with exit code `1` showing the optional error message;
* `findAsset(item: str, asset: str) -> str`: returns the absolute path of the `<item>/<asset>` file, searched like included accendino files,
    or `None` if not found. The extra files needed by an accendino file are stored in a directory with the same name, for instance
    `findAsset('cef', 'cef-install.cmake')` in `cef.accendino`;

### Objects

* `DepsAdjuster(cond : str, add : List[str], drop : List[str])`: an object that can adjust the dependency list based on the platform. `cond` contains a
    [platform version condition](#platform-version-condition) string to test, if that condition is met then we add the items in the `add` list, and we remove
    items from the `drop` list.
    For example, `DepsAdjuster('< Debian 11.00', add=['pkg1'])` will add `pkg1` as dependency if we're building under a Debian with a version before `11.00`. `DepsAdjuster` can be
    used for build artifacts dependencies or for platform packages. The common cases are: on all Ubuntu version you need the same platform packages except that the package is renamed starting at
    a given version. Another common case is build artifact dependencies, where a platform lib is not available after a given Ubuntu version and you need to build it by hand and so add a build artifact
    dependency;
* `logging`: an export of the `zenlog` module. You can use it to log your messages with for instance `logging.debug('hello from the accendino file')`;
* `NativePath(*args, **kwargs)`: an object representing a native path (with `\` under windows or `/` under posix). `args` are the path components of the path
    If needed you can ship `prefix=<prefix>` or `suffix=<suffix>`, these strings are added before or after the generated path. For instance
    `NativePath('{srcdir}', 'toto', 'bin', prefix='--mypath=', suffix='-after')` will generate `--mypath={srcdir}/toto/bin-after` under posix or
    `--mypath={srcdir}\toto\bin-after` under windows. This is very usefull if you need to pass a path to a tool that must be in native path notation.
* `RunInShell(args: T.list)`: notify that the given command shall always be run on a real shell so either the regular shell under unix, or the msys2   
    shell under windows;


### Sources

`Source` objects are invoked to checkout your code, we have these available:

* `GitSource(url: str, branch: str, depth: int = 1, shallow_submodules: bool = False, recurse_submodules: bool = False)` : a source that checks out the code from `git`.
    Parameters mimick the `git` command line arguments;
* `LocalSource(srcdir : str, do_symlink : bool = False)` : a source that uses code stored in a local directory. If `do_symlink` is true, the code is just symlinked
    in the _Accendino_ sources directory, otherwise the whole source tree is copied;
* `RemoteArchiveSource(url: str, saveAs: str = None, compression_method: str = 'guess', strip_depth: int = 0, checked_file: str = 'aclocal.m4)`: sources
    contained in a remote archive. The archive will be downloaded and then decompressed. `strip_depth` allows to strip the version directory if any (like if the archive expands
    to `libressl-1.4.2/...`), it works for tar and zip archives;

### Platform packages dependencies
Platform packages dependencies are expressed as a `dict` with the key that is the target distribution. It takes in account
cross compilation with the `<distrib>-><targetDistrib>@<arch>` format. We also support the `|` syntax to match multiple distributions at once.

The corresponding list value is packages that are needed (we check that they are installed and install them if missing) to build.
The list can also contain `DepsAdjuster` objects, this way you can specify generic needed package and

Here's some examples for the key:
* `Fedora` matches any Fedora version
* `Fedora|Redhat` matches when building on Fedora or Redhat
* `Debian 12` matches Debian version 12
* `Ubuntu 24.04` matches Ubuntu 24.04
* `Darwin` matches builds on MacOs
* `Windows` matches builds on Windows
* `Fedora->mingw@x86_64` matches build on a Fedora for a cross build to mingw64
* `Ubuntu->emscripten@wasm32` matches build on a Ubuntu for a cross build to emscripten

Here's some full examples:
* `'Ubuntu|Debian': ['libprotobuf-c-dev', DepsAdjuster('>= Ubuntu 22.04|>= Debian 12.00', add=['thrift-compiler', 'libthrift-dev'])]` always require the `libprotobuf-c-dev` when
    under Ubuntu or Debian. If we're on a Ubuntu greater or equal to 22.04 or a Debian greater or equal to 12, then also require `thrift-compiler` and `libthrift-dev`;
* `'Fedora->mingw@x86_64': ['mingw64-zlib']` when cross compiling on Fedora to mingw64, require the mingw64-zlib rpm package;

The Windows platform has a special format for package names that is `<packageType>/<packageName>`. packageType can be:
* `choco`: search for packages handles with Chocolatey
* `path`: search for the given executable in the PATH

So for instance :
* `choco/nasm` means "check and install the `nasm` package of Chocolatey"
* `path/nasm` means "checks for `nasm.exe` in the PATH"

You can also use alternative installations using the `|` separator and give this way the search order. So for instance `choco/nasm|path/nasm.exe` means
"check that the nasm package of chocolatey, and then nasm.exe in the PATH, and if not found then install nasm from chocolatey"



### Build artifacts

All build artifacts share the same parameters:

* `name : str`: name of this artifact;
* `deps : List[str]`: a list of the name of build artifacts that this artifact depends on for the build;
* `srcObj : accendino.sources.Source`: a [`accendino.sources.Source`](#sources) object that will checkout your sources;
* `provides : List[str] | str`: a list of build artifacts that this artifact provides. For instance you can have a `freerdp2` artifact that provides `freerdp`;
* `pkgs : Dict[str, List[str]]`: a dictionary of platform packages dependencies, see the [previous paragraph](#platform-packages-dependencies) for the syntax of this dictionary;
* `toolchainArtifacts = 'c'`: a list or a coma separated string of toolchain artificats that you are needed by this build item. Usual values argument
 `c` or `c++`, it will be used to add package requirements;
* `toolDeps : List[str]`: build artifacts that this artifact uses as tools during its build (a code generator for
  instance). Without cross compilation they are plain dependencies, when cross compiling they are built for the build
  machine (see [Tools for the build machine](#tools-for-the-build-machine)).
* `buildMachineOnly = False`: the artifact only makes sense as a tool for the build machine (a code generator,
  an assembler...). When cross compiling it is not built for the target, and dependencies to it from target artifacts
  are tool dependencies (see [Tools for the build machine](#tools-for-the-build-machine)).


When giving commands, you can use these format string they will be replaced by their respective values:

* `prefix`: the `--prefix` argument given to _Accendino_ in native form (with `/` under posix and `\` under windows)
* `prefix_posix`: the `--prefix` argument given to _Accendino_ in posix form (with `/` in the path)
* `prefix_msys2`: the `--prefix` argument given to _Accendino_ as a msys2 path form (so `c:\\toto` will become `/c/toto`)
* `libdir`: where libraries are usually built and installed (`lib` on most places, `lib64` on redhat like systems)
* `srcdir`: the source directory of this artifact in native form (with `/` under posix and `\` under windows).
    Useful to run commands in the source tree (for projects that needs `autogen.sh` / `bootstrap`)
* `srcdir_posix`: the source directory of this artifact in posix form (with `/` in the path)
* `builddir`: the build directory of this artifact in native form (with `/` under posix and `\` under windows)
* `builddir_posix`: the build directory of this artifact in posix form (with `/` in the path)
* `build_prefix`, `build_prefix_posix`: where tools for the build machine are installed (`--buildToolsPrefix`) when cross
  compiling, the same as `prefix` otherwise

Specific build artifacts objects and their signatures:

* `DepsBuildArtifact(name: str, deps=[], provides=[], pkgs={})`: a meta build artifact that can used to group other build artifacts
* `BuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[])`: a generic build artifact with prepare commands and build commands
* `CMakeBuildArtifact(name: str, deps, srcObj, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={}, cmakeProjectDir='{srcdir}')`: a build artifact that uses `cmake` to be built.
    `cmakeProjectDir` is the directory of the `CMakeLists.txt` to use, by default the root of the sources. It can point to an asset (see `findAsset()`) to install a prebuilt
    distribution that doesn't have a CMake project, the sources directory is then available as `{srcdir}` in `cmakeOpts`
* `QMakeBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={})`: a build artifact relying on `qmake` / `make` to build
* `AutogenBuildArtifact(name: str, deps, srcObj, autogenArgs=[], noconfigure=False, isAutogen=True, configureArgs=[], runInstallDir=None, extraEnv={}, provides=[], pkgs={}`:
    a build artifact that relies on `autotools` / `make` to build
* `MesonBuildArtifact(name: str, deps, srcObj, mesonOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={})`: a build artifact that relies on `meson` to build
* `CustomCommandBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_src_cmds=[], prepare_cmds=[], build_target='all', install_target='install', builder='make')`: build artifact with the provided `builder` (can be `make`, `makeMsys2`, `nmake` or `ninja`) with specified commands to prepare the source and build directory


## Tools for the build machine
Some artifacts produce programs that are run during the build of others: `protoc` generates code from `.proto` files,
Qt has `moc` and `rcc`, `wayland-scanner` generates protocol code... When cross compiling these programs must be built
for the machine running the build, while the libraries of the same project are needed for the target. So what makes
something a tool is the dependency, declared with `toolDeps`:

```python
CMakeBuildArtifact('myapp', ['protobuf-artifact'], src,
    toolDeps=['protobuf-artifact'],
    cmakeOpts=['-DProtobuf_PROTOC_EXECUTABLE={build_prefix_posix}/bin/protoc'])
```

Here `myapp` links with the `libprotobuf` of the target and runs the `protoc` of the build machine.

Without cross compilation `toolDeps` are merged into `deps` and nothing else changes. When cross compiling and some
artifacts have `toolDeps` (or a `native:` target is requested), _Accendino_ evaluates the _Accendino_ files a second
time, with a new context describing the build machine:
* `targetDistribId` and `targetArch` are the ones of the local machine and `crossCompilation` is `False`, so recipes
  pick platform packages or native builds as usual;
* `buildingTools` is `True` and `toolsForDistribId` / `toolsForArch` tell the target the tools are for. Recipes use it
  to build less (only the tools), or to keep tools and target libraries at the same version;
  `protobuf.accendino` for instance builds `protoc` from sources when the target `libprotobuf` is built from sources:
  ```python
  protobuf_forDistribId = toolsForDistribId if buildingTools else targetDistribId
  protobuf_fromSources = getOption('protobuf.fromSources', protobuf_forDistribId in ('Windows', 'mingw', 'emscripten',))
  ```
* options are first searched in `native:<section>` sections;
* the artifacts of this evaluation are named `native:<name>` (with their provides and dependencies), are installed in
  `--buildToolsPrefix` and their source and build directories are named `native-<name>`. They can be requested with
  `--targets=native:<name>`.

Tool dependencies of the target artifacts point to these `native:` artifacts. When building target artifacts, the `bin`
directory of the build prefix is added to `PATH` and `CMAKE_PROGRAM_PATH`, and its library directory to
`LD_LIBRARY_PATH` (`DYLD_LIBRARY_PATH` on macOS) so that tools linked with shared libraries can run. The
`tests/cross-tools` directory contains an example cross compiling programs that run `protoc` (built with CMake and
with meson), `protoc-gen-c` (protobuf-c) and `wayland-scanner`.

An artifact created with `buildMachineOnly=True` is never built for the target when cross compiling: it only exists as
`native:<name>`, the dependencies of target artifacts to it become tool dependencies and asking for it in `--targets`
builds its `native:` version. Without cross compilation it's a regular artifact.

Meson knows the difference between the two machines: `dependency(..., native: true)` and `find_program(..., native:
true)` look for things of the build machine. When cross compiling, _Accendino_ gives meson a native file
(`accendino-native.ini` in the build directory) where `pkg-config` searches the build prefix and the system
directories, instead of the target directories of `PKG_CONFIG_LIBDIR`; the build prefix is also in `cmake_prefix_path`
for the build machine. CMake has no such notion, CMake projects find tools with `find_program()` thanks to
`CMAKE_PROGRAM_PATH`.
When a meson artifact is prepared again (because one of its dependencies was rebuilt for instance), _Accendino_ clears
meson's cache of found dependencies first, so that their new versions are seen.

An artifact can use its own tools: `wayland` builds `wayland-scanner` and uses it to generate its protocol code. Its
`toolDeps` contain `wayland-artifact`: without cross compilation a tool dependency on the artifact itself is ignored, when
cross compiling the target `wayland` is built without its scanner and uses the one of `native:wayland`, that only builds
`wayland-scanner`.

## Building for emscripten
With `--targetDistrib=emscripten` _Accendino_ builds WebAssembly with [emscripten](https://emscripten.org), for instance
`accendino --targetDistrib=emscripten --targets=freerdp3 freerdp.accendino` builds FreeRDP's SDL3 client for the browser.

The `emscripten` toolchain uses the emsdk pointed by the `EMSDK` env variable when it is set (like in the
`emscripten/emsdk` docker image). Otherwise it installs emsdk in the `tools/emsdk` directory of the project, it
only needs `git`, `python3`, `xz` and `tar` on the host. The toolchain sets `CC=emcc`, `CXX=em++`, `AR=emar`
and the environment of `emsdk_env.sh` for all the build commands.

Options in the `emscripten` section of the build options file:
* `version`: the emsdk version to install when `EMSDK` is not set (`6.0.11` by default);
* `pthreads`: compile and link everything with `-pthread` (on by default), needed for shared memory and so to use
  threads in the program.

What changes compared to a native build:
* there are no shared libraries in WebAssembly: the cmake cross file sets `BUILD_SHARED_LIBS=OFF` by default and meson
  builds use `-Ddefault_library=static`. Projects with their own option for this (like zlib's `ZLIB_BUILD_SHARED`) must
  be told explicitly;
* the cmake cross file wraps emsdk's `Emscripten.cmake` (what `emcmake` does) and adds the deploy prefix to
  `CMAKE_FIND_ROOT_PATH`, so `find_package()` finds the artifacts we have built. Programs run in `node`
  (`CMAKE_CROSSCOMPILING_EMULATOR` and meson's `exe_wrapper`). `install(TARGETS)` only installs the `.js` loader of
  an executable, so after `cmake --install` _Accendino_ installs the matching `.wasm` module next to each installed `.js`;
* `PKG_CONFIG_LIBDIR` only contains the deploy prefix and the emscripten sysroot, never the host `.pc` files;
* platform packages can't satisfy a dependency: _Accendino_ files must build it from sources when `targetDistribId` is
  `emscripten`. For autotools based projects pass `--host=wasm32-unknown-emscripten` in the configure arguments.

## Building for the other macOS architecture

On macOS, `--targetArch=x86_64` on an Apple Silicon machine or `--targetArch=arm64` on an Intel one
cross compiles for the other architecture with Apple's clang:
* the cmake cross file sets `CMAKE_OSX_ARCHITECTURES`, `CMAKE_SYSTEM_NAME` (so `CMAKE_CROSSCOMPILING` is true) and
  ignores the Homebrew prefix; the meson one passes `-arch` to the compilers and linkers. Other builds (autotools,
  custom commands) get `-arch` in `CFLAGS`, `CXXFLAGS`, `OBJCFLAGS`, `OBJCXXFLAGS` and `LDFLAGS`, autotools projects
  building for arm64 on Intel also need `--host=aarch64-apple-darwin` in their configure arguments;
* x86_64 binaries run on Apple Silicon with Rosetta, so meson runs its checks for x86_64 without an exe wrapper;
* Homebrew only has libraries for the local architecture: `PKG_CONFIG_LIBDIR` doesn't contain its directories and
  _Accendino_ files must build the target libraries from sources when `crossCompilation` is true. Package keys stay
  `Darwin`, so Homebrew packages still provide the build tools (cmake, ninja, meson, ...);
* tools are built for the local architecture as `native:` artifacts, see
  [Tools for the build machine](#tools-for-the-build-machine).

Without cross compilation, `PKG_CONFIG_LIBDIR` contains Homebrew's `lib/pkgconfig` and `share/pkgconfig` (Homebrew
is found with `$HOMEBREW_PREFIX`, `/opt/homebrew` or `/usr/local`), as setting `PKG_CONFIG_LIBDIR` replaces the default
search path of Homebrew's `pkg-config`.

Universal binaries are made by building the project twice, once per architecture with a different `--prefix`, and
merging the results with `lipo`; _Accendino_ doesn't do this last step.
