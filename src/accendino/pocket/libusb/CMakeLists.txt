# Builds libusb with libusb-cmake (LIBUSB_SOURCE_DIR) and installs the libusb-1.0.pc that the autotools build
# installs and libusb-cmake doesn't: packages like FreeRDP put libusb-1.0 in the requirements of their own .pc.
cmake_minimum_required(VERSION 3.16)
project(libusb-accendino LANGUAGES C)

if(NOT LIBUSB_SOURCE_DIR)
    message(FATAL_ERROR "LIBUSB_SOURCE_DIR must be set to the libusb-cmake sources")
endif()

add_subdirectory("${LIBUSB_SOURCE_DIR}" libusb)

get_directory_property(LIBUSB_PC_VERSION DIRECTORY "${LIBUSB_SOURCE_DIR}" DEFINITION PROJECT_VERSION)
configure_file(libusb-1.0.pc.in libusb-1.0.pc @ONLY)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/libusb-1.0.pc" DESTINATION lib/pkgconfig)
