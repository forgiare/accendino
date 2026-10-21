# a program whose build runs protoc: when cross compiling, protoc must be a binary for the build machine while
# libprotobuf is built for the target
cmake_minimum_required(VERSION 3.16)
project(crosstools CXX)

set(CMAKE_CXX_STANDARD 17)

find_package(Protobuf CONFIG REQUIRED)
find_program(PROTOC_EXECUTABLE protoc REQUIRED)

# protoc and libprotobuf versions must match
execute_process(COMMAND ${PROTOC_EXECUTABLE} --version OUTPUT_VARIABLE PROTOC_VERSION OUTPUT_STRIP_TRAILING_WHITESPACE)
message(STATUS "protoc: ${PROTOC_EXECUTABLE} (${PROTOC_VERSION}), libprotobuf: ${Protobuf_VERSION}")
string(REGEX REPLACE "^libprotoc " "" PROTOC_VERSION "${PROTOC_VERSION}")
# libprotobuf is either <protoc version>.0 or <c++ runtime major>.<protoc version>
if(NOT Protobuf_VERSION MATCHES "(^|\\.)${PROTOC_VERSION}(\\.|$)")
  message(FATAL_ERROR "protoc ${PROTOC_VERSION} doesn't match libprotobuf ${Protobuf_VERSION}")
endif()

add_custom_command(
  OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hello.pb.cc ${CMAKE_CURRENT_BINARY_DIR}/hello.pb.h
  COMMAND ${PROTOC_EXECUTABLE} --cpp_out=${CMAKE_CURRENT_BINARY_DIR} -I${CMAKE_CURRENT_SOURCE_DIR}
          ${CMAKE_CURRENT_SOURCE_DIR}/hello.proto
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/hello.proto
)

add_executable(crosstools main.cpp ${CMAKE_CURRENT_BINARY_DIR}/hello.pb.cc)
target_include_directories(crosstools PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(crosstools PRIVATE protobuf::libprotobuf)
install(TARGETS crosstools)
