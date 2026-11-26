# Builds protobuf-c (PROTOBUF_C_SOURCE_DIR) with MSVC and the DLL runtime (/MD): its static build forces the static
# runtime (/MT), expecting protobuf's default static runtime, while protobuf.accendino builds protobuf with
# protobuf_MSVC_STATIC_RUNTIME=OFF like the other libraries.
cmake_minimum_required(VERSION 3.15)
project(protobuf-c-accendino LANGUAGES C CXX)

if(NOT PROTOBUF_C_SOURCE_DIR)
    message(FATAL_ERROR "PROTOBUF_C_SOURCE_DIR must be set to the protobuf-c sources")
endif()

add_subdirectory("${PROTOBUF_C_SOURCE_DIR}/build-cmake" protobuf-c)

# the MSVC_RUNTIME_LIBRARY property of a target wins over the CMAKE_MSVC_RUNTIME_LIBRARY that initialized it
get_property(protobuf_c_targets DIRECTORY "${PROTOBUF_C_SOURCE_DIR}/build-cmake" PROPERTY BUILDSYSTEM_TARGETS)
foreach(target IN LISTS protobuf_c_targets)
    get_target_property(target_type ${target} TYPE)
    if(NOT target_type STREQUAL "UTILITY" AND NOT target_type STREQUAL "INTERFACE_LIBRARY")
        set_target_properties(${target} PROPERTIES MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
    endif()
endforeach()
