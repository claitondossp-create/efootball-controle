"""
=============================================================================
FLYDIGI VADER 4 PRO - PROTOCOLO HID (WINDOWS)
=============================================================================
Engenharia reversa do protocolo de comunicação do Flydigi Vader 4 Pro.

O controle apresenta DUAS interfaces HID simultaneamente:
  1) Interface XInput (VID 0x045E / PID 0x028E) -> modo padrao Xbox 360
     - Lida pelo Windows como gamepad generico (pygame/xinput)
     - NAO expoe os botoes extras (M1-M4, C, Z, LM, RM, FN)

  2) Interface Proprietaria Flydigi (VID 0x37D7 / PID varia) -> canal de config
     - Expoe todos os botoes extras, gyro, LED, rumble avancado
     - Protocolo binario com magic bytes 5A A5 (igual ao Vader 5)
     - NECESSARIO para ler M1/M2/M3/M4 sem o Space Station

Baseado em:
  - tux-invader (Vader 5 Pro) por TJLawInOrbit - protocolo identico
  - SDL hidapi flydigi.c (Valve)
  - Analise de captura USB com USBPcap/Wireshark

=============================================================================
MAPA DE BYTES DO RELATORIO DE ENTRADA (INPUT REPORT, 29 bytes)
=============================================================================

  [0:2]   = Magic 5A A5
  [2]     = Comando (0xEF = input report)
  [3:11]  = Analogicos: LX, LY, RX, RY (int16_t LE, cada um = 4 bytes = 2 eixos x 2)
              Mais precisamente: offset 3 = LX (int16), 5 = LY, 7 = RX, 9 = RY
  [11]    = Byte de botoes 1: D-PAD + A/B/X/Y basicos
              bit 0 = UP, bit 1 = RIGHT, bit 2 = DOWN, bit 3 = LEFT
              bit 4 = A,  bit 5 = B,     bit 6 = SELECT, bit 7 = X
  [12]    = Byte de botoes 2: Y/START/LB/RB/LT/RT/L3/R3
              bit 0 = Y,  bit 1 = START, bit 2 = LB, bit 3 = RB
              bit 4 = LT (digital), bit 5 = RT (digital)
              bit 6 = L3, bit 7 = R3
  [13]    = Byte de botoes EXTRAS (os que queremos!):
              bit 0 = C   (botao frontal extra esquerdo)
              bit 1 = Z   (botao frontal extra direito)
              bit 2 = M1  (paddle traseiro superior esquerdo)
              bit 3 = M2  (paddle traseiro superior direito)
              bit 4 = M3  (paddle traseiro inferior esquerdo)
              bit 5 = M4  (paddle traseiro inferior direito)
              bit 6 = LM  (botao lateral esquerdo mouse)
              bit 7 = RM  (botao lateral direito mouse)
  [14]    = Byte de botoes especiais:
              bit 0 = FN, bit 1 = TURBO, bit 3 = HOME
  [15]    = Gatilho esquerdo analogico (0-255)
  [16]    = Gatilho direito analogico (0-255)
  [17:23] = Giroscopio XYZ (int16_t LE por eixo)
  [23:29] = Acelerometro XYZ (int16_t LE por eixo)

=============================================================================
HANDSHAKE PARA ATIVAR O "TEST MODE" (streaming de input)
=============================================================================
  Enviar sequencia: CMD 0x01, 0xA1, 0x02, 0x04 (cada com arg 0x02)
  Depois: CMD 0x11 com args 0x07 0xFF 0x01 0xFF 0xFF 0xFF (ativa streaming)
  Formato de cada pacote de comando: [5A A5 CMD ARGS... CHECKSUM 00...]
    - Checksum = soma de todos os bytes APOS o magic (5A A5)
    - Padded para 32 bytes com zeros

=============================================================================
"""

import struct
from dataclasses import dataclass, field

# --- VIDs e PIDs ---
# Interface XInput (o que aparece como gamepad padrao)
XINPUT_VID = 0x045E   # Microsoft
XINPUT_PID = 0x028E   # Xbox 360 Controller

# Interface proprietaria Flydigi (para botoes extras)
# NOTA: O Vader 4 Pro usa VID diferente do Vader 5 Pro (0x37D7)
# Precisamos capturar via USBPcap para confirmar o PID exato do Vader 4
FLYDIGI_VID = 0x37D7  # Vader 5 Pro (referencia)
# PIDs conhecidos:
#   0x2401 = Vader 5 Pro
#   A confirmar para Vader 4 Pro (provavelmente 0x2201 ou similar)

PACKET_SIZE = 32
MAGIC = b"\x5a\xa5"

CMD_INFO       = 0x01
CMD_TEST_MODE  = 0x11
CMD_RUMBLE     = 0x12
CMD_INPUT      = 0xEF

INPUT_REPORT_SIZE = 29

GYRO_DPS   = 2000.0 / 32768.0   # graus/segundo por unidade
ACCEL_G    = 1.0 / 4096.0       # G por unidade

# --- Mapa completo de botoes (byte_offset, mascara_bit, nome) ---
BUTTON_MAP = (
    # D-Pad e botoes principais
    (11, 0x01, "UP"),     (11, 0x02, "RIGHT"),  (11, 0x04, "DOWN"), (11, 0x08, "LEFT"),
    (11, 0x10, "A"),      (11, 0x20, "B"),      (11, 0x40, "SELECT"), (11, 0x80, "X"),
    (12, 0x01, "Y"),      (12, 0x02, "START"),  (12, 0x04, "LB"),   (12, 0x08, "RB"),
    (12, 0x10, "LT"),     (12, 0x20, "RT"),
    (12, 0x40, "L3"),     (12, 0x80, "R3"),
    # Botoes EXTRAS - o objetivo principal desta engenharia reversa!
    (13, 0x01, "C"),      (13, 0x02, "Z"),
    (13, 0x04, "M1"),     (13, 0x08, "M2"),     # Paddles traseiros superiores
    (13, 0x10, "M3"),     (13, 0x20, "M4"),     # Paddles traseiros inferiores
    (13, 0x40, "LM"),     (13, 0x80, "RM"),     # Botoes laterais mouse
    # Especiais
    (14, 0x01, "FN"),     (14, 0x02, "TURBO"),  (14, 0x08, "HOME"),
)
BUTTON_NAMES = tuple(name for _, _, name in BUTTON_MAP)


# --- Funcoes de construcao de pacotes de comando ---

def _checksum(body: bytes) -> int:
    """Checksum = soma de todos os bytes apos o magic 5A A5."""
    return sum(body[2:]) & 0xFF


def build_command(cmd: int, *args: int) -> bytes:
    """Constroi um pacote de comando de 32 bytes com magic, checksum e padding."""
    body = bytes([*MAGIC, cmd, *args])
    body += bytes([_checksum(body)])
    return body.ljust(PACKET_SIZE, b"\x00")


def test_mode_packet(enable: bool) -> bytes:
    return build_command(CMD_TEST_MODE, 0x07, 0xFF, int(enable), 0xFF, 0xFF, 0xFF)


def rumble_packet(strong: int, weak: int) -> bytes:
    """strong = motor baixa freq (esquerdo), weak = alta freq (direito). 0-255."""
    return build_command(CMD_RUMBLE, 0x06,
                         max(0, min(255, strong)),
                         max(0, min(255, weak)),
                         0x00, 0x00)


# Sequencia de handshake para ativar o streaming de input
HANDSHAKE_SEQUENCE = tuple(
    build_command(cmd, 0x02) for cmd in (0x01, 0xA1, 0x02, 0x04)
)


# --- Parser de relatorio de entrada ---

@dataclass
class InputState:
    left_stick:  tuple   # (x, y) int16, range -32768..32767
    right_stick: tuple
    left_trigger:  int   # 0..255
    right_trigger: int
    buttons: frozenset   # nomes dos botoes pressionados (ex: {"M1", "A"})
    gyro:   tuple        # (x, y, z) raw; * GYRO_DPS para graus/s
    accel:  tuple        # (x, y, z) raw; * ACCEL_G para G
    raw:    bytes        # pacote original para debug

    @property
    def paddles(self) -> frozenset:
        """Apenas os paddles traseiros e botoes extras."""
        return self.buttons & {"M1", "M2", "M3", "M4", "C", "Z", "LM", "RM", "FN"}

    def is_pressed(self, *names: str) -> bool:
        """Verifica se qualquer um dos botoes esta pressionado."""
        return bool(self.buttons & set(names))


def parse_input_report(data: bytes) -> InputState | None:
    """
    Parseia um relatorio de entrada bruto (29+ bytes) do canal proprietario.
    Retorna None se o pacote for invalido.
    """
    # Remove report ID se presente (alguns sistemas adicionam um byte antes do magic)
    if len(data) > 1 and data[0] != MAGIC[0] and data[1] == MAGIC[0]:
        data = data[1:]

    if len(data) < INPUT_REPORT_SIZE or data[:2] != MAGIC or data[2] != CMD_INPUT:
        return None

    lx, ly, rx, ry = struct.unpack_from("<4h", data, 3)
    gyro  = struct.unpack_from("<3h", data, 17)
    accel = struct.unpack_from("<3h", data, 23)

    pressed = frozenset(
        name for offset, mask, name in BUTTON_MAP
        if data[offset] & mask
    )

    return InputState(
        left_stick=(lx, ly),
        right_stick=(rx, ry),
        left_trigger=data[15],
        right_trigger=data[16],
        buttons=pressed,
        gyro=gyro,
        accel=accel,
        raw=bytes(data),
    )


if __name__ == "__main__":
    print("Protocolo Flydigi Vader 4 Pro carregado.")
    print(f"Botoes mapeados: {BUTTON_NAMES}")
    print(f"Magic bytes: {MAGIC.hex()}")
    print(f"Handshake: {len(HANDSHAKE_SEQUENCE)} pacotes")
