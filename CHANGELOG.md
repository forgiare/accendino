# _Accendino_ changelog

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
