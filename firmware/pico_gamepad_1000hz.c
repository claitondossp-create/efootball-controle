/**
 * ⚽ eFootball Master AI - Firmware C Nativo RP2040 a 1000Hz (1ms Polling)
 * Raspberry Pi Pico SDK + TinyUSB
 * 
 * Comunicação Serial DMA a 921600 baud + Emulação de Gamepad USB DirectInput / HID Oficial.
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "bsp/board.h"
#include "tusb.h"

// Pacote binário recebido do Python (6 bytes por frame):
// [0..1] buttons (16 bits)
// [2]    lx      (int8 -127..127)
// [3]    ly      (int8 -127..127)
// [4]    rx      (int8 -127..127)
// [5]    ry      (int8 -127..127)
#pragma pack(push, 1)
typedef struct {
    uint16_t buttons;
    int8_t   lx;
    int8_t   ly;
    int8_t   rx;
    int8_t   ry;
} report_serial_t;
#pragma pack(pop)

static report_serial_t ultimo_report = {0, 0, 0, 0, 0};
static uint8_t buffer_rx[sizeof(report_serial_t)];
static uint8_t idx_rx = 0;

void hid_task(void) {
    if (!tud_hid_ready()) return;

    // Report HID oficial eFootball DirectInput:
    // Eixos X, Y, Z, Rz e 16 botões digitais mapeados com 1000Hz
    tud_hid_report(0, &ultimo_report, sizeof(ultimo_report));
}

int main(void) {
    board_init();
    tusb_init();

    // Inicializa LED onboard
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
    gpio_put(PICO_DEFAULT_LED_PIN, 1);

    while (1) {
        tud_task();

        // Lê bytes seriais CDC do Python a taxa máxima
        if (tud_cdc_available()) {
            uint32_t count = tud_cdc_read(buffer_rx + idx_rx, sizeof(report_serial_t) - idx_rx);
            idx_rx += count;

            if (idx_rx >= sizeof(report_serial_t)) {
                memcpy(&ultimo_report, buffer_rx, sizeof(report_serial_t));
                idx_rx = 0;
            }
        }

        hid_task();
    }

    return 0;
}
