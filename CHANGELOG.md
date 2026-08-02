# _Accendino_ changelog

## 0.6.2

* fixed toolchain detection on MacOsX: it was identified as `Gcc` by default while `cc`/`gcc` are actually aliases for `clang`
* fixed some conditional from-sources builds under MacOsX
* force building `zlib` from sources on MacOsX, otherwise packages looking for its `.pc` file (eg `fido2`) fail to find it
* fixed `PKG_CONFIG_PATH` inherited from the host environment taking precedence over `PKG_CONFIG_LIBDIR`, causing system packages to be used instead of the ones we just built
* fixed build of FreeRDP on Ubuntu 22.04 by allowing `libcbor` and `fido2` to be forced to build from sources as the system versions are too old
* fixed `fido2` accendino file (missing package name argument, build as shared lib)
* added `--refreshSources` command line argument to force updating git sources to their upstream branch and rebuild artifacts (and their dependents) whose source actually changed
* added `--refresh` command line argument to force rebuilding the requested targets, even if they were already built

## 0.6.1

* added accendino files for `spdlog`, `stduuid`, `redis++`, `nlohmann/json`, `jwt-cpp`, `cpr`, `libressl` and `libyuv`
* added accendino files for wayvnc and its deps: `aml`, `libdrm`, `neatvnc`, `pixman-1`, `wayland`, `wayland-protocols`, `wlroots`, `xkbcommon`, `wayvnc`
* fixed version comparison
* `RemoteArchiveSource` now supports stripping the top-level directory from archives
* added `stdGitSourceFromOptions` as a shortcut function for accendino files
* fixed pkgconfig path handling: switched from `PKG_CONFIG_PATH` to `PKG_CONFIG_LIBDIR` so built artifacts take priority over system packages
* allow specifying a custom meson version to install in the build venv
* added `fido2` accendino file and integrated it into FreeRDP
* added `SDL3` accendino file and made FreeRDP use it

## 0.6.0

* added `sso-mib` accendino file
* changed build directory schema to `<arch-distrib>/<build-item>`
* fixed default deploy directory
* exposed more variables and functions to accendino files
* propagated use of `getOption` across accendino files to allow forcing builds from sources via a build options file
* added support for building ffmpeg+x264 under Windows: multiple targets in `CustomCommandBuild`, proper msys2 path handling
* added faac support for FreeRDP under Windows, improved mingw cross-compile settings (windres, missing C11 features)
* fixed include search to look in the directory of the including file
* reworked environment variable handling
* weston: don't build colord due to recent Python compatibility issues
* updated forgiare accendino files to point to forgiare repos, fixed pkgconfig directory
* updated GitHub CI workflows to install meson from PyPI

## 0.5.10 alpha 2

* fixed `LocalSource` when using symbolic links
* various fixes in windows packages manager (choco and inPath)
* MinGw is now a toolchain
* added build options support via a ini file that specifies build options
* make `MesonBuildArtifact` respect the parallel job parameter
* fixed a bug in prepared file comparison
* added `RemoteArchiveSource` to grab code from a zip or 7z remote file
* expose `mergePkgDeps` to accendino files
* added accendino files for `x264`

## 0.5.10 alpha 1

* updated accendino files for FreeBSD packages
* rebuild an artifact when one of its dependency has been rebuilt more recently
* included files can be included just once
* introduced the toolchain concept, that allows to setup the environment correctly for MSVC or other build chains.
  So `BuildArtifact` have the new `toolchainArtifacts` argument to give the artifacts to pull from the toolchain (only
  the `c` artifact by default)
* search for accendino files in local directory and then in pockets by default when passed on the command line
* introduce the msys2 system that allows to install package on msys2 and run scripts there. That allows to build
  ffmpeg under windows with MSVC (run configure script under msys2)
* adds a `RunInShell` special class that allows to specify some commands that must be run in a shell, so either the default
shell on unixes or msys2 on Windows
* added accendino files for `cairo`, `cjson`, `qfreerdp_platform`
* the windows build system has been reworked to generate and use powershell script, that allows to pass env variables from VS devEnv scripts


## 0.5.9

* added support for cross compilation
* splitted standard accendino files by build artifacts
* accendino automatically add .accendino if not present to included file names by `include()`
* `PKG_CONFIG_PATH` env variable was not set as it should during builds
* if not cross compiling `PATH` is updated during build to give access to generated binaries
* CMake builder now builds using `cmake --build` and `cmake --install`
* Meson builder now builds using `meson compile` and `meson install`
* Build artifacts and `Source` objects now come with their package needs, no need to add `cmake` for a cmake built artifact or `git`
* we try to avoid re-running prepare commands when it has been already prepared and nothing has changed since last preparation. The same applies
  when we've successfully built an artifact
* when run with `--debug` accendino generates scripts to help redoing a build by hand (with environment and build commands)
* introduced the `NativePath` class that allows to work with path that needs to be expressed as an OS native path, so with `/` for
  posix system or `\` under windows
* added support for `choco`, `pkg` and `pacman` package managers


## 0.5.0
Massive rework of the code base:

* reworked build artifacts to have a more generic workflow
* introduced `Source` objects (added `LocalSource`), the `GitSource` gains tons of options
* added the capability to include other _accendino_ files, also added include search paths
* many functions added and available in the _accendino_ files
* reworked the construction of the build plan and added conditional dependencies between built artifacts or platform packages
* added a proper manual documenting the _accendino_ files
* added a `resume from` capacity
* some sample _accendino_ files provided to build `freerdp`, `ogon` and `forgiare` version of `ogon`. These
  are good examples of what can be achieved with _Accendino_
* first version published on Pypy

## Initial version
Release of the first working version of _accendino_, it was able to build ogon
