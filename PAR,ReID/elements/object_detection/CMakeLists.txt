# CMake configuration for object detection & tracking element

cmake_minimum_required(VERSION 3.16)
project(mantis_object_detection VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include shared platform detection utilities
include(${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cmake/PlatformDetection.cmake)

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)

# GStreamer dependencies
pkg_check_modules(GSTREAMER REQUIRED gstreamer-1.0)
pkg_check_modules(GSTREAMER_APP REQUIRED gstreamer-app-1.0)
pkg_check_modules(GSTREAMER_RTSP REQUIRED gstreamer-rtsp-1.0)
pkg_check_modules(GSTREAMER_VIDEO REQUIRED gstreamer-video-1.0)

# ZeroMQ
pkg_check_modules(ZMQ REQUIRED libzmq)

# MessagePack (header-only ok)
find_package(msgpack QUIET)
if(NOT msgpack_FOUND)
    pkg_check_modules(MSGPACK msgpack)
    if(NOT MSGPACK_FOUND)
        find_path(MSGPACK_INCLUDE_DIR msgpack.hpp PATHS /usr/include /usr/local/include /opt/homebrew/include PATH_SUFFIXES msgpack)
        if(MSGPACK_INCLUDE_DIR)
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

# DeepStream SDK
set(DEEPSTREAM_DIR $ENV{DEEPSTREAM_SDK_ROOT_DIR})
if(NOT DEEPSTREAM_DIR)
    set(DEEPSTREAM_DIR "/opt/nvidia/deepstream/deepstream")
endif()

if(NOT EXISTS "${DEEPSTREAM_DIR}")
    message(FATAL_ERROR "DeepStream SDK not found. Set DEEPSTREAM_SDK_ROOT_DIR to your DeepStream installation path.")
endif()

find_path(NVDS_META_INCLUDE_DIR
    NAMES nvdsmeta.h
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES sources/includes includes include
)

find_path(GST_NVDS_META_INCLUDE_DIR
    NAMES gstnvdsmeta.h
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES sources/includes sources/gst-plugins/gst-nvdsmeta includes include
)

find_path(GST_NVINFER_INCLUDE_DIR
    NAMES nvbufsurface.h
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES sources/includes includes include sources/gst-plugins/gst-nvinfer
)

if(NOT NVDS_META_INCLUDE_DIR OR NOT GST_NVDS_META_INCLUDE_DIR)
    message(FATAL_ERROR "Failed to locate DeepStream metadata headers (nvdsmeta.h / gstnvdsmeta.h). "
        "Set DEEPSTREAM_SDK_ROOT_DIR to your DeepStream installation.")
endif()

set(DEEPSTREAM_INCLUDE_DIRS
    ${NVDS_META_INCLUDE_DIR}
    ${GST_NVDS_META_INCLUDE_DIR}
    ${DEEPSTREAM_DIR}/sources/includes
    ${DEEPSTREAM_DIR}/includes
    ${DEEPSTREAM_DIR}/include
)

if(GST_NVINFER_INCLUDE_DIR)
    list(APPEND DEEPSTREAM_INCLUDE_DIRS ${GST_NVINFER_INCLUDE_DIR})
endif()

find_library(NVDS_META_LIBRARY
    NAMES nvds_meta
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES lib lib64 lib/gst-plugins
)

find_library(NVDSGST_META_LIBRARY
    NAMES nvdsgst_meta
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES lib lib64 lib/gst-plugins
)

find_library(NVBUFSURFACE_LIBRARY
    NAMES nvbufsurface
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES lib lib64 lib/gst-plugins
)

find_library(NVBUFSURFTRANS_LIBRARY
    NAMES nvbufsurftransform
    HINTS ${DEEPSTREAM_DIR}
    PATH_SUFFIXES lib lib64 lib/gst-plugins
)

if(NOT NVDS_META_LIBRARY OR NOT NVDSGST_META_LIBRARY OR NOT NVBUFSURFACE_LIBRARY OR NOT NVBUFSURFTRANS_LIBRARY)
    message(FATAL_ERROR "Failed to locate required DeepStream libraries. "
        "Ensure DeepStream SDK development headers are installed.")
endif()

set(DEEPSTREAM_LIBRARY_DIRS
    ${DEEPSTREAM_DIR}/lib
    ${DEEPSTREAM_DIR}/lib64
    ${DEEPSTREAM_DIR}/lib/gst-plugins
)

add_executable(object-detection)

target_sources(object-detection PRIVATE
    main.cpp
    src/detection_app.cpp
    src/pipeline_builder.cpp
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/error.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/strict_config.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/moth_config_overrides.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/label_filter.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/gst_runner.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/pad_manager.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element/frame_message.cpp"
)

target_include_directories(object-detection PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/cpp/element"
    ${GSTREAMER_INCLUDE_DIRS}
    ${GSTREAMER_APP_INCLUDE_DIRS}
    ${GSTREAMER_RTSP_INCLUDE_DIRS}
    ${GSTREAMER_VIDEO_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
    ${MSGPACK_INCLUDE_DIRS}
    ${DEEPSTREAM_INCLUDE_DIRS}
)

target_link_directories(object-detection PRIVATE
    ${GSTREAMER_LIBRARY_DIRS}
    ${GSTREAMER_APP_LIBRARY_DIRS}
    ${GSTREAMER_RTSP_LIBRARY_DIRS}
    ${GSTREAMER_VIDEO_LIBRARY_DIRS}
    ${ZMQ_LIBRARY_DIRS}
    ${MSGPACK_LIBRARY_DIRS}
    ${DEEPSTREAM_LIBRARY_DIRS}
)

target_link_libraries(object-detection PRIVATE
    Threads::Threads
    ${GSTREAMER_LIBRARIES}
    ${GSTREAMER_APP_LIBRARIES}
    ${GSTREAMER_RTSP_LIBRARIES}
    ${GSTREAMER_VIDEO_LIBRARIES}
    ${ZMQ_LIBRARIES}
    ${NVDS_META_LIBRARY}
    ${NVDSGST_META_LIBRARY}
    ${NVBUFSURFACE_LIBRARY}
    ${NVBUFSURFTRANS_LIBRARY}
)

if(MSGPACK_LIBRARIES)
    target_link_libraries(object-detection PRIVATE ${MSGPACK_LIBRARIES})
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(object-detection PRIVATE nlohmann_json::nlohmann_json)
    target_compile_definitions(object-detection PRIVATE JSON_AVAILABLE=1)
else()
    target_compile_definitions(object-detection PRIVATE NO_JSON_SUPPORT=1)
endif()

target_compile_options(object-detection PRIVATE
    ${GSTREAMER_CFLAGS_OTHER}
    ${GSTREAMER_APP_CFLAGS_OTHER}
    ${GSTREAMER_RTSP_CFLAGS_OTHER}
    ${GSTREAMER_VIDEO_CFLAGS_OTHER}
    ${ZMQ_CFLAGS_OTHER}
    ${MSGPACK_CFLAGS_OTHER}
    $<$<CONFIG:Debug>:-g -O0>
    $<$<NOT:$<CONFIG:Debug>>:-O2>
    -Wno-deprecated-declarations
)

target_compile_definitions(object-detection PRIVATE
    GSTREAMER_AVAILABLE=1
    ZMQ_FOUND=1
    DEEPSTREAM_AVAILABLE=1
)

# Platform-specific optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64)")
    target_compile_options(object-detection PRIVATE -march=x86-64-v3)
endif()

# Configure platform-specific binary naming and output directory
configure_element_binary(object-detection "object_detection")

install(TARGETS object-detection RUNTIME DESTINATION bin COMPONENT runtime)

message(STATUS "Building Mantis Object Detection & Tracking element")
