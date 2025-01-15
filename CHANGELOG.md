# _Accendino_ changelog

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