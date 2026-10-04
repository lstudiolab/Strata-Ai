cmake_minimum_required(VERSION 3.16)
project(StrataAI LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_executable(strata
 src/main.cpp
 src/Model.cpp
)
target_include_directories(strata PRIVATE include)
if(NOT MSVC)
 target_compile_options(strata PRIVATE -O2 -Wall -Wextra -Wpedantic)
endif()
