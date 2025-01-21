# Accendino manual

## Command line invocation

_Accendino_ accepts the following command line arguments:

* `--prefix=<dir>`: the directory where to install generated items
* `-h|--help`: show an help message
* `-v|--version`: display the version
* `--debug`: show extra debugging message during build
* `--no-packages`: don't do any platform packages checks
* `--targets=<targets>`: a coma separated list of targets to build
* `--build-type=<build type>`: kind of build, can be `release` or `debug`
* `--work-dir=<dir>`: the directory where builds and sources will be stored
* `--resume-from=<target>`: resume the build starting at this target
* `--project=<name>`: sets a project name (used to store all items of this project in the same tree)
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

* `DEFAULT_TARGETS` : contains the default build artifacts to build when no target is given on the command line (coma separated string);
* `ARTIFACTS` : contains a list of build artifacts;
* `PROJECT` : an optional project name, it allows to store all the build items (sources and binaries) in a specific directory;

When interpreting the source file _Accendino_ provides some useful variables and functions to the source file:

### Variables

* `accendinoVersion`: the version of _Accendino_
* `distribId`: the distribution id can be `Debian`, `Ubuntu`, `redhat`, `Fedora`, `Windows`, `Darwin` (for MacOsX)
* `distribVersion`: the version associated with the distribution in `distribId`
* `UBUNTU_LIKE`: contains `Debian|Ubuntu` a shortcut for dpkg based distributions
* `REDHAT_LIKE`: contains `Fedora|Redhat` a shortcut for rpm based distributions

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
* `include(name : str) -> bool`: allows to include another _Accendino_ source file. _Accendino_ will search for this file in the following
    locations: `.`, `pocket`, paths given in the `ACCENDINO_PATH` env variable, and finally in the pockets directory of _Accendino_
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
    dependency.
* `logging`: an export of the `zenlog` module. You can use it to log your messages with for instance `logging.debug('hello from the accendino file')`


### Sources

`Source` objects are invoked to checkout your code, we have this kinds available:

* `GitSource(url: str, branch: str, depth: int = 1, shallow_submodules: bool = False, recurse_submodules: bool = False)` : a source that checks out the code from `git`. Parameters mimick the `git` command arguments;
* `LocalSource(srcdir : str, do_symlink : bool = False)` : a source that uses code stored in a local directory. If `do_symlink` is true, the code is just symlinked in the _Accendino_ sources directory, otherwise the whole source tree is copied

### Build artifacts

All build artifacts share the same parameters:

* `name : str`: name of this artifact
* `deps : List[str]`: a list of the name of build artifacts that this artifact depends on for the build
* `srcObj : accendino.sources.Source`: a [`accendino.sources.Source`](#sources) object that will checkout your sources
* `provides : List[str] | str`: a list of build artifacts that this artifact provides. For instance you can have a `freerdp2` artifact that provides `freerdp`
* `pkgs : Dict[str, List[str]]`: a dictionary of platform packages dependencies

When giving commands, you can use these format string they will be replaced by their respective values:

* `prefix`: the `--prefix` argument given to _Accendino_
* `libdir`: where libraries are usually built and installed (`lib` on most places, `lib64` on redhat like systems)
* `srcdir`: the source directory of this artifact. Useful to run commands in the source tree (for projects that needs `autogen.sh` / `bootstrap`)
* `builddir`: the build directory of this artifact

Specific build artifacts objects and their signatures:

* `DepsBuildArtifact(name: str, deps=[], provides=[], pkgs={})`: a meta build artifact that can used to group other build artifacts
* `BuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_cmds = [], build_cmds=[])`: a generic build artifact with prepare commands and build commands
* `CMakeBuilArtifact(name: str, deps, srcObj, cmakeOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={})`: a build artifact that uses `cmake` to be built
* `QMakeBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={})`: a build artifact relying on `qmake` / `make` to build
* `AutogenBuildArtifact(name: str, deps, srcObj, autogenArgs=[], noconfigure=False, isAutogen=True, configureArgs=[], runInstallDir=None, extraEnv={}, provides=[], pkgs={}`:
    a build artifact that relies on `autotools` / `make` to build
* `MesonBuildArtifact(name: str, deps, srcObj, mesonOpts=[], parallelJobs=True, extraEnv={}, provides=[], pkgs={})`: a build artifact that relies on `meson` to build
* `CustomCommandBuildArtifact(name: str, deps, srcObj, extraEnv={}, provides=[], pkgs={}, prepare_src_cmds=[], prepare_cmds=[], build_target='all', install_target='install')`: build artifact with `make` that specified commands to prepare the source and build directory

