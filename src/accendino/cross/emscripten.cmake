#
#  Copyright (C) 2026 David Fort <contact@hardening-consulting.com>
#
#  Toolchain file for emscripten targets, it wraps emsdk's own toolchain file (what emcmake does). $EMSDK and
#  $EMSDK_NODE are set by accendino's emscripten toolchain.
#
include("$ENV{EMSDK}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake")

# Emscripten.cmake only searches libraries, headers and packages in the emscripten sysroot (the find root path
# modes are ONLY), add the deploy prefix so that the artifacts we have built are found
if(CMAKE_INSTALL_PREFIX)
  list(APPEND CMAKE_FIND_ROOT_PATH "${CMAKE_INSTALL_PREFIX}")
endif()

# run cross compiled programs (try_run, tests) with node, like emcmake does
if(NOT CMAKE_CROSSCOMPILING_EMULATOR AND DEFINED ENV{EMSDK_NODE})
  set(CMAKE_CROSSCOMPILING_EMULATOR "$ENV{EMSDK_NODE}" CACHE FILEPATH "toolchain default")
endif()

# there are no shared libraries in a WebAssembly program
set(BUILD_SHARED_LIBS OFF CACHE BOOL "toolchain default")
