cmake_minimum_required(VERSION 3.16)
project(qthello LANGUAGES CXX)

find_package(Qt6 REQUIRED COMPONENTS Core WebSockets)
qt_standard_project_setup()

qt_add_executable(qthello main.cpp)
target_link_libraries(qthello PRIVATE Qt6::Core Qt6::WebSockets)
install(TARGETS qthello)
