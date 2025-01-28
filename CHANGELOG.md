# _Accendino_ changelog

## 0.6.0

* add missing dependencies on Mac for FreeRDP deps
* added support for cross compilation
* splitted standard accendino files by build artifact
* accendino automatically add .accendino if not present to included file names by `include()`
* `PKG_CONFIG_PATH` env variable was not set as it should during builds
* CMake builder now builds using `cmake --build` and `cmake --install`
* Meson builder now builds using `meson compile` and `meson install`
* Build artifacts and `Source` objects now come with their package needs, no need to add `cmake` for a cmake built artifact or `git`


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