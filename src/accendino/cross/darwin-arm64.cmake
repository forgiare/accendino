# cross file for macOS arm64 binaries, built on a macOS Intel machine with Apple's clang

set(CMAKE_SYSTEM_NAME Darwin CACHE STRING "toolchain default")
set(CMAKE_SYSTEM_PROCESSOR arm64 CACHE STRING "toolchain default")
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "toolchain default")

set(CMAKE_C_COMPILER clang CACHE STRING "toolchain default")
set(CMAKE_CXX_COMPILER clang++ CACHE STRING "toolchain default")
set(CMAKE_OBJC_COMPILER clang CACHE STRING "toolchain default")
set(CMAKE_OBJCXX_COMPILER clang++ CACHE STRING "toolchain default")

# the Homebrew of the build machine only has libraries for its own architecture
set(CMAKE_IGNORE_PREFIX_PATH /usr/local CACHE STRING "toolchain default")
