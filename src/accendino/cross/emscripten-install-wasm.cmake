#
#  Copyright (C) 2026 David Fort <contact@hardening-consulting.com>
#
#  Run with cmake -DBUILD_DIR=<dir> -P after "cmake --install" of an emscripten build: for an executable
#  install(TARGETS) only installs the .js loader, not the .wasm module it loads, so the program can't run from
#  the install tree. For each .js listed in the install manifest, this installs the .wasm of the same name built
#  in the build tree next to it.
#
if(NOT EXISTS "${BUILD_DIR}/install_manifest.txt")
  return()
endif()

file(STRINGS "${BUILD_DIR}/install_manifest.txt" installedFiles)
foreach(installed IN LISTS installedFiles)
  if(NOT installed MATCHES "\\.js$")
    continue()
  endif()

  get_filename_component(name "${installed}" NAME_WE)
  get_filename_component(destDir "${installed}" DIRECTORY)
  file(GLOB_RECURSE candidates "${BUILD_DIR}/${name}.wasm" "${BUILD_DIR}/*/${name}.wasm")
  list(FILTER candidates EXCLUDE REGEX "/CMakeFiles/")
  list(LENGTH candidates count)
  if(count EQUAL 1)
    file(INSTALL "${candidates}" DESTINATION "${destDir}")
  elseif(count GREATER 1)
    message(WARNING "several ${name}.wasm in ${BUILD_DIR}, not installing any: ${candidates}")
  endif()
endforeach()
