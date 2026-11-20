# Builds and installs Sentry's crashpad fork (CRASHPAD_SOURCE_DIR), replacing its crashpad-config.cmake that is
# broken with the system zlib (it configures crashpad::zlib before the targets file creates it), doesn't look
# for libcurl on Linux and doesn't export include/crashpad as an include directory.
cmake_minimum_required(VERSION 3.12)
project(crashpad-accendino LANGUAGES C CXX)

if(NOT CRASHPAD_SOURCE_DIR)
    message(FATAL_ERROR "CRASHPAD_SOURCE_DIR must be set to the crashpad sources")
endif()

add_subdirectory("${CRASHPAD_SOURCE_DIR}" crashpad)

# install rules of subdirectories run in the order they're added, so the config installed by config/ overwrites
# the crashpad one
add_subdirectory(config)
