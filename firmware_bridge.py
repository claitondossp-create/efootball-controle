import sys
import time
import math
import struct
import serial
import serial.tools.list_ports
import pygame
import keyboard

# ==============================================================================
# CONFIGURAÇÃO DE PORTA E HARDWARE
# ==============================================================================

def encontrar_porta_rp2040():
    """Detecta automaticamente a porta de dados do RP2040."""
    portas = list(serial.tools.list_ports.comports())
    for p in portas:
        if '239A' in p.hwid:
            # Interface 2 é a porta CDC Data criada pelo boot.py
            if 'MI_02' in p.hwid or 'x.2' in p.hwid:
                return p.device
    return 'COM9'  # Fallback padrão

PORTA_RP2040 = encontrar_porta_rp2040()
BAUD_RATE = 115200

# Mapeamento padrão XInput / DInput no Pygame
BTN_A = 0          # Passe curto (X no PlayStation / A no Xbox)
BTN_B = 1          # Cruzamento / Carrinho (Bolinha / B)
BTN_X = 2          # Chute / Bote (Quadrado / X)
BTN_Y = 3          # Lançamento em profundidade (Triângulo / Y)
BTN_LB = 4         # Troca de cursor / Modificador (L1 / LB)
BTN_RB = 5         # Corrida / Comando Fenomenal (R1 / RB)
BTN_BACK = 6       # Select / Back
BTN_START = 7      # Start
BTN_L3 = 8         # Clique analógico esquerdo
BTN_R3 = 9         # Clique analógico direito
BTN_LT_DIGITAL = 10# Gatilho L2 / LT (se lido como botão digital)
BTN_RT_DIGITAL = 11# Gatilho R2 / RT (se lido como botão digital)

# Atalhos de Teclado (Configurados no Flydigi Space Station para M1..M4, C, Z)
# Aceita: caractere ('8'), nome numpad ('num 8') e ScanCode exato do hardware (72)
TECLAS_DOUBLE_TOUCH_DIR   = ['8', 'num 8', 72]  # M1 no Vader 4 Pro
TECLAS_DOUBLE_TOUCH_ESQ   = ['9', 'num 9', 73]  # M2 no Vader 4 Pro
TECLAS_SUPER_CANCEL       = ['7', 'num 7', 71]  # M3 no Vader 4 Pro (R1 + R2)
TECLAS_FAKE_SHOT          = ['0', 'num 0', 82]  # C no Vader 4 Pro (Quadrado -> X)
TECLAS_PRESSAO_COORDENADA = ['6', 'num 6', 77]  # M4 no Vader 4 Pro (L2 + Segundo Homem)

# ==============================================================================
# FUNÇÕES DE COMUNICAÇÃO SERIAL (1000Hz)
# ==============================================================================

def clamp_axis(valor):
    """Converte valor normalizado (-1.0 a 1.0) para inteiro assinado de 8 bits (-127 a 127)."""
    return max(-127, min(127, int(valor * 127)))

def enviar_relatorio(ser, buttons, lx, ly, rx, ry):
    """
    Empacota e envia 6 bytes:
    - 2 bytes (uint16_t) para 16 botões
    - 4 bytes (int8_t) para os eixos: Left Stick X, Left Stick Y, Right Stick X, Right Stick Y
    """
    pacote = struct.pack('<Hbbbb', buttons, clamp_axis(lx), clamp_axis(ly), clamp_axis(rx), clamp_axis(ry))
    ser.write(pacote)

# ==============================================================================
# MACROS DINÂMICAS DE ALTA VELOCIDADE
# ==============================================================================

def macro_double_touch(ser, buttons, lx, ly, lado_direito=True):
    """
    Calcula dinamicamente a direção em 360° do Analógico Esquerdo via atan2
    e injeta o toque perpendicular de 90° no Analógico Direito para o Toque Duplo perfeito.
    """
    magnitude = math.hypot(lx, ly)
    if magnitude < 0.20:
        return  # Jogador parado, ignora para não cometer erro

    # Ângulo atual de corrida em radianos
    angulo_corrida = math.atan2(ly, lx)

    # 90 graus (pi/2) para o lado desejado
    desvio = (math.pi / 2) if lado_direito else -(math.pi / 2)
    angulo_drible = angulo_corrida + desvio

    rx_drible = math.cos(angulo_drible)
    ry_drible = math.sin(angulo_drible)

    # Fase 1: Toque no Analógico Direito (45ms) com Esquerdo neutro
    enviar_relatorio(ser, buttons, 0, 0, rx_drible, ry_drible)
    time.sleep(0.045)

    # Fase 2: Pausa ultracurta de transição mecânica (15ms)
    enviar_relatorio(ser, buttons, 0, 0, 0, 0)
    time.sleep(0.015)

    # Fase 3: Confirmação da direção original da corrida no Analógico Esquerdo (80ms)
    enviar_relatorio(ser, buttons, lx, ly, 0, 0)
    time.sleep(0.080)

def macro_fake_shot(ser, buttons, lx, ly):
    """Chute Falso (Fake Shot): Dispara Chute (Quadrado) e corta com Passe (X) mantendo a corrida."""
    # Fase 1: Quadrado pressionado por 40ms
    btn_chute = buttons | (1 << BTN_X)
    enviar_relatorio(ser, btn_chute, lx, ly, 0, 0)
    time.sleep(0.040)

    # Fase 2: Solta Quadrado e aperta X por 60ms
    btn_passe = (buttons & ~(1 << BTN_X)) | (1 << BTN_A)
    enviar_relatorio(ser, btn_passe, lx, ly, 0, 0)
    time.sleep(0.060)

def macro_super_cancel(ser, buttons, lx, ly):
    """Super Cancel Instantâneo de 1-frame (R1 + R2) para destravar do trilho de corrida."""
    # Ativa R1 (BTN_RB) e R2 (bit 11) simultaneamente
    btn_cancel = buttons | (1 << BTN_RB) | (1 << 11)
    enviar_relatorio(ser, btn_cancel, lx, ly, 0, 0)
    time.sleep(0.090)

def macro_pressao_coordenada(ser, buttons, lx, ly):
    """Cercar com L2 + Chamar Segundo Homem sincronizado no mesmo milissegundo."""
    # Ativa L2 (bit 10) e Segundo Homem (Quadrado/Bolinha - bit 2)
    btn_press = buttons | (1 << 10) | (1 << BTN_X)
    enviar_relatorio(ser, btn_press, lx, ly, 0, 0)
    time.sleep(0.120)

# ==============================================================================
# LOOP PRINCIPAL DO BRIDGE
# ==============================================================================

def main():
    print("="*60)
    print(" EFOOTBALL CONTROLLER BRIDGE - RP2040 + FLYDIGI VADER 4 PRO")
    print("="*60)
    print(f"[*] Conectando à porta serial de dados do RP2040: {PORTA_RP2040}...")

    try:
        ser = serial.Serial(PORTA_RP2040, BAUD_RATE, timeout=0)
        print("[OK] Conectado ao RP2040 com sucesso!")
    except Exception as e:
        print(f"[ERRO] Não foi possível abrir {PORTA_RP2040}: {e}")
        sys.exit(1)

    pygame.init()
    pygame.joystick.init()

    # Procura o controle de entrada (Vader 4 Pro)
    vader = None
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        # Ignora o próprio emulador CircuitPython para não entrar em loop de feedback
        if 'CircuitPython' not in j.get_name():
            vader = j
            print(f"[OK] Controle de entrada selecionado: [{i}] {vader.get_name()}")
            break

    if not vader:
        print("[AVISO] Flydigi Vader 4 Pro não detectado ainda.")
        print("[*] Aguardando conexão do controle... Plugue o Dongle ou cabo.")
        while not vader:
            pygame.joystick.quit()
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                j = pygame.joystick.Joystick(i)
                if 'CircuitPython' not in j.get_name():
                    vader = j
                    print(f"[OK] Vader 4 Pro conectado: {vader.get_name()}")
                    break
            time.sleep(1)

    print("\n[PRONTO] Sistema operacional a 1000Hz!")
    print("Atalhos Ativos (linha topo OU numpad):")
    print(f" - Teclas {TECLAS_DOUBLE_TOUCH_DIR}: Double Touch Direita")
    print(f" - Teclas {TECLAS_DOUBLE_TOUCH_ESQ}: Double Touch Esquerda")
    print(f" - Teclas {TECLAS_SUPER_CANCEL}: Super Cancel Instantâneo")
    print(f" - Teclas {TECLAS_FAKE_SHOT}: Fake Shot Instantâneo")
    print(f" - Teclas {TECLAS_PRESSAO_COORDENADA}: Pressão Coordenada (L2 + 2º Homem)")
    print("\nPressione Ctrl+C no terminal para encerrar.")

    try:
        while True:
            pygame.event.pump()

            # Leitura dos analógicos
            lx = vader.get_axis(0)
            ly = vader.get_axis(1)
            rx = vader.get_axis(2) if vader.get_numaxes() > 2 else 0.0
            ry = vader.get_axis(3) if vader.get_numaxes() > 3 else 0.0

            # Monta a máscara de bits dos botões
            buttons = 0
            for b in range(min(16, vader.get_numbuttons())):
                if vader.get_button(b):
                    buttons |= (1 << b)

            # Gatilhos de Macros via Teclado (mapeados no Flydigi Space Station)
            # Usa any() para aceitar tanto linha de cima quanto numpad
            if any(keyboard.is_pressed(t) for t in TECLAS_DOUBLE_TOUCH_DIR):
                macro_double_touch(ser, buttons, lx, ly, lado_direito=True)
                continue

            if any(keyboard.is_pressed(t) for t in TECLAS_DOUBLE_TOUCH_ESQ):
                macro_double_touch(ser, buttons, lx, ly, lado_direito=False)
                continue

            if any(keyboard.is_pressed(t) for t in TECLAS_FAKE_SHOT):
                macro_fake_shot(ser, buttons, lx, ly)
                continue

            if any(keyboard.is_pressed(t) for t in TECLAS_SUPER_CANCEL):
                macro_super_cancel(ser, buttons, lx, ly)
                continue

            if any(keyboard.is_pressed(t) for t in TECLAS_PRESSAO_COORDENADA):
                macro_pressao_coordenada(ser, buttons, lx, ly)
                continue

            # Modo normal passthrough em tempo real (1000Hz)
            enviar_relatorio(ser, buttons, lx, ly, rx, ry)
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[INFO] Bridge encerrado pelo usuário.")
        ser.close()

if __name__ == '__main__':
    main()
