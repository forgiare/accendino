# cross file for macOS x86_64 binaries, built on a macOS Apple Silicon machine with Apple's clang

set(CMAKE_SYSTEM_NAME Darwin CACHE STRING "toolchain default")
set(CMAKE_SYSTEM_PROCESSOR x86_64 CACHE STRING "toolchain default")
set(CMAKE_OSX_ARCHITECTURES x86_64 CACHE STRING "toolchain default")

set(CMAKE_C_COMPILER clang CACHE STRING "toolchain default")
set(CMAKE_CXX_COMPILER clang++ CACHE STRING "toolchain default")
set(CMAKE_OBJC_COMPILER clang CACHE STRING "toolchain default")
set(CMAKE_OBJCXX_COMPILER clang++ CACHE STRING "toolchain default")

# the Homebrew of the build machine only has libraries for its own architecture
set(CMAKE_IGNORE_PREFIX_PATH /opt/homebrew CACHE STRING "toolchain default")
