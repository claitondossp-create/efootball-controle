# ⚡ Firmware C Nativo RP2040 (1000Hz Ultra-Baixa Latência)

Este módulo substitui o interpretador CircuitPython por um executável nativo em C/C++ compilado diretamente para os dois núcleos ARM Cortex-M0+ do Raspberry Pi Pico RP2040.

### 🌟 Vantagens sobre CircuitPython:
* **Taxa de Polling de 1000Hz (1ms cravado)** nativa sem garbage collection.
* **Comunicação serial direta DMA**: Buffer em anel em nível de hardware.
* **Menor jitter de clock**: Injeção da mira 360° no eFootball com latência inferior a $0.1$ms.

### 🔨 Como Compilar e Gravar (Opção 1: Arquivo Pronto UF2):
1. Segure o botão branco `BOOTSEL` do seu Raspberry Pi Pico enquanto conecta o cabo USB no computador.
2. O Pico abrirá uma pasta como pendrive chamada `RPI-RP2`.
3. Arraste o arquivo compilado `.uf2` para dentro dessa pasta. O Pico reiniciará instantaneamente como Gamepad HID nativo!

### ⚙️ Como Compilar do Código Fonte (Pico SDK):
```bash
mkdir build && cd build
cmake ..
cmake --build .
```
Isso gerará o binário `efootball_pico_1000hz.uf2`.
