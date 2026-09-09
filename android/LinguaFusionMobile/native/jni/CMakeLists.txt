# Native build for on-device transcription.
#
# Produces one library, lingua_whisper, containing our JNI binding plus
# whisper.cpp and GGML compiled for the CPU. Only arm64-v8a and armeabi-v7a
# are built; see abiFilters in build.gradle for why.

cmake_minimum_required(VERSION 3.22.1)
project(lingua_whisper C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(WHISPER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../whisper.cpp)

# CPU only. Every GPU backend is off, and the matching sources are not even
# vendored -- turning one on here would fail at configure time rather than
# silently building something untested.
set(GGML_CPU     ON  CACHE BOOL "" FORCE)
set(GGML_CUDA    OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN  OFF CACHE BOOL "" FORCE)
set(GGML_OPENCL  OFF CACHE BOOL "" FORCE)
set(GGML_METAL   OFF CACHE BOOL "" FORCE)
set(GGML_BLAS    OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP  OFF CACHE BOOL "" FORCE)
set(GGML_RPC     OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS      OFF CACHE BOOL "" FORCE)

add_subdirectory(${WHISPER_DIR} ${CMAKE_CURRENT_BINARY_DIR}/whisper.cpp EXCLUDE_FROM_ALL)

add_library(lingua_whisper SHARED lingua_whisper.c)

target_include_directories(lingua_whisper PRIVATE
    ${WHISPER_DIR}/include
    ${WHISPER_DIR}/ggml/include)

find_library(LOG_LIB log)
target_link_libraries(lingua_whisper ${LOG_LIB} whisper)

# Size matters here: the library ships inside an APK people download over a
# phone connection. Strip what is not reachable, and hide every symbol except
# the JNI entry points, which the JNIEXPORT attribute keeps visible.
target_compile_options(lingua_whisper PRIVATE
    -O3 -fvisibility=hidden -ffunction-sections -fdata-sections)
target_link_options(lingua_whisper PRIVATE
    -Wl,--gc-sections -Wl,--exclude-libs,ALL)
