if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(CRASHPAD_NEEDS_CURL ON)
else()
    set(CRASHPAD_NEEDS_CURL OFF)
endif()

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
configure_package_config_file(crashpad-config.cmake.in crashpad-config.cmake
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/crashpad"
)
# both configs are usually generated in the same second, the install would skip ours as up to date
install(CODE "file(REMOVE \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}/cmake/crashpad/crashpad-config.cmake\")")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/crashpad-config.cmake" DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/crashpad")
