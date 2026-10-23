# CMakeLists.txt para Raspberry Pi Pico RP2040 Gamepad 1000Hz
cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(efootball_pico_1000hz C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(efootball_pico_1000hz
    pico_gamepad_1000hz.c
)

target_include_directories(efootball_pico_1000hz PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(efootball_pico_1000hz
    pico_stdlib
    tinyusb_device
    tinyusb_board
)

pico_enable_stdio_usb(efootball_pico_1000hz 1)
pico_enable_stdio_uart(efootball_pico_1000hz 0)

pico_add_extra_outputs(efootball_pico_1000hz)
