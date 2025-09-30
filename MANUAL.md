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
* `--work-dir=<dir>`: the top directory where projects will be stored, current directory by default
* `--resume-from=<target>`: resume the build starting at this target
* `--project=<name>`: sets a project name (used to store all items of this project in the same tree), "work" by default
* `<accendino file>`: the name of the root _Accendino_ file to load

_Accendino_ uses the `ACCENDINO_PATH` env variable that contains a PATH like period separated string of location where
to search for accendino source files.

## Accendino workflow

Here's the steps performed by _Accendino_ when building:

1. first we determine the platform on which we're running, that gives us which package manager is in use
    on this platform
2. the _Accendino_ source file is read, possibly reading the included files
3. the targets to build are determined either by what's provided on the command line or with `DEFAULT_TARGETS` given
    in the _Accendino_ source file
4. _Accendino_ creates a build plan, that's a sequence of artifacts to build
5. given the build plan _Accendino_ checks which platform packages are needed and try to install the ones which are missing
6. then it's the build step: for each artifact of the build plan, _Accendino_ will
    * checkout the source code of the build artifact
    * run commands to prepare the source directory
    * run commands to prepare the build directory
    * build
    * install

If a `--resume` argument is given we start the build plan from that build artifact.


## Custom source file
_Accendino_ is there to pull your sources and build a your software with complex dependencies, to achieve this you
ship a _source_ file that is a python script listing new dependencies and packages to build. The [forgiare](https://github.com/forgiare/accendino/blob/master/forgiare.conf)
file give an example of such capacity, it will substitute the official _ogon_ repo with last changes from the _forgiare_ project.

_Accendino_ reads a source file and interprets it as a python file and when done it will search for these variables:

* `DEFAULT_TARGETS : str` : contains the default build artifacts to build when no target is given on the command line (coma separated string);
* `ARTIFACTS : List[Any]` : contains a list of build artifacts;
* `PROJECT : str` : an optional project name, it allows to store all the build items (sources and binaries) in a specific directory. Like the `--project` command line argument;
* `CROSS_PLATFORM_FILE_CHOOSER : Callable` : a function with the signature `(builder: str, localDistrib : str, distrib : str, arch: str) -> str`, that aims to return the path for
     a cross compilation file for the given `builder` (can be `cmake` or `meson` for now) and the given arch. If not specified it contains a default function that
     will work for `mingw[32|64]` builds

When interpreting the source file _Accendino_ provides some useful variables and functions to the source file:

### Variables

* `accendinoVersion : str`: the version of _Accendino_
* `distribId : str`: the local distribution id can be `Debian`, `Ubuntu`, `redhat`, `Fedora`, `Windows`, `Darwin` (for MacOsX)
* `distribVersion : str`: the version associated with the distribution in `distribId`
* `targetArch : str`: the destination architecture `x86_64`, `i686`, ...
* `targetDistribId : str`: the destination target id can be `Debian`, `Ubuntu`, `redhat`, `Fedora`, `Windows`, `Darwin` or `mingw`
* `crossCompilation : bool`: tells if the build is any kind of cross compilation
* `libdir : str`: the library directory to use for this distribution (typically `lib` or `lib64`)
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

* `checkAccendinoVersion(cond: str) -> bool`: checks if you're running on a given _Accendino_ version. The condition is something like `<op> <version>` with `op`
    than can be `=`, `==`, `!`, `!=`, `<`, `<=`, `>` or `>=`. And `version` is the version string with 3 digits. For example: `cond='>= 0.5.1'`
* `checkDistrib(cond : str) -> bool`: checks if the current distribution matches the [platform version condition](#platform-version-condition)
    given in `cond`
* `include(name : str, include_once: bool = True) -> bool`: allows to include another _Accendino_ source file. _Accendino_ will search for this file in the following
    locations: `.`, `pocket`, paths given in the `ACCENDINO_PATH` env variable, and finally in the pockets directory of _Accendino_. If `include_once` is set to `True`
    the file is just included once
* `pickDeps(name : str) -> List[str]`: returns a copy of the artifact dependencies of the build artifact named `name`.
    This is useful if you define a build artifact that is just the variant of another one
* `pickPkgDeps(name : str, extra = None, override : bool = False) -> Dict[str, List[str]]`: returns a copy
    of the package dependencies of the `name` build artifact. `extra` packages definitions are added to the result.
    `override` is true, the extra entries overrides the existing values instead of being added .For instance with
    `source deps={'Fedora': ['pack1'], 'Ubuntu': ['pack2'] }` and `extra={'Ubuntu': ['pack3']}` with `override=True`
    you have `{'Fedora': ['pack1'], 'Ubuntu': ['pack3'] }`).
    With `override=False`(the default) you have `{'Fedora': ['pack1'], 'Ubuntu': ['pack2', 'pack3'] }`). This is useful if you define a build
    artifact that is just the variant of another one

### Objects

* `DepsAdjuster(cond : str, add : List[str], drop : List[str])`: an object that can adjust the dependency list based on the platform. `cond` contains a
    [platform version condition](#platform-version-condition) string to test, if that condition is met then we add the items in the `add` list, and we remove
    items from the `drop` list.
    For example, `DepsAdjuster('< Debian 11.00', add=['pkg1'])` will add `pkg1` as dependency if we're building under a Debian with a version before `11.00`. `DepsAdjuster` can be
    used for build artifacts dependencies or for platform packages. The common cases are: on all Ubuntu version you need the same platform packages except that the package is renamed starting at
    a given version. Another common case is build artifact dependencies, where a platform lib is not available after a given Ubuntu version and you need to build it by hand and so add a build artifact
    dependency
* `logging`: an export of the `zenlog` module. You can use it to log your messages with for instance `logging.debug('hello from the accendino file')`
* `NativePath(*args, **kwargs)`: an object representing a native path (with `\` under windows or `/` under posix). `args` are the path components of the path
    If needed you can ship `prefix=<prefix>` or `suffix=<suffix>`, these strings are added before or after the generated path. For instance
    `NativePath('{srcdir}', 'toto', 'bin', prefix='--mypath=', suffix='-after')` will generate `--mypath={srcdir}/toto/bin-after` under posix or
    `--mypath={srcdir}\toto\bin-after` under windows. This is very usefull if you need to pass a path to a tool that must be in native path notation.
* `RunInShell(args: T.list)`: notify that the given command shall always be run on a real shell so either the regular shell under unix, or the msys2   
    shell under windows


### Sources

`Source` objects are invoked to checkout your code, we have these available:

* `GitSource(url: str, branch: str, depth: int = 1, shallow_submodules: bool = False, recurse_submodules: bool = False)` : a source that checks out the code from `git`. Parameters mimick the `git` command line arguments;
* `LocalSource(srcdir : str, do_symlink : bool = False)` : a source that uses code stored in a local directory. If `do_symlink` is true, the code is just symlinked in the _Accendino_ sources directory, otherwise the whole source tree is copied

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

Here's some full examples:
* `'Ubuntu|Debian': ['libprotobuf-c-dev', DepsAdjuster('>= Ubuntu 22.04|>= Debian 12.00', add=['thrift-compiler', 'libthrift-dev'])]` always require the `libprotobuf-c-dev` when
    under Ubuntu or Debian. If we're on a Ubuntu greater or equal to 22.04 or a Debian greater or equal to 12, then also require `thrift-compiler` and `libthrift-dev`
* `'Fedora->mingw@x86_64': ['mingw64-zlib']` when cross compiling on Fedora to mingw64, require the mingw64-zlib rpm package

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

* `name : str`: name of this artifact
* `deps : List[str]`: a list of the name of build artifacts that this artifact depends on for the build
* `srcObj : accendino.sources.Source`: a [`accendino.sources.Source`](#sources) object that will checkout your sources
* `provides : List[str] | str`: a list of build artifacts that this artifact provides. For instance you can have a `freerdp2` artifact that provides `freerdp`
* `pkgs : Dict[str, List[str]]`: a dictionary of platform packages dependencies, see the [previous paragraph](#platform-packages-dependencies) for the syntax of this dictionary
* `toolchainArtifacts = 'c'`: a list or a coma separated string of toolchain artificats that you are needed by this build item. Usual values argument
 `c` or `c++`, it will be used to add package requirements


When giving commands, you can use these format string they will be replaced by their respective values:

* `prefix`: the `--prefix` argument given to _Accendino_ in native form (with `/` under posix and `\` under windows)
* `prefix_posix`: the `--prefix` argument given to _Accendino_ in posix form (with `/` in the path)
* `libdir`: where libraries are usually built and installed (`lib` on most places, `lib64` on redhat like systems)
* `srcdir`: the source directory of this artifact in native form (with `/` under posix and `\` under windows).
    Useful to run commands in the source tree (for projects that needs `autogen.sh` / `bootstrap`)
* `srcdir_posix`: the source directory of this artifact in posix form (with `/` in the path)
* `builddir`: the build directory of this artifact in native form (with `/` under posix and `\` under windows)
* `builddir_posix`: the build directory of this artifact in posix form (with `/` in the path)

Specific build artifacts objects and their signatures:

* `DepsBuildArtifact(name: str, deps=[], provides=[], pkgs={})`: a meta build artifact that can used to group other build artifacts
* `BuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[])`: a generic build artifact with prepare commands and build commands
* `CMakeBuilArtifact(name: str, deps, srcObj, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={})`: a build artifact that uses `cmake` to be built
* `QMakeBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={})`: a build artifact relying on `qmake` / `make` to build
* `AutogenBuildArtifact(name: str, deps, srcObj, autogenArgs=[], noconfigure=False, isAutogen=True, configureArgs=[], runInstallDir=None, extraEnv={}, provides=[], pkgs={}`:
    a build artifact that relies on `autotools` / `make` to build
* `MesonBuildArtifact(name: str, deps, srcObj, mesonOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={})`: a build artifact that relies on `meson` to build
* `CustomCommandBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_src_cmds=[], prepare_cmds=[], build_target='all', install_target='install', builder='make')`: build artifact with the provided `builder` (can be `make`, `nmake` or `ninja`) with specified commands to prepare the source and build directory

