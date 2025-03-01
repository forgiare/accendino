# _Accendino_ changelog

## 0.5.10

* updated accendino files for FreeBSD packages
* rebuild an artifact when one of its dependency has been rebuilt more recently


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