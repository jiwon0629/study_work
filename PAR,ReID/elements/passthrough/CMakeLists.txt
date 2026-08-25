# CMakeLists.txt for Passthrough element

cmake_minimum_required(VERSION 3.16)
project(mantis_passthrough VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include shared platform detection utilities
include(${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cmake/PlatformDetection.cmake)

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)

# GStreamer (core + app)
pkg_check_modules(GSTREAMER REQUIRED gstreamer-1.0)
pkg_check_modules(GSTREAMER_APP REQUIRED gstreamer-app-1.0)

# ZeroMQ
pkg_check_modules(ZMQ REQUIRED libzmq)

# MessagePack (header-only ok)
find_package(msgpack QUIET)
if(NOT msgpack_FOUND)
    pkg_check_modules(MSGPACK msgpack)
    if(NOT MSGPACK_FOUND)
        find_path(MSGPACK_INCLUDE_DIR msgpack.hpp PATHS /usr/include /usr/local/include /opt/homebrew/include PATH_SUFFIXES msgpack)
        if(MSGPACK_INCLUDE_DIR)
            message(STATUS "Found header-only MessagePack at ${MSGPACK_INCLUDE_DIR}")
            set(MSGPACK_FOUND TRUE)
            set(MSGPACK_INCLUDE_DIRS ${MSGPACK_INCLUDE_DIR})
            set(MSGPACK_LIBRARIES "")
        else()
            message(FATAL_ERROR "MessagePack not found. Please install msgpack-cxx.")
        endif()
    endif()
endif()

# nlohmann/json (optional)
find_package(nlohmann_json QUIET)

add_executable(passthrough)

target_sources(passthrough PRIVATE
    main.cpp
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/error.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/strict_config.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/moth_config_overrides.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/gst_runner.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/pad_manager.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/frame_message.cpp"
)

target_include_directories(passthrough PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element"
    ${GSTREAMER_INCLUDE_DIRS}
    ${GSTREAMER_APP_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
    ${MSGPACK_INCLUDE_DIRS}
)

target_link_directories(passthrough PRIVATE
    ${GSTREAMER_LIBRARY_DIRS}
    ${GSTREAMER_APP_LIBRARY_DIRS}
    ${ZMQ_LIBRARY_DIRS}
    ${MSGPACK_LIBRARY_DIRS}
)

target_link_libraries(passthrough PRIVATE
    Threads::Threads
    ${GSTREAMER_LIBRARIES}
    ${GSTREAMER_APP_LIBRARIES}
    ${ZMQ_LIBRARIES}
)

if(MSGPACK_LIBRARIES)
    target_link_libraries(passthrough PRIVATE ${MSGPACK_LIBRARIES})
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(passthrough PRIVATE nlohmann_json::nlohmann_json)
    target_compile_definitions(passthrough PRIVATE JSON_AVAILABLE=1)
else()
    target_compile_definitions(passthrough PRIVATE NO_JSON_SUPPORT=1)
endif()

target_compile_options(passthrough PRIVATE
    ${GSTREAMER_CFLAGS_OTHER}
    ${GSTREAMER_APP_CFLAGS_OTHER}
    ${ZMQ_CFLAGS_OTHER}
    ${MSGPACK_CFLAGS_OTHER}
    $<$<CONFIG:Debug>:-g -O0>
    $<$<NOT:$<CONFIG:Debug>>:-O2>
)

target_compile_definitions(passthrough PRIVATE
    GSTREAMER_AVAILABLE=1
    ZMQ_FOUND=1
)

# Platform-specific optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64)")
    target_compile_options(passthrough PRIVATE -march=x86-64-v3)
endif()

# Configure platform-specific binary naming and output directory
configure_element_binary(passthrough "passthrough")

install(TARGETS passthrough RUNTIME DESTINATION bin COMPONENT runtime)

message(STATUS "Building Mantis Passthrough element")
