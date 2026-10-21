"""
================================================================================
   EFOOTBALL MASTER AI & CONTROLLER HUB - ALL-IN-ONE (ARQUIVO MESTRE ÚNICO)
================================================================================
Projeto Unificado de Assistência Tática em Tempo Real para eFootball (PC).
Funciona tanto na versão MICROSOFT STORE / XBOX APP quanto na versão STEAM!

Recursos integrados neste único arquivo:
1. Motor de Visão Computacional a 60 FPS (MSS + OpenCV):
   - Detecção do Radar (Mandante Verde vs Visitante Vermelho)
   - Detecção Automática de Time via Anel Amarelo do Cursor
   - Rastreamento Cinemático com Filtro EMA e interceptação analítica de Bhaskara
   - Curva Balística Não Linear com cálculo milimétrico da barra de força
   - Detecção de Linha de Impedimento Oficial IFAB
   - Cone Dinâmico de Bloqueio (chaveamento automático para passe aéreo cavado)
   - Seleção Inteligente de Cruzamento (Rasteiro, Cabeça/Peito ou Fenomenal)

2. Injeção de Hardware Direta via DirectX SendInput (user32.dll):
   - Envia Scancodes nativos de hardware diretamente para a janela do eFootball
   - Compatível com a versão Microsoft Store sem depender de drivers externos
   - Dispara W (Lançamento), A (Cruzamento), D (Chute), S (Passe), Q (Cavada), etc.

3. Ponte de Hardware Opcional (RP2040 1000Hz):
   - Conecta automaticamente à placa Raspberry Pi Pico na porta serial se conectada

4. Hook Global de Teclado para Flydigi Space Station:
   - Captura instantânea dos botões Z, C, M1, M2, M3, M4
   - Sistema de Edge Trigger (1 disparo por toque, sem repetição indesejada)

5. Interface Gráfica Interativa (Tkinter):
   - Monitor de teclas em tempo real com diagnóstico visual
   - Remapeamento de atalhos em tempo real
   - Visualização HUD OpenCV com zoom 3x do radar e alvos futuros
================================================================================
"""

import os
import sys
import time
import math
import json
import struct
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import mss
import numpy as np
import pygame
import serial
import serial.tools.list_ports
import keyboard
import pydirectinput

pydirectinput.PAUSE = 0
pydirectinput.FAILSAFE = False

# Força line-buffering para prints imediatos no terminal
sys.stdout.reconfigure(line_buffering=True)

# ==============================================================================
# 1. INJEÇÃO DE ENTRADAS NATIVAS DIRECTX (WINDOWS SENDINPUT + PYDIRECTINPUT)
# ==============================================================================
PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)
    ]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

# Scancodes de hardware DirectX (Padrão Oficial eFootball PC):
SCAN_W = 0x11  # Lançamento em Profundidade (Through Ball / Botão Y)
SCAN_D = 0x20  # Cruzamento / Passe Longo (Lofted Pass / Botão B)
SCAN_A = 0x1E  # Chute / Finalização / Segundo Homem (Shoot / Botão X)
SCAN_S = 0x1F  # Passe Curto (Short Pass / Botão A)
SCAN_Q = 0x10  # Troca de Cursor / Modificador Cavado (Botão LB / L1)
SCAN_E = 0x12  # Sprint / Correr (Botão RT / R2)
SCAN_C = 0x2E  # Controle Especial (Botão RB / R1)
SCAN_Z = 0x2C  # Controle Manual (Botão LT / L2)
SCAN_NUM8 = 0x48  # Analógico Direito Cima (Numpad 8 - Drible)
SCAN_NUM2 = 0x50  # Analógico Direito Baixo (Numpad 2 - Drible)

SCAN_PARA_TECLA = {
    SCAN_W: 'w',
    SCAN_D: 'd',
    SCAN_A: 'a',
    SCAN_S: 's',
    SCAN_Q: 'q',
    SCAN_E: 'e',
    SCAN_C: 'c',
    SCAN_Z: 'z',
}

_ignorando_hook = False

def directx_press(scancode):
    """Pressiona tecla a nível de hardware via SendInput DirectX nativo."""
    global _ignorando_hook
    _ignorando_hook = True
    try:
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    except Exception:
        pass
    finally:
        _ignorando_hook = False

def directx_release(scancode):
    """Solta tecla a nível de hardware DirectX."""
    global _ignorando_hook
    _ignorando_hook = True
    try:
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    except Exception:
        pass
    finally:
        _ignorando_hook = False

def directx_liberar_tudo():
    """Garante que nenhuma tecla fique travada pressionada no Windows/DirectX."""
    for sc in (SCAN_W, SCAN_D, SCAN_A, SCAN_S, SCAN_Q, SCAN_E, SCAN_C, SCAN_Z):
        directx_release(sc)

def directx_tap(scancode, duracao_sec):
    """Mantém a tecla pressionada pela duração balística exata calculada pela IA."""
    directx_press(scancode)
    time.sleep(duracao_sec)
    directx_release(scancode)


# ==============================================================================
# 2. CONFIGURAÇÕES PADRÃO E ARQUIVO JSON
# ==============================================================================
CONFIG_PATH = "d:/Efootball controle/config_visao.json"

RADAR_ROI_PADRAO = {
    "top": 890,
    "left": 830,
    "width": 260,
    "height": 130
}

DEFAULT_CONFIG = {
    "radar_roi": RADAR_ROI_PADRAO,
    "hotkeys": {
        "lancamento_ia":     "5",     # Botão Z (tecla 5 - livre de conflito)
        "cruzamento_ia":     "6",     # Botão C (tecla 6 - livre de conflito com eFootball)
        "inverter_cor_time": "f10"
    },
    "modo_cor_time": "AUTO",
    "usar_mira_automatica_360": True
}

# Constantes de botões do Gamepad
BTN_A = 0
BTN_B = 1
BTN_X = 2
BTN_Y = 3
BTN_LB = 4
BTN_RB = 5
BTN_LT_DIGITAL = 10
BTN_RT_DIGITAL = 11


# ==============================================================================
# 3. MOTOR DE VISÃO COMPUTACIONAL, CINEMÁTICA E BALÍSTICA (OPENCV)
# ==============================================================================
class KinematicPlayerTracker:
    """Rastreador Cinemático com Filtro Exponencial Móvel (EMA) para velocidade."""
    def __init__(self, alpha=0.65, max_match_dist=25.0):
        self.alpha = alpha
        self.max_match_dist = max_match_dist
        self.tracks = {}
        self.next_id = 0
        self.last_time = None

    def update(self, detected_pts, current_time=None):
        if current_time is None:
            current_time = time.time()

        if self.last_time is None:
            dt = 0.05
        else:
            dt = max(0.01, min(0.20, current_time - self.last_time))
        self.last_time = current_time

        unmatched_dets = list(detected_pts)
        matched_velocities = {}

        for tid, track in list(self.tracks.items()):
            best_idx = None
            best_dist = float('inf')
            for i, pt in enumerate(unmatched_dets):
                d = np.hypot(pt[0] - track['pos'][0], pt[1] - track['pos'][1])
                if d < best_dist and d <= self.max_match_dist:
                    best_dist = d
                    best_idx = i

            if best_idx is not None:
                pt = unmatched_dets.pop(best_idx)
                vx_raw = (pt[0] - track['pos'][0]) / dt
                vy_raw = (pt[1] - track['pos'][1]) / dt
                speed = np.hypot(vx_raw, vy_raw)
                if speed > 45.0:
                    scale = 45.0 / speed
                    vx_raw *= scale
                    vy_raw *= scale
                if speed < 2.5:
                    vx_raw, vy_raw = 0.0, 0.0

                vx_smooth = self.alpha * vx_raw + (1.0 - self.alpha) * track['vel'][0]
                vy_smooth = self.alpha * vy_raw + (1.0 - self.alpha) * track['vel'][1]
                self.tracks[tid] = {'pos': pt, 'vel': (vx_smooth, vy_smooth), 'lost': 0}
                matched_velocities[pt] = (vx_smooth, vy_smooth)
            else:
                track['lost'] += 1
                if track['lost'] > 4:
                    del self.tracks[tid]

        for pt in unmatched_dets:
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = {'pos': pt, 'vel': (0.0, 0.0), 'lost': 0}
            matched_velocities[pt] = (0.0, 0.0)

        return matched_velocities


def calcular_forca_balistica(distancia_metros, usar_aereo=False):
    """
    Curva balística com atrito do gramado:
    forca = 0.20 + 0.76 * (dist_norm)^0.86
    tempo_ms = 95 + forca * 250
    """
    d = max(6.0, min(52.0, float(distancia_metros)))
    dist_norm = (d - 6.0) / (52.0 - 6.0)
    forca_barra = 0.20 + 0.76 * (dist_norm ** 0.86)
    if usar_aereo:
        forca_barra = min(1.0, forca_barra * 1.12)
    forca_barra = max(0.18, min(1.0, forca_barra))
    tempo_ms = int(95.0 + forca_barra * 250.0)
    return forca_barra, tempo_ms


class RadarPassesEFootball:
    def __init__(self, roi=None):
        self.roi = roi or RADAR_ROI_PADRAO
        self.kinematic_tracker = KinematicPlayerTracker(alpha=0.65)
        # Faixas de cor HSV calibradas para o eFootball
        self.verde_min = np.array([35, 40, 40])
        self.verde_max = np.array([85, 255, 255])
        self.verm_min1 = np.array([0, 70, 70])
        self.verm_max1 = np.array([10, 255, 255])
        self.verm_min2 = np.array([165, 70, 70])
        self.verm_max2 = np.array([180, 255, 255])
        self.anel_min = np.array([18, 100, 150])
        self.anel_max = np.array([35, 255, 255])

    def isolar_pontos(self, hsv, min_val, max_val, area_min=6, area_max=120):
        mascara = cv2.inRange(hsv, min_val, max_val)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        pontos = []
        for c in contornos:
            area = cv2.contourArea(c)
            if area_min <= area <= area_max:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    pontos.append((cX, cY))
        return pontos

    def processar_frame(self, frame_bgr):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        verdes = self.isolar_pontos(hsv, self.verde_min, self.verde_max, 5, 130)
        masc_v1 = cv2.inRange(hsv, self.verm_min1, self.verm_max1)
        masc_v2 = cv2.inRange(hsv, self.verm_min2, self.verm_max2)
        masc_verm = cv2.bitwise_or(masc_v1, masc_v2)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        masc_verm = cv2.morphologyEx(masc_verm, cv2.MORPH_OPEN, kernel)
        contornos_v, _ = cv2.findContours(masc_verm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        vermelhos = []
        for c in contornos_v:
            if 5 <= cv2.contourArea(c) <= 130:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    vermelhos.append((int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])))

        # 1. Anel Amarelo/Dourado do Cursor (Dilatação para fechar anel fino sem apagar com erosão)
        masc_anel = cv2.inRange(hsv, np.array([16, 60, 110]), np.array([38, 255, 255]))
        kernel_d = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        masc_anel = cv2.dilate(masc_anel, kernel_d, iterations=1)
        contornos_a, _ = cv2.findContours(masc_anel, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cursor_usuario = None
        for ca in contornos_a:
            area_a = cv2.contourArea(ca)
            if 3 <= area_a <= 400:
                Ma = cv2.moments(ca)
                if Ma["m00"] > 0:
                    cursor_usuario = (int(Ma["m10"] / Ma["m00"]), int(Ma["m01"] / Ma["m00"]))
                    break

        # 2. Ponto da Bola (Branco brilhante no radar)
        masc_bola = cv2.inRange(hsv, np.array([0, 0, 185]), np.array([180, 55, 255]))
        contornos_b, _ = cv2.findContours(masc_bola, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        pos_bola = None
        for cb in contornos_b:
            area_b = cv2.contourArea(cb)
            if 2 <= area_b <= 35:
                Mb = cv2.moments(cb)
                if Mb["m00"] > 0:
                    pos_bola = (int(Mb["m10"] / Mb["m00"]), int(Mb["m01"] / Mb["m00"]))
                    break

        return verdes, vermelhos, cursor_usuario, pos_bola

    def analisar_linhas_de_passe(self, portador, companheiros, adversarios, atacando_direita=True, linha_zaga=None):
        livres = []
        bloqueados = []
        px_to_meters = 0.42
        largura_campo = self.roi["width"]
        gol_alvo_x = largura_campo if atacando_direita else 0
        velocidades = self.kinematic_tracker.update(companheiros)

        for comp in companheiros:
            dist_px = math.hypot(comp[0] - portador[0], comp[1] - portador[1])
            if dist_px < 6.0:
                continue

            # Bhaskara: Ponto futuro
            vx, vy = velocidades.get(comp, (0.0, 0.0))
            comp_speed = math.hypot(vx, vy)
            v_bola = 125.0
            dx0 = comp[0] - portador[0]
            dy0 = comp[1] - portador[1]
            A = (vx**2 + vy**2) - (v_bola**2)
            B = 2.0 * (dx0 * vx + dy0 * vy)
            C = dx0**2 + dy0**2
            discriminante = B**2 - 4.0 * A * C

            t_star = None
            if discriminante >= 0 and abs(A) > 1e-4:
                sqrt_disc = math.sqrt(discriminante)
                t1 = (-B - sqrt_disc) / (2.0 * A)
                t2 = (-B + sqrt_disc) / (2.0 * A)
                candidatos = [t for t in (t1, t2) if t > 0.05]
                if candidatos:
                    t_star = min(candidatos)

            if t_star is None or t_star > 1.20:
                t_star = dist_px / v_bola
            t_star = max(0.08, min(0.95, t_star))

            pred_x = int(comp[0] + vx * t_star)
            pred_y = int(comp[1] + vy * t_star)
            destino_futuro = (
                max(2, min(largura_campo - 2, pred_x)),
                max(2, min(self.roi["height"] - 2, pred_y))
            )

            # Cone anti-bloqueio e colisão de zagueiro
            bloqueado = False
            zagueiro_bloqueador = None
            dx_fut = destino_futuro[0] - portador[0]
            dy_fut = destino_futuro[1] - portador[1]
            dist_fut_px = math.hypot(dx_fut, dy_fut)
            ang_passe = math.atan2(dy_fut, dx_fut)

            for adv in adversarios:
                dx_adv = adv[0] - portador[0]
                dy_adv = adv[1] - portador[1]
                dist_adv = math.hypot(dx_adv, dy_adv)
                if dist_adv < dist_fut_px:
                    proj = (dx_adv * dx_fut + dy_adv * dy_fut) / (dist_fut_px + 1e-5)
                    if 0 < proj < dist_fut_px:
                        perp = abs(dx_adv * math.sin(ang_passe) - dy_adv * math.cos(ang_passe))
                        margem_seg = 6.0 + (proj / dist_fut_px) * 7.5
                        if perp < margem_seg:
                            bloqueado = True
                            zagueiro_bloqueador = adv
                            break

            # Motor de Arco Evasivo de Curva (Trivela / Efeito Fenomenal / Cavada)
            curva_ativa = False
            tipo_passe = "RASTEIRO"
            pontos_arco = []
            apex = None

            dist_metros = dist_fut_px * px_to_meters

            if bloqueado:
                curva_ativa = True
                u_x = dx_fut / (dist_fut_px + 1e-5)
                u_y = dy_fut / (dist_fut_px + 1e-5)
                # Vetor normal perpendicular à linha reta
                n_x = -u_y
                n_y = u_x

                altura_c = self.roi["height"]
                melhor_lado = 1
                maior_folga = -999.0

                # Testa os dois lados de curvatura (flanco superior vs flanco inferior)
                for lado in (1, -1):
                    offset_lat = 16.0 * lado
                    apx = int(portador[0] + dx_fut * 0.45 + n_x * offset_lat)
                    apy = int(portador[1] + dy_fut * 0.45 + n_y * offset_lat)
                    if not (3 < apy < altura_c - 3) or not (3 < apx < largura_campo - 3):
                        continue
                    folga_adv = min([math.hypot(apx - adv[0], apy - adv[1]) for adv in adversarios], default=99.0)
                    if folga_adv > maior_folga:
                        maior_folga = folga_adv
                        melhor_lado = lado
                        apex = (apx, apy)

                if apex is not None:
                    # Gera 8 pontos da Curva de Bézier quadrática
                    for step in range(8):
                        t_b = step / 7.0
                        bx = int((1.0 - t_b)**2 * portador[0] + 2.0 * (1.0 - t_b) * t_b * apex[0] + t_b**2 * destino_futuro[0])
                        by = int((1.0 - t_b)**2 * portador[1] + 2.0 * (1.0 - t_b) * t_b * apex[1] + t_b**2 * destino_futuro[1])
                        pontos_arco.append((bx, by))

                    if dist_metros > 18.0:
                        tipo_passe = "FENOMENAL_CURVA"  # Stunning Through Ball (RT+Y / E+W - Trivela com Efeito)
                    else:
                        tipo_passe = "CAVADO_ARCO"      # Lofted Through Ball (LB+Y / Q+W - Arco por cima)
                else:
                    tipo_passe = "CAVADO_ARCO"
            # Regra IFAB Oficial de Impedimento (Lei 11):
            # Medida rigorosamente na posição física do atacante NO MOMENTO DO PASSE (comp[0]) e na linha da bola!
            impedido = False
            rompimento = False
            atras_da_bola = (comp[0] <= (portador[0] + 1.0)) if atacando_direita else (comp[0] >= (portador[0] - 1.0))

            if linha_zaga is not None and not atras_da_bola:
                if atacando_direita:
                    if comp[0] > (linha_zaga + 1.0):
                        impedido = True
                    elif comp[0] <= (linha_zaga + 1.0) and destino_futuro[0] > (linha_zaga - 1.0) and vx > 5.0:
                        rompimento = True
                else:
                    if comp[0] < (linha_zaga - 1.0):
                        impedido = True
                    elif comp[0] >= (linha_zaga - 1.0) and destino_futuro[0] < (linha_zaga + 1.0) and vx < -5.0:
                        rompimento = True

            if bloqueado:
                if apex is not None and dist_metros > 18.0:
                    tipo_passe = "FENOMENAL_CURVA"  # Stunning Through Ball (RT+Y / E+W - Trivela com Efeito)
                else:
                    tipo_passe = "CAVADO_ARCO"      # Lofted Through Ball (LB+Y / Q+W - Arco por cima)
            else:
                if rompimento:
                    tipo_passe = "FENOMENAL_CURVA" if dist_metros > 22.0 else "CAVADO_ARCO"
                elif dist_metros > 28.0:
                    tipo_passe = "FENOMENAL_CURVA"
                else:
                    tipo_passe = "RASTEIRO"

            forca_b, tempo_ms = calcular_forca_balistica(dist_metros, usar_aereo=(tipo_passe == "CAVADO_ARCO"))
            avanco_ofensivo = (destino_futuro[0] - portador[0]) if atacando_direita else (portador[0] - destino_futuro[0])
            dist_gol = abs(gol_alvo_x - destino_futuro[0]) * px_to_meters

            score = 100.0 - dist_gol * 1.1 + avanco_ofensivo * 0.95 + comp_speed * 0.4
            if bloqueado:
                score -= 10.0  # Penalidade reduzida pois temos a rota em curva evasiva!
            if impedido:
                score -= 60.0
            if rompimento:
                score += 35.0

            item = {
                "origem": portador,
                "destino": comp,
                "destino_futuro": destino_futuro,
                "velocidade_kmh": comp_speed * 1.8,
                "dist_metros": dist_metros,
                "forca_barra": forca_b,
                "tempo_ms": tempo_ms,
                "aereo": (tipo_passe == "CAVADO_ARCO"),
                "curva": curva_ativa,
                "tipo_passe": tipo_passe,
                "pontos_arco": pontos_arco,
                "apex": apex,
                "zagueiro_bloqueador": zagueiro_bloqueador,
                "impedido": impedido,
                "rompimento": rompimento,
                "score": score
            }

            if bloqueado and not impedido:
                bloqueados.append(item)
            else:
                livres.append(item)

        livres.sort(key=lambda x: x["score"], reverse=True)
        return livres, bloqueados

    def analisar_cruzamento_tatico(self, portador, companheiros, adversarios, atacando_direita=True, linha_zaga=None):
        """
        Motor Tático de Cruzamento Inteligente:
        - Classificação de 1ª Trave, 2ª Trave e Meia-Lua
        - Detecção de Marcação Defensiva (Folga dos Zagueiros)
        - Regra de Impedimento IFAB estrita (linha da bola e linha de zaga)
        - Seleção automática entre Rasteiro (D+D), Balão Alto (LB+D), Antecipado (LB+D), Fenomenal (RT+D) e Cabeça (D)
        """
        largura_campo = self.roi["width"]
        altura_campo = self.roi["height"]
        px_to_meters = 0.42
        gol_alvo_x = largura_campo if atacando_direita else 0
        centro_y = altura_campo / 2.0
        dir_atq = 1 if atacando_direita else -1

        # Distância do portador até a linha de fundo
        dist_fundo_px = abs(gol_alvo_x - portador[0])
        dist_fundo_m = dist_fundo_px * px_to_meters

        # Posições de referência da 1ª e 2ª trave (dependendo de qual lateral o portador está)
        y_trave_sup = int(centro_y - 18)
        y_trave_inf = int(centro_y + 18)
        if portador[1] <= centro_y:
            y_1a_trave = y_trave_sup
            y_2a_trave = y_trave_inf
        else:
            y_1a_trave = y_trave_inf
            y_2a_trave = y_trave_sup

        # Detecção de Escanteio: cobrador no bico da linha de fundo
        no_escanteio = (dist_fundo_px <= 16 and (portador[1] <= 22 or portador[1] >= (altura_campo - 22)))

        candidatos_cruz = []

        for comp in companheiros:
            dist_gol_x = abs(gol_alvo_x - comp[0])
            # Considera companheiros dentro da zona ofensiva ou penetrando na área (últimos 26 metros)
            if dist_gol_x > 62.0:
                continue

            # Regra IFAB de Impedimento para Cruzamento:
            # Nunca há impedimento se o atacante estiver atrás ou na mesma linha da bola (ou no escanteio)
            impedido = False
            if not no_escanteio and linha_zaga is not None:
                if atacando_direita:
                    if comp[0] > (linha_zaga + 1.0) and comp[0] > portador[0]:
                        impedido = True
                else:
                    if comp[0] < (linha_zaga - 1.0) and comp[0] < portador[0]:
                        impedido = True

            if impedido:
                continue

            # Classificação Setorial na Área
            dist_1a = abs(comp[1] - y_1a_trave)
            dist_2a = abs(comp[1] - y_2a_trave)

            if dist_gol_x > 38.0:
                setor = "ENTRADA_AREA"
            elif dist_1a <= dist_2a:
                setor = "1A_TRAVE"
            else:
                setor = "2A_TRAVE"

            # Índice de Marcação Defensiva: distância até o adversário mais próximo do recebedor
            folga_def_px = min([math.hypot(comp[0] - adv[0], comp[1] - adv[1]) for adv in adversarios], default=99.0)
            folga_def_m = folga_def_px * px_to_meters
            marcado = (folga_def_m < 3.8)

            # Ponto Futuro de finalização
            cx_fut = int(comp[0] + dir_atq * min(16.0, dist_gol_x * 0.20))
            alvo_y_setor = y_1a_trave if setor == "1A_TRAVE" else (y_2a_trave if setor == "2A_TRAVE" else int(centro_y))
            cy_fut = int(comp[1] + (alvo_y_setor - comp[1]) * 0.25)
            destino_futuro = (max(2, min(largura_campo - 2, cx_fut)), max(2, min(altura_campo - 2, cy_fut)))

            dist_cruz_px = math.hypot(destino_futuro[0] - portador[0], destino_futuro[1] - portador[1])
            dist_cruz_m = dist_cruz_px * px_to_meters

            # Monitoramento dos Zagueiros: Bloqueio Frontal e Interceptação de Trajetória
            dx_c = destino_futuro[0] - portador[0]
            dy_c = destino_futuro[1] - portador[1]
            dist_c_safe = max(1.0, dist_cruz_px)
            ang_c = math.atan2(dy_c, dx_c)

            bloqueio_frontal = False
            bloqueio_trajetoria = False

            for adv in adversarios:
                dx_a = adv[0] - portador[0]
                dy_a = adv[1] - portador[1]
                dist_a_px = math.hypot(dx_a, dy_a)
                dist_a_m = dist_a_px * px_to_meters

                # 1. Zagueiro/Lateral no combate direto (a menos de 3.2m na frente do cruzador)
                if dist_a_m < 3.2:
                    prod_proj = (dx_a * dx_c + dy_a * dy_c) / dist_c_safe
                    if prod_proj > 0:
                        bloqueio_frontal = True

                # 2. Zagueiro interceptando o corredor da trajetória aérea/rasteira
                if dist_a_px < dist_c_safe:
                    proj = (dx_a * dx_c + dy_a * dy_c) / dist_c_safe
                    if 5.0 < proj < (dist_c_safe - 6.0):
                        dist_perp = abs(dx_a * math.sin(ang_c) - dy_a * math.cos(ang_c)) * px_to_meters
                        if dist_perp < 2.5:
                            bloqueio_trajetoria = True

            # Seleção Inteligente do Tipo de Cruzamento:
            tipo_cruz = "CABEÇA"
            tag_hud = "CRUZAMENTO D"

            if no_escanteio:
                # No escanteio nunca usar RT (evita travar menu tático/câmera do eFootball)
                if setor == "2A_TRAVE":
                    tipo_cruz = "BALAO_ALTO"
                    tag_hud = "ESCANTEIO 2ª TRAVE LB+D"
                elif setor == "1A_TRAVE":
                    tipo_cruz = "CABEÇA"
                    tag_hud = "ESCANTEIO 1ª TRAVE D"
                else:
                    tipo_cruz = "RASTEIRO"
                    tag_hud = "ESCANTEIO CURTO D+D"
            elif setor == "1A_TRAVE":
                if (dist_gol_x * px_to_meters) < 15.0 and not bloqueio_frontal and not bloqueio_trajetoria:
                    tipo_cruz = "RASTEIRO"
                    tag_hud = "1ª TRAVE RASTEIRO D+D"
                elif dist_fundo_m > 22.0:
                    tipo_cruz = "ANTECIPADO"
                    tag_hud = "1ª TRAVE ANTECIPADO LB+D"
                else:
                    tipo_cruz = "CABEÇA"
                    tag_hud = "1ª TRAVE CABEÇA D"
            elif setor == "2A_TRAVE":
                if dist_fundo_m > 24.0:
                    tipo_cruz = "ANTECIPADO"
                    tag_hud = "2ª TRAVE ANTECIPADO LB+D"
                elif dist_fundo_m <= 18.0 or bloqueio_trajetoria or bloqueio_frontal:
                    tipo_cruz = "BALAO_ALTO"
                    tag_hud = "2ª TRAVE BALÃO LB+D"
                elif dist_cruz_m > 44.0 and not bloqueio_frontal:
                    tipo_cruz = "FENOMENAL"
                    tag_hud = "2ª TRAVE FENOMENAL RT+D"
                else:
                    tipo_cruz = "CABEÇA"
                    tag_hud = "2ª TRAVE CABEÇA D"
            else:  # ENTRADA_AREA
                if bloqueio_frontal or bloqueio_trajetoria:
                    tipo_cruz = "CABEÇA"
                    tag_hud = "MEIA-LUA PELO ALTO D"
                else:
                    tipo_cruz = "RASTEIRO"
                    tag_hud = "MEIA-LUA ATRASADO D+D"

            # Score Tático
            score = 100.0 - (dist_gol_x * px_to_meters) * 1.2 + folga_def_m * 4.5
            if setor == "2A_TRAVE" and not marcado:
                score += 28.0  # Bônus alto para 2ª trave desmarcada
            elif setor == "1A_TRAVE" and not marcado:
                score += 20.0
            if marcado:
                score -= 32.0  # Penalidade forte se o recebedor estiver marcado por zagueiro
            if bloqueio_trajetoria and setor == "1A_TRAVE":
                score -= 25.0  # Zagueiro cortando a 1ª trave -> favorece virar na 2ª trave livre!
            if bloqueio_frontal:
                score -= 10.0  # Pressão imediata no cruzador

            usar_aereo = (tipo_cruz != "RASTEIRO")
            forca_c, tempo_c = calcular_forca_balistica(dist_cruz_m, usar_aereo=usar_aereo)

            candidatos_cruz.append({
                "origem": portador,
                "destino": comp,
                "destino_futuro": destino_futuro,
                "setor": setor,
                "marcado": marcado,
                "folga_def_m": folga_def_m,
                "tipo": tipo_cruz,
                "tag_hud": tag_hud,
                "dist_metros": dist_cruz_m,
                "forca_barra": forca_c,
                "tempo_ms": tempo_c,
                "score": score
            })

        candidatos_cruz.sort(key=lambda x: x["score"], reverse=True)
        return candidatos_cruz[0] if candidatos_cruz else None



# ==============================================================================
# 4. HOOK DE TECLADO E ESTADO GLOBAL DO SISTEMA
# ==============================================================================
_teclas_ativas = set()
_lock_teclas = threading.Lock()
_ultima_tecla = [""]

def _on_key_down(event):
    if _ignorando_hook:
        return
    nome = event.name.lower() if event.name else ""
    with _lock_teclas:
        _teclas_ativas.add(nome)
    _ultima_tecla[0] = nome

def _on_key_up(event):
    if _ignorando_hook:
        return
    nome = event.name.lower() if event.name else ""
    with _lock_teclas:
        _teclas_ativas.discard(nome)
        if nome.isdigit():
            _teclas_ativas.discard(f"num {nome}")

def tecla_foi_pressionada(nome_tecla):
    if not nome_tecla:
        return False
    t = str(nome_tecla).strip().lower()
    t_num = f"num {t}" if t.isdigit() else None

    # 1. Via Hardware GetAsyncKeyState (VK) - checagem de estado físico real em nível de kernel
    try:
        vk = None
        if len(t) == 1:
            if '0' <= t <= '9':
                vk = 0x30 + int(t)
            elif 'a' <= t <= 'z':
                vk = 0x41 + (ord(t) - ord('a'))
        if vk is not None:
            down_std = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
            down_num = bool(ctypes.windll.user32.GetAsyncKeyState(0x60 + int(t)) & 0x8000) if t.isdigit() else False
            if down_std or down_num:
                _ultima_tecla[0] = t
                return True
            else:
                # Se o kernel do Windows informa que a tecla NÃO está pressionada,
                # remove imediatamente de _teclas_ativas para nunca ficar presa!
                with _lock_teclas:
                    _teclas_ativas.discard(t)
                    if t_num:
                        _teclas_ativas.discard(t_num)
                return False
    except Exception:
        pass

    # 2. Via keyboard.is_pressed direto
    try:
        if keyboard.is_pressed(t) or (t_num and keyboard.is_pressed(t_num)):
            _ultima_tecla[0] = t
            return True
        else:
            with _lock_teclas:
                _teclas_ativas.discard(t)
                if t_num:
                    _teclas_ativas.discard(t_num)
            return False
    except Exception:
        pass

    # 3. Via Hook _teclas_ativas
    with _lock_teclas:
        if t in _teclas_ativas or (t_num and t_num in _teclas_ativas):
            _ultima_tecla[0] = t
            return True

    return False

def consumir_tecla(*nomes_tecla):
    with _lock_teclas:
        for item in nomes_tecla:
            if not item:
                continue
            t = str(item).strip().lower()
            _teclas_ativas.discard(t)
            if t.isdigit():
                _teclas_ativas.discard(f"num {t}")


class TelemetriaPasses:
    """Rastreia cada passe disparado pela IA e afere se foi concluído ou interceptado."""
    def __init__(self):
        self.lock = threading.Lock()
        self.total_disparados = 0
        self.acertos = 0
        self.erros = 0
        self.historico = []  # Lista com os últimos 50 passes
        self.passe_em_voo = None

    def zerar(self):
        with self.lock:
            self.total_disparados = 0
            self.acertos = 0
            self.erros = 0
            self.historico.clear()
            self.passe_em_voo = None

    def registrar_disparo(self, dados_passe, tempo_ms, aereo):
        with self.lock:
            self.total_disparados += 1
            dist = dados_passe.get("dist_metros", 20.0) if dados_passe else 20.0
            df = dados_passe.get("destino_futuro", (0, 0)) if dados_passe else (0, 0)
            alvo = dados_passe.get("destino", df) if dados_passe else df
            origem = dados_passe.get("origem", (0, 0)) if dados_passe else (0, 0)
            t_voo = max(0.35, min(2.5, dist / 13.0))
            self.passe_em_voo = {
                "id": self.total_disparados,
                "hora": time.strftime("%H:%M:%S"),
                "dist_m": dist,
                "tempo_ms": int(tempo_ms),
                "aereo": aereo,
                "origem": origem,
                "alvo_pos": alvo,
                "destino_futuro": df,
                "t_disparo": time.perf_counter(),
                "t_chegada": time.perf_counter() + t_voo,
                "t_limite": time.perf_counter() + t_voo + 1.25,
                "status": "EM_VOO"
            }

    def avaliar_frame(self, cursor_usuario, companheiros, adversarios, pos_bola=None):
        with self.lock:
            if not self.passe_em_voo or self.passe_em_voo["status"] != "EM_VOO":
                return None

            agora = time.perf_counter()
            pv = self.passe_em_voo
            df = pv["destino_futuro"]
            alvo_p = pv.get("alvo_pos", df)
            origem = pv.get("origem", (0, 0))
            t_decorrido = agora - pv["t_disparo"]

            # 1. Checagem de Bloqueio do Zagueiro ao longo da trajetória
            if adversarios and t_decorrido >= 0.25:
                dx_p = df[0] - origem[0]
                dy_p = df[1] - origem[1]
                dist_linha = math.hypot(dx_p, dy_p) + 1e-5
                for adv in adversarios:
                    dx_a = adv[0] - origem[0]
                    dy_a = adv[1] - origem[1]
                    proj = (dx_a * dx_p + dy_a * dy_p) / dist_linha
                    # Se o adversário está posicionado na rota entre o passador e o alvo
                    if 8.0 < proj < (dist_linha - 10.0):
                        perp = abs(dx_a * (dy_p / dist_linha) - dy_a * (dx_p / dist_linha))
                        # Se a bola ou o zagueiro bloquearam a linha (< 8px de distância perpendicular)
                        if perp < 8.0:
                            if pos_bola and math.hypot(pos_bola[0] - adv[0], pos_bola[1] - adv[1]) < 12.0:
                                pv["status"] = "❌ BLOQUEADO (Zagueiro)"
                                self.erros += 1
                                self.historico.insert(0, dict(pv))
                                if len(self.historico) > 50:
                                    self.historico.pop()
                                self.passe_em_voo = None
                                return "ERRO"

            # 2. Transferência do cursor amarelo para o RECEBEDOR PRETENDIDO (exclusivo)
            if cursor_usuario is not None and t_decorrido >= 0.20:
                dist_cursor_df = math.hypot(cursor_usuario[0] - df[0], cursor_usuario[1] - df[1])
                dist_cursor_alvo = math.hypot(cursor_usuario[0] - alvo_p[0], cursor_usuario[1] - alvo_p[1])
                dist_cursor_origem = math.hypot(cursor_usuario[0] - origem[0], cursor_usuario[1] - origem[1])

                # Deve estar próximo do alvo futuro (raio 26px) ou do alvo inicial (20px), e longe de quem passou
                if (dist_cursor_df < 26.0 or dist_cursor_alvo < 20.0) and dist_cursor_origem > 14.0:
                    pv["status"] = "✅ CONCLUÍDO (No Alvo)"
                    self.acertos += 1
                    self.historico.insert(0, dict(pv))
                    if len(self.historico) > 50:
                        self.historico.pop()
                    self.passe_em_voo = None
                    return "ACERTO"

            # 3. A BOLA alcançou a zona do recebedor pretendido
            if pos_bola is not None and t_decorrido >= 0.35:
                dist_bola_df = math.hypot(pos_bola[0] - df[0], pos_bola[1] - df[1])
                dist_bola_alvo = math.hypot(pos_bola[0] - alvo_p[0], pos_bola[1] - alvo_p[1])
                dist_bola_origem = math.hypot(pos_bola[0] - origem[0], pos_bola[1] - origem[1])

                if (dist_bola_df < 16.0 or dist_bola_alvo < 14.0) and dist_bola_origem > 15.0:
                    pv["status"] = "✅ CONCLUÍDO (Bola no Alvo)"
                    self.acertos += 1
                    self.historico.insert(0, dict(pv))
                    if len(self.historico) > 50:
                        self.historico.pop()
                    self.passe_em_voo = None
                    return "ACERTO"

            # 4. Adversário interceptou a posse da bola
            if pos_bola is not None and t_decorrido >= 0.30:
                dist_bola_origem = math.hypot(pos_bola[0] - origem[0], pos_bola[1] - origem[1])
                if dist_bola_origem > 15.0:
                    for adv in adversarios:
                        if math.hypot(pos_bola[0] - adv[0], pos_bola[1] - adv[1]) < 9.0:
                            pv["status"] = "❌ INTERCEPTADO"
                            self.erros += 1
                            self.historico.insert(0, dict(pv))
                            if len(self.historico) > 50:
                                self.historico.pop()
                            self.passe_em_voo = None
                            return "ERRO"

            # 5. Tempo limite expirou
            if agora >= pv["t_limite"]:
                interceptado = any(math.hypot(adv[0] - df[0], adv[1] - df[1]) < 20.0 for adv in adversarios)
                pv["status"] = "❌ BLOQUEADO (Zagueiro)" if interceptado else "❌ FORA / LONGO"
                self.erros += 1
                self.historico.insert(0, dict(pv))
                if len(self.historico) > 50:
                    self.historico.pop()
                self.passe_em_voo = None
                return "ERRO"

            return None

    def obter_estatisticas(self):
        with self.lock:
            tot = self.total_disparados
            certos = self.acertos
            errados = self.erros
            taxa = (certos / tot * 100.0) if tot > 0 else 0.0
            dists = [p["dist_m"] for p in self.historico]
            dist_media = (sum(dists) / len(dists)) if dists else 0.0
            tempos = [p["tempo_ms"] for p in self.historico]
            tempo_medio = (sum(tempos) / len(tempos)) if tempos else 0.0
            hist = list(self.historico)
            if self.passe_em_voo and self.passe_em_voo.get("status") == "EM_VOO":
                hist = [dict(self.passe_em_voo)] + hist
            return {
                "total": tot,
                "acertos": certos,
                "erros": errados,
                "taxa": taxa,
                "dist_media": dist_media,
                "tempo_medio": tempo_medio,
                "historico": hist
            }


class EstadoSistema:
    def __init__(self):
        self.rodando = True
        self.lock = threading.Lock()
        self.config = self.carregar_config()
        self.dados_passe = None
        self.ultimo_passe_valido = None
        self.dados_cruzamento = None
        self.pos_bola = None
        self.cursor_usuario = None
        self.sou_time_verde = True
        self.atacando_direita = True
        self.radar_ativo = False
        self.rp2040_conectado = False
        self.telemetria = TelemetriaPasses()

    def carregar_config(self):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    salvo = json.load(f)
                    if "hotkeys" in salvo:
                        cfg["hotkeys"].update(salvo["hotkeys"])
                    if "modo_cor_time" in salvo:
                        cfg["modo_cor_time"] = salvo["modo_cor_time"]
                    if "usar_mira_automatica_360" in salvo:
                        cfg["usar_mira_automatica_360"] = salvo["usar_mira_automatica_360"]
            except Exception:
                pass
        return cfg

    def salvar_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[AVISO] Falha ao salvar {CONFIG_PATH}: {e}")


# ==============================================================================
# 5. AUXILIARES DE HARDWARE RP2040 (OPCIONAL SE CONECTADO)
# ==============================================================================
def encontrar_porta_rp2040():
    portas = list(serial.tools.list_ports.comports())
    for p in portas:
        if "239A" in p.hwid:
            if "MI_02" in p.hwid or "x.2" in p.hwid:
                return p.device
    for p in portas:
        if "239A" in p.hwid:
            return p.device
    return "COM9"

def enviar_relatorio_rp2040(ser, buttons, lx, ly, rx, ry):
    if ser and ser.is_open:
        try:
            clamp = lambda v: max(-127, min(127, int(v * 127)))
            pacote = struct.pack("<Hbbbb", buttons, clamp(lx), clamp(ly), clamp(rx), clamp(ry))
            ser.write(pacote)
        except Exception:
            pass


# ==============================================================================
# 6. THREAD DE CONTROLE E DISPARO DE AÇÕES (DIRECTX + RP2040)
# ==============================================================================
def thread_controle_execucao(estado: EstadoSistema):
    """
    Escuta os gatilhos dos botões do Flydigi Space Station e executa
    instantaneamente via DirectX SendInput (para a janela do eFootball)
    e via Serial RP2040 simultaneamente.
    """
    ser = None
    try:
        p = encontrar_porta_rp2040()
        ser = serial.Serial(p, 115200, timeout=0)
        estado.rp2040_conectado = True
        print(f"[RP2040] ✅ Conectado na porta {p} (Bridge a 1000Hz ativa)")
    except Exception:
        print("[RP2040] ℹ️ Placa não encontrada — operando com injeção nativa DirectX para o eFootball!")

    pygame.init()
    pygame.joystick.init()
    keyboard.on_press(_on_key_down, suppress=False)
    keyboard.on_release(_on_key_up, suppress=False)

    vader = None
    ultimo_disparo = 0.0
    cooldown = 0.28

    ant_lanc = False
    ant_cruz = False

    while estado.rodando:
        try:
            pygame.event.pump()
            if vader is None:
                for i in range(pygame.joystick.get_count()):
                    j = pygame.joystick.Joystick(i)
                    if "CircuitPython" not in j.get_name():
                        vader = j
                        print(f"[CONTROLE] Ativo: {vader.get_name()}")
                        break

            lx, ly = (vader.get_axis(0), vader.get_axis(1)) if vader else (0.0, 0.0)
            agora = time.perf_counter()
            hk = estado.config["hotkeys"]

            # --- 1. LANÇAMENTO TELEGUIADO IA (Botão Z no Flydigi -> Tecla 5 ou Z) ---
            tecla_lanc = hk.get("lancamento_ia", "5")
            tecla_lanc_ativa = None
            for cand in [tecla_lanc, "5", "z"]:
                if cand and tecla_foi_pressionada(cand):
                    tecla_lanc_ativa = cand
                    break

            press_lanc = tecla_lanc_ativa is not None
            if press_lanc and not ant_lanc and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                consumir_tecla(tecla_lanc, "5", "z")

                with estado.lock:
                    dp = estado.dados_passe.copy() if estado.dados_passe else (estado.ultimo_passe_valido.copy() if estado.ultimo_passe_valido else None)

                try:
                    if dp:
                        tempo_sec = max(0.090, min(0.350, dp["tempo_ms"] / 1000.0))
                        aereo = dp.get("aereo", False)
                        tipo_p = dp.get("tipo_passe", "RASTEIRO")
                        dist_m = dp.get("dist_metros", 20.0)
                        estado.telemetria.registrar_disparo(dp, tempo_sec * 1000.0, aereo)

                        if tipo_p == "FENOMENAL_CURVA":
                            print(f"\n[DISPARO] 🌀 Lançamento FENOMENAL EM CURVA (Trivela/Efeito E+W) [Tecla: {tecla_lanc_ativa.upper()}]: Dist={dist_m:.1f}m | Duração={tempo_sec*1000:.0f}ms")
                            directx_press(SCAN_E)  # RT (Stunning / Fenomenal)
                            time.sleep(0.025)
                            directx_press(SCAN_W)  # Y (Through ball)
                            time.sleep(tempo_sec)
                            directx_release(SCAN_W)
                            directx_release(SCAN_E)
                        elif tipo_p == "CAVADO_ARCO" or aereo:
                            print(f"\n[DISPARO] 🎯 Lançamento CAVADO EM ARCO (LB+W) [Tecla: {tecla_lanc_ativa.upper()}]: Dist={dist_m:.1f}m | Duração={tempo_sec*1000:.0f}ms")
                            directx_press(SCAN_Q)  # LB (Passe Cavado)
                            time.sleep(0.020)
                            directx_press(SCAN_W)  # Y (Through ball)
                            time.sleep(tempo_sec)
                            directx_release(SCAN_W)
                            directx_release(SCAN_Q)
                        else:
                            print(f"\n[DISPARO] 🎯 Lançamento IA [Tecla: {tecla_lanc_ativa.upper()}]: Dist={dist_m:.1f}m | Duração={tempo_sec*1000:.0f}ms")
                            directx_press(SCAN_W)
                            time.sleep(tempo_sec)
                            directx_release(SCAN_W)
                    else:
                        dir_frente = 38 if estado.atacando_direita else -38
                        alvo_aprox = (130 + dir_frente, 65)
                        estado.telemetria.registrar_disparo({
                            "dist_metros": 18.0,
                            "destino_futuro": alvo_aprox,
                            "origem": (130, 65)
                        }, 170.0, False)
                        print(f"\n[DISPARO] 🎯 Lançamento Manual (Sem alvo em sprint no radar) [Tecla: {tecla_lanc_ativa.upper()}] -> Disparando W padrão")
                        directx_tap(SCAN_W, 0.170)
                finally:
                    directx_liberar_tudo()

                enviar_relatorio_rp2040(ser, 1 << BTN_Y, lx, ly, 0, 0)
                time.sleep(0.015)
                enviar_relatorio_rp2040(ser, 0, lx, ly, 0, 0)
            ant_lanc = press_lanc

            # --- 2. CRUZAMENTO INTELIGENTE IA (Botão C no Flydigi -> Tecla 6 / Numpad 6) ---
            tecla_cruz = hk.get("cruzamento_ia", "6")
            tecla_cruz_ativa = None
            for cand in [tecla_cruz, "6", "num 6", "numpad 6", "f14", "[", "c"]:
                if cand and tecla_foi_pressionada(cand):
                    tecla_cruz_ativa = cand
                    break

            press_cruz = tecla_cruz_ativa is not None
            if press_cruz and not ant_cruz and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                consumir_tecla(tecla_cruz, "6", "num 6", "numpad 6", "f14", "[", "c")

                with estado.lock:
                    dc = estado.dados_cruzamento.copy() if estado.dados_cruzamento else None

                try:
                    if dc:
                        tipo = dc.get("tipo", "CABEÇA")
                        setor = dc.get("setor", "ÁREA")
                        tag = dc.get("tag_hud", tipo)
                        dist_m = dc.get("dist_metros", 25.0)
                        tempo_sec = max(0.095, min(0.350, dc["tempo_ms"] / 1000.0))
                        print(f"\n[DISPARO] ⚡ Cruzamento Inteligente: {tag} ({setor}) | Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")

                        if tipo == "RASTEIRO":
                            # Toque duplo rápido D + D (Low Driven Cross)
                            directx_tap(SCAN_D, 0.040)
                            time.sleep(0.035)
                            directx_tap(SCAN_D, max(0.065, tempo_sec * 0.70))
                        elif tipo in ("BALAO_ALTO", "ANTECIPADO"):
                            # LB + D (High Floated / Early Cross com cobertura nas costas da zaga)
                            directx_press(SCAN_Q)  # LB
                            time.sleep(0.020)
                            directx_press(SCAN_D)  # B
                            time.sleep(tempo_sec)
                            directx_release(SCAN_D)
                            directx_release(SCAN_Q)
                        elif tipo == "FENOMENAL":
                            # RT + D (Stunning Cross tenso com efeito e velocidade máxima)
                            directx_press(SCAN_E)  # RT
                            time.sleep(0.025)
                            directx_press(SCAN_D)  # B
                            time.sleep(tempo_sec)
                            directx_release(SCAN_D)
                            directx_release(SCAN_E)
                        else:  # CABEÇA / PADRAO
                            directx_tap(SCAN_D, tempo_sec)
                    else:
                        print("\n[DISPARO] ⚡ Cruzamento Manual (Sem alvo na área no radar) -> Disparando D padrão")
                        directx_tap(SCAN_D, 0.170)
                finally:
                    directx_liberar_tudo()

                enviar_relatorio_rp2040(ser, 1 << BTN_B, lx, ly, 0, 0)
                time.sleep(0.015)
                enviar_relatorio_rp2040(ser, 0, lx, ly, 0, 0)
            ant_cruz = press_cruz

            # Inverter Time manualmente com F10
            tecla_inv = hk.get("inverter_cor_time", "f10")
            if tecla_foi_pressionada(tecla_inv):
                consumir_tecla(tecla_inv)
                with estado.lock:
                    estado.sou_time_verde = not estado.sou_time_verde
                    novo_modo = "VERDE" if estado.sou_time_verde else "VERMELHO"
                    estado.config["modo_cor_time"] = novo_modo
                    estado.salvar_config()
                    print(f"\n[TIME] Invertido manualmente e salvo: {novo_modo}")

            # Passthrough padrão para o RP2040 (se houver controle conectado)
            if vader and ser and ser.is_open:
                buttons = 0
                for b in range(min(16, vader.get_numbuttons())):
                    if vader.get_button(b):
                        buttons |= (1 << b)
                enviar_relatorio_rp2040(ser, buttons, lx, ly, 0, 0)

            time.sleep(0.002)

            # Passthrough padrão para o RP2040 (se houver controle conectado)
            if vader and ser and ser.is_open:
                buttons = 0
                for b in range(min(16, vader.get_numbuttons())):
                    if vader.get_button(b):
                        buttons |= (1 << b)
                enviar_relatorio_rp2040(ser, buttons, lx, ly, 0, 0)

            time.sleep(0.002)

        except Exception:
            time.sleep(0.005)

    if ser and ser.is_open:
        ser.close()


# ==============================================================================
# 7. THREAD DE VISÃO COMPUTACIONAL A 60 FPS (MSS + OPENCV)
# ==============================================================================
def thread_visao_radar(estado: EstadoSistema):
    sct = mss.mss()
    roi = estado.config.get("radar_roi", RADAR_ROI_PADRAO)
    processador = RadarPassesEFootball(roi)
    print(f"[RADAR] Visão Computacional iniciada na ROI: {roi}")
    votos_verde = 0
    votos_verm = 0

    while estado.rodando:
        try:
            t_inicio = time.perf_counter()
            screenshot = np.array(sct.grab(roi))
            img_bgr = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            verdes, vermelhos, cursor_usuario, pos_bola = processador.processar_frame(img_bgr)

            # Detecção de Time Estável (Histerese com 10 quadros de confirmação)
            modo = estado.config.get("modo_cor_time", "AUTO")
            if modo == "VERDE":
                estado.sou_time_verde = True
            elif modo == "VERMELHO":
                estado.sou_time_verde = False
            else:
                if cursor_usuario is not None:
                    dist_verde = min([math.hypot(cursor_usuario[0] - v[0], cursor_usuario[1] - v[1]) for v in verdes], default=999)
                    dist_verm = min([math.hypot(cursor_usuario[0] - r[0], cursor_usuario[1] - r[1]) for r in vermelhos], default=999)
                    if dist_verde < dist_verm and dist_verde < 18:
                        votos_verde += 1
                        votos_verm = 0
                        if votos_verde >= 10:
                            estado.sou_time_verde = True
                    elif dist_verm < dist_verde and dist_verm < 18:
                        votos_verm += 1
                        votos_verde = 0
                        if votos_verm >= 10:
                            estado.sou_time_verde = False

            meus_jogadores = verdes if estado.sou_time_verde else vermelhos
            adversarios = vermelhos if estado.sou_time_verde else verdes

            # Detecção da Direção do Ataque com Inércia
            atacando_direita = estado.atacando_direita
            if len(meus_jogadores) >= 4 and len(adversarios) >= 4:
                media_meu_x = np.mean([p[0] for p in meus_jogadores])
                media_adv_x = np.mean([p[0] for p in adversarios])
                atacando_direita = (media_meu_x < media_adv_x)
            estado.atacando_direita = atacando_direita

            # Linha de Impedimento Oficial IFAB
            linha_x = None
            if len(adversarios) >= 2:
                xs_adv = sorted([adv[0] for adv in adversarios], reverse=atacando_direita)
                linha_x = xs_adv[1]

            # Desenho HUD do Radar Zoom 3x
            altura_r, largura_r = img_bgr.shape[:2]
            overlay = img_bgr.copy()
            cor_meu = (0, 255, 0) if estado.sou_time_verde else (0, 0, 255)
            cor_adv = (0, 0, 255) if estado.sou_time_verde else (0, 255, 0)

            for adv in adversarios:
                cv2.circle(overlay, adv, 4, cor_adv, -1)
            for jog in meus_jogadores:
                cv2.circle(overlay, jog, 4, cor_meu, -1)
            if linha_x is not None:
                cv2.line(overlay, (linha_x, 0), (linha_x, altura_r), (0, 140, 255), 2)

            melhor_passe = None
            melhor_cruz = None

            if len(meus_jogadores) >= 2:
                portador = meus_jogadores[0]
                if cursor_usuario is not None:
                    # Ordena para colocar o jogador mais próximo do cursor como portador da bola
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - cursor_usuario[0], p[1] - cursor_usuario[1]))
                    portador = meus_jogadores[0]
                elif pos_bola is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - pos_bola[0], p[1] - pos_bola[1]))
                    portador = meus_jogadores[0]

                companheiros = [p for p in meus_jogadores if p != portador]

                # 1. Análise de Lançamento Y (Se por terra estiver bloqueado, usa cavada inteligente Q+W)
                livres, bloqueados = processador.analisar_linhas_de_passe(
                    portador, companheiros, adversarios,
                    atacando_direita=atacando_direita, linha_zaga=linha_x
                )
                todos_candidatos = [p for p in (livres + bloqueados) if not p.get("impedido", False)]
                todos_candidatos.sort(key=lambda x: x["score"], reverse=True)
                if todos_candidatos:
                    melhor_passe = todos_candidatos[0]
                    df = melhor_passe["destino_futuro"]
                    pts_arco = melhor_passe.get("pontos_arco", [])
                    tipo_p = melhor_passe.get("tipo_passe", "RASTEIRO")
                    if pts_arco and len(pts_arco) >= 2:
                        pts_arr = np.array(pts_arco, dtype=np.int32).reshape((-1, 1, 2))
                        cor_arco = (0, 220, 255) if tipo_p == "FENOMENAL_CURVA" else (0, 180, 255)
                        cv2.polylines(overlay, [pts_arr], isClosed=False, color=cor_arco, thickness=2, lineType=cv2.LINE_AA)
                        cv2.circle(overlay, df, 7, cor_arco, 2)
                        tag_txt = "TRIVELA RT+W" if tipo_p == "FENOMENAL_CURVA" else "CAVADO LB+W"
                        cv2.putText(overlay, tag_txt, (max(2, df[0] - 22), max(12, df[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, cor_arco, 1)
                    else:
                        cor_linha = (0, 240, 255) if melhor_passe.get("rompimento") else ((0, 200, 255) if melhor_passe.get("aereo") else (0, 255, 180))
                        cv2.line(overlay, portador, df, cor_linha, 2)
                        cv2.circle(overlay, df, 7, cor_linha, 2)

                # 2. Análise Tática Inteligente de Cruzamento (1ª Trave, 2ª Trave, Meia-Lua)
                melhor_cruz = processador.analisar_cruzamento_tatico(
                    portador, companheiros, adversarios,
                    atacando_direita=atacando_direita, linha_zaga=linha_x
                )
                if melhor_cruz:
                    df_c = melhor_cruz["destino_futuro"]
                    tag_c = melhor_cruz["tag_hud"]
                    tipo_c = melhor_cruz["tipo"]
                    cor_cruz = (255, 0, 200) if tipo_c == "FENOMENAL" else ((0, 220, 255) if tipo_c == "RASTEIRO" else ((0, 255, 255) if tipo_c in ("BALAO_ALTO", "ANTECIPADO") else (0, 255, 120)))
                    cv2.line(overlay, portador, df_c, cor_cruz, 1, cv2.LINE_AA)
                    cv2.circle(overlay, df_c, 5, cor_cruz, -1)
                    cv2.putText(overlay, tag_c, (max(2, df_c[0] - 25), max(10, df_c[1] + 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.32, cor_cruz, 1)

            if cursor_usuario is not None:
                cv2.circle(overlay, cursor_usuario, 7, (0, 255, 255), 2)
            if pos_bola is not None:
                cv2.circle(overlay, pos_bola, 3, (255, 255, 255), -1)

            with estado.lock:
                estado.radar_ativo = True
                estado.dados_passe = melhor_passe
                if melhor_passe:
                    estado.ultimo_passe_valido = melhor_passe
                estado.dados_cruzamento = melhor_cruz
                estado.cursor_usuario = cursor_usuario
                estado.pos_bola = pos_bola

            # Avaliação em tempo real da telemetria de lançamento teleguiado
            estado.telemetria.avaliar_frame(cursor_usuario, meus_jogadores, adversarios, pos_bola=pos_bola)

            # Exibe HUD com zoom 3x
            hud_zoom = cv2.resize(overlay, (largura_r * 3, altura_r * 3), interpolation=cv2.INTER_NEAREST)
            time_txt = "MANDANTE (VERDE)" if estado.sou_time_verde else "VISITANTE (VERMELHO)"
            dir_txt = "ATQ -> DIR" if atacando_direita else "ATQ <- ESQ"
            cv2.putText(hud_zoom, f"{time_txt} | {dir_txt}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # HUD Banner de Assertividade dos Lançamentos
            st_hud = estado.telemetria.obter_estatisticas()
            if st_hud["total"] > 0:
                txt_hud = f"ASSERTIVIDADE: {st_hud['taxa']:.0f}% ({st_hud['acertos']}/{st_hud['total']})"
                cor_hud = (0, 255, 100) if st_hud['taxa'] >= 70 else ((0, 220, 255) if st_hud['taxa'] >= 50 else (0, 80, 255))
                cv2.putText(hud_zoom, txt_hud, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor_hud, 2)

            cv2.imshow("eFootball Radar Tatico IA (60 FPS)", hud_zoom)

            if cv2.waitKey(1) & 0xFF == 27:
                estado.rodando = False
                break

            dt = time.perf_counter() - t_inicio
            time.sleep(max(0.001, (1.0 / 60.0) - dt))

        except Exception:
            time.sleep(0.015)

    cv2.destroyAllWindows()


# ==============================================================================
# 8. INTERFACE GRÁFICA MODERNA COM ABAS (TKINTER + TTK NOTEBOOK)
# ==============================================================================
class InterfaceMestre:
    def __init__(self, estado: EstadoSistema):
        self.estado = estado
        self.root = tk.Tk()
        self.root.title("⚽ eFootball Master AI & Controller Hub")
        self.root.geometry("600x520")
        self.root.configure(bg="#0c0c14")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.encerrar)

        # Configuração de Estilo ttk para abas escuras modernas
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TNotebook", background="#0c0c14", borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background="#161628",
            foreground="#8888aa",
            font=("Segoe UI", 9, "bold"),
            padding=[16, 7]
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", "#22223a"), ("active", "#1c1c32")],
            foreground=[("selected", "#00ffcc"), ("active", "#ffffff")]
        )
        self.style.configure(
            "Treeview",
            background="#121220",
            foreground="#ffffff",
            fieldbackground="#121220",
            rowheight=24,
            font=("Consolas", 9)
        )
        self.style.configure(
            "Treeview.Heading",
            background="#1c1c30",
            foreground="#00ffcc",
            font=("Segoe UI", 9, "bold")
        )
        self.style.map("Treeview", background=[('selected', '#2d2d50')])

        # Cabeçalho Superior Fixo
        topo = tk.Frame(self.root, bg="#121220", pady=8)
        topo.pack(fill="x")
        tk.Label(
            topo, text="⚡ EFOOTBALL MASTER AI & CONTROLLER HUB",
            font=("Segoe UI", 12, "bold"), fg="#00ffcc", bg="#121220"
        ).pack()
        tk.Label(
            topo, text="Injeção Direta DirectX + Radar Tático 60 FPS + Flydigi Vader 4 Pro",
            font=("Segoe UI", 8), fg="#8888aa", bg="#121220"
        ).pack()

        # Notebook com as Abas
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=8)

        # ABA 1: Visão Computacional & Configurações
        self.tab_visao = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_visao, text="  👁️ Visão Computacional  ")

        # ABA 2: Estatísticas de Lançamento Teleguiado
        self.tab_stats = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_stats, text="  📊 Estatísticas do Lançamento  ")

        self._construir_aba_visao()
        self._construir_aba_estatisticas()

        # Rodapé Fixo com Diagnóstico em Tempo Real
        self.lbl_tecla_monitor = tk.Label(
            self.root, text="🔑 Monitor: Aguardando toque no controle...",
            bg="#080810", fg="#666688", font=("Consolas", 9), pady=3
        )
        self.lbl_tecla_monitor.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(
            self.root, text="Iniciando...",
            bg="#0f0f1c", fg="#00ff88", font=("Segoe UI", 8), pady=3
        )
        self.lbl_status.pack(fill="x", side="bottom")

        self.atualizar_status()

    def _construir_aba_visao(self):
        # Detecção de Equipe
        frame_time = tk.LabelFrame(
            self.tab_visao, text=" Detecção de Equipe (Radar) ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=6
        )
        frame_time.pack(fill="x", padx=10, pady=6)

        self.var_modo = tk.StringVar(value=self.estado.config.get("modo_cor_time", "AUTO"))
        for val, txt in [
            ("AUTO", "Automático (Anel Amarelo sobre jogador com a bola)"),
            ("VERDE", "Forçar Verde (Mandante)"),
            ("VERMELHO", "Forçar Vermelho (Visitante)")
        ]:
            rb = tk.Radiobutton(
                frame_time, text=txt, value=val, variable=self.var_modo,
                command=self.mudar_modo, bg="#0c0c14", fg="#ffffff", selectcolor="#1c1c30",
                activebackground="#0c0c14", font=("Segoe UI", 9)
            )
            rb.pack(anchor="w", pady=1)

        # Tabela de Atalhos da IA
        frame_keys = tk.LabelFrame(
            self.tab_visao, text=" Atalhos das Ações Táticas da IA (Flydigi Space Station) ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=6
        )
        frame_keys.pack(fill="x", padx=10, pady=6)

        self.botoes_teclas = {}
        acoes = [
            ("lancamento_ia", "🎯 Lançamento Teleguiado IA (Y)", "W"),
            ("cruzamento_ia", "⚡ Cruzamento Inteligente IA (B)", "D"),
        ]

        for chave, nome, comando_jogo in acoes:
            linha = tk.Frame(frame_keys, bg="#0c0c14")
            linha.pack(fill="x", pady=2)
            tk.Label(linha, text=nome, font=("Segoe UI", 9), fg="#ffffff", bg="#0c0c14", width=32, anchor="w").pack(side="left")
            tk.Label(linha, text=f"-> {comando_jogo}", font=("Segoe UI", 8), fg="#ffaa00", bg="#0c0c14", width=10, anchor="w").pack(side="left")

            tecla_atual = self.estado.config["hotkeys"].get(chave, "?").upper()
            btn = tk.Button(
                linha, text=f"[ {tecla_atual} ]", font=("Consolas", 9, "bold"),
                bg="#1a1a2e", fg="#00ffcc", activebackground="#00ffcc", activeforeground="#000",
                width=8, command=lambda c=chave: self.capturar_tecla(c)
            )
            btn.pack(side="right")
            self.botoes_teclas[chave] = btn

        # Info de Resolução & Status de Visão
        frame_info = tk.LabelFrame(
            self.tab_visao, text=" Informações da Captura ",
            bg="#0c0c14", fg="#8888aa", font=("Segoe UI", 8, "bold"), padx=10, pady=4
        )
        frame_info.pack(fill="x", padx=10, pady=4)
        tk.Label(
            frame_info,
            text="• Captura a 60 FPS direta da tela via MSS e janela do Radar OpenCV 3x Zoom ativa.\n• Bhaskara cinemático prevê movimento futuro do recebedor e evita impedimentos.",
            bg="#0c0c14", fg="#777799", font=("Segoe UI", 8), justify="left"
        ).pack(anchor="w")

    def _construir_aba_estatisticas(self):
        # 1. Cards de Métricas (Top KPIs)
        frame_cards = tk.Frame(self.tab_stats, bg="#0c0c14")
        frame_cards.pack(fill="x", padx=10, pady=6)
        frame_cards.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        def _criar_card(pai, col, titulo, subtexto, cor_val="#00ffcc"):
            card = tk.Frame(pai, bg="#121220", padx=8, pady=6, highlightbackground="#1e1e32", highlightthickness=1)
            card.grid(row=0, column=col, padx=4, sticky="nsew")
            tk.Label(card, text=titulo, font=("Segoe UI", 8, "bold"), fg="#8888aa", bg="#121220").pack(anchor="center")
            lbl_val = tk.Label(card, text="--", font=("Segoe UI", 16, "bold"), fg=cor_val, bg="#121220")
            lbl_val.pack(anchor="center", pady=2)
            tk.Label(card, text=subtexto, font=("Segoe UI", 7), fg="#555577", bg="#121220").pack(anchor="center")
            return lbl_val

        self.lbl_card_taxa = _criar_card(frame_cards, 0, "PRECISÃO", "Taxa de acerto", "#00ff88")
        self.lbl_card_total = _criar_card(frame_cards, 1, "LANÇAMENTOS", "Acertos / Total", "#00ffcc")
        self.lbl_card_dist = _criar_card(frame_cards, 2, "DIST. MÉDIA", "Metros até o alvo", "#ffaa00")
        self.lbl_card_tempo = _criar_card(frame_cards, 3, "BARRA MÉDIA", "Tempo pressionado", "#ff77ff")

        # 2. Status do Lançamento Atual / Em voo
        self.lbl_status_voo = tk.Label(
            self.tab_stats, text="🎯 Pronto. Dispare o lançamento no controle para registrar...",
            bg="#10101c", fg="#aaaacc", font=("Segoe UI", 8, "italic"), pady=3
        )
        self.lbl_status_voo.pack(fill="x", padx=14, pady=3)

        # 3. Histórico dos Últimos Passes (Treeview)
        frame_tabela = tk.Frame(self.tab_stats, bg="#0c0c14")
        frame_tabela.pack(fill="both", expand=True, padx=10, pady=4)

        colunas = ("id", "hora", "dist", "barra", "tipo", "status")
        self.tree = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=5)
        self.tree.heading("id", text="#")
        self.tree.heading("hora", text="Hora")
        self.tree.heading("dist", text="Distância")
        self.tree.heading("barra", text="Barra")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("status", text="Resultado")

        self.tree.column("id", width=35, anchor="center")
        self.tree.column("hora", width=70, anchor="center")
        self.tree.column("dist", width=85, anchor="center")
        self.tree.column("barra", width=75, anchor="center")
        self.tree.column("tipo", width=70, anchor="center")
        self.tree.column("status", width=145, anchor="center")

        scroll = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Tags de cor para o Treeview
        self.tree.tag_configure("concluido", foreground="#00ff88")
        self.tree.tag_configure("interceptado", foreground="#ff5555")
        self.tree.tag_configure("fora", foreground="#ffaa00")
        self.tree.tag_configure("em_voo", foreground="#00e5ff")

        # 4. Barra de Ações Inferior
        frame_acoes = tk.Frame(self.tab_stats, bg="#0c0c14")
        frame_acoes.pack(fill="x", padx=10, pady=4)

        btn_zerar = tk.Button(
            frame_acoes, text="🔄 Zerar Estatísticas", font=("Segoe UI", 8, "bold"),
            bg="#2a1a1a", fg="#ff6666", activebackground="#ff4444", activeforeground="#ffffff",
            padx=10, pady=2, relief="flat", command=self.zerar_estatisticas
        )
        btn_zerar.pack(side="left")

        tk.Label(
            frame_acoes,
            text="* Acerto medido pela transferência do anel amarelo para o recebedor.",
            bg="#0c0c14", fg="#666688", font=("Segoe UI", 7)
        ).pack(side="right")

    def mudar_modo(self):
        with self.estado.lock:
            self.estado.config["modo_cor_time"] = self.var_modo.get()
            self.estado.salvar_config()

    def capturar_tecla(self, chave):
        self.botoes_teclas[chave].configure(text="Aperte tecla...", bg="#ffaa00", fg="#000")

        def _aguardar():
            ev = keyboard.read_event(suppress=False)
            while ev.event_type != keyboard.KEY_DOWN:
                ev = keyboard.read_event(suppress=False)
            nome = ev.name.lower()
            if nome.startswith("num ") and len(nome) == 5:
                nome = nome[-1]
            with self.estado.lock:
                self.estado.config["hotkeys"][chave] = nome
                self.estado.salvar_config()
            self.root.after(0, lambda: self.botoes_teclas[chave].configure(
                text=f"[ {nome.upper()} ]", bg="#1a1a2e", fg="#00ffcc"
            ))

        threading.Thread(target=_aguardar, daemon=True).start()

    def zerar_estatisticas(self):
        self.estado.telemetria.zerar()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_card_taxa.configure(text="0.0%", fg="#8888aa")
        self.lbl_card_total.configure(text="0 / 0")
        self.lbl_card_dist.configure(text="--")
        self.lbl_card_tempo.configure(text="--")
        self.lbl_status_voo.configure(text="🎯 Estatísticas zeradas. Pronto para novos lançamentos.")

    def atualizar_status(self):
        if not self.estado.rodando:
            self.root.destroy()
            return

        cor_str = "VERDE" if self.estado.sou_time_verde else "VERMELHO"
        dir_str = "Direita (->)" if self.estado.atacando_direita else "Esquerda (<-)"
        rp_str = "COM9 Ativo" if self.estado.rp2040_conectado else "DirectX Nativo"
        self.lbl_status.configure(
            text=f"Time: {cor_str} | Ataque: {dir_str} | Modo: {rp_str}"
        )

        ultima = _ultima_tecla[0]
        if ultima:
            hotkeys = self.estado.config.get("hotkeys", {})
            mapeadas = {v: k for k, v in hotkeys.items()}
            acao = mapeadas.get(ultima, "")
            if acao:
                self.lbl_tecla_monitor.configure(
                    text=f"🔑 Tecla recebida: [{ultima.upper()}] -> ✅ DISPARA: {acao}", fg="#00ff88"
                )
            else:
                self.lbl_tecla_monitor.configure(
                    text=f"🔑 Tecla recebida: [{ultima.upper()}] -> não mapeada", fg="#ffaa00"
                )

        # Atualiza Estatísticas e Tabela de Telemetria
        stats = self.estado.telemetria.obter_estatisticas()
        tot = stats["total"]
        certos = stats["acertos"]
        taxa = stats["taxa"]

        cor_taxa = "#00ff88" if taxa >= 70.0 else ("#ffaa00" if taxa >= 50.0 else "#ff5555")
        if tot == 0:
            cor_taxa = "#8888aa"

        self.lbl_card_taxa.configure(text=f"{taxa:.1f}%", fg=cor_taxa)
        self.lbl_card_total.configure(text=f"{certos} / {tot}")
        self.lbl_card_dist.configure(text=f"{stats['dist_media']:.1f} m" if tot > 0 else "--")
        self.lbl_card_tempo.configure(text=f"{stats['tempo_medio']:.0f} ms" if tot > 0 else "--")

        # Atualiza status em voo
        pv = self.estado.telemetria.passe_em_voo
        if pv and pv.get("status") == "EM_VOO":
            t_passado = time.perf_counter() - pv["t_disparo"]
            self.lbl_status_voo.configure(
                text=f"🚀 Lançamento em voo #{pv['id']} ({pv['dist_m']:.1f}m)... {t_passado:.1f}s (rastreando anel amarelo)",
                fg="#00e5ff"
            )
        else:
            if stats["historico"]:
                ultimo = stats["historico"][0]
                self.lbl_status_voo.configure(
                    text=f"Último lançamento #{ultimo['id']}: {ultimo['status']} ({ultimo['dist_m']:.1f}m - {ultimo['tempo_ms']}ms)",
                    fg="#00ff88" if "CONCLUÍDO" in ultimo["status"] else "#ff7777"
                )
            else:
                self.lbl_status_voo.configure(
                    text="🎯 Pronto. Dispare o lançamento no controle para registrar...",
                    fg="#aaaacc"
                )

        # Atualiza itens na Treeview se a lista mudar
        itens_atuais = self.tree.get_children()
        historico = stats["historico"]
        precisa_atualizar = False
        if len(itens_atuais) != len(historico):
            precisa_atualizar = True
        elif historico and itens_atuais:
            primeiro_item = self.tree.item(itens_atuais[0])['values']
            if len(primeiro_item) >= 6 and (str(primeiro_item[0]) != str(historico[0]["id"]) or str(primeiro_item[5]) != str(historico[0]["status"])):
                precisa_atualizar = True

        if precisa_atualizar:
            self.tree.delete(*itens_atuais)
            for p in historico:
                st = p["status"]
                tag = "concluido" if "CONCLUÍDO" in st else ("interceptado" if "INTERCEPTADO" in st else ("em_voo" if "EM_VOO" in st else "fora"))
                tipo_str = "Aéreo (Cavado)" if p.get("aereo") else "Rasteiro"
                self.tree.insert("", "end", values=(
                    p["id"],
                    p["hora"],
                    f"{p['dist_m']:.1f} m",
                    f"{p['tempo_ms']} ms",
                    tipo_str,
                    st
                ), tags=(tag,))

        self.root.after(150, self.atualizar_status)

    def encerrar(self):
        self.estado.rodando = False
        self.root.destroy()

    def iniciar(self):
        self.root.mainloop()


# ==============================================================================
# 9. PONTO DE ENTRADA PRINCIPAL (MAIN)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print("   ⚽ EFOOTBALL MASTER AI & CONTROLLER HUB - ALL-IN-ONE")
    print("   Injeção Direta DirectX + Radar 60 FPS + Flydigi Vader 4 Pro")
    print("=" * 65)

    estado_mestre = EstadoSistema()

    # 1. Inicia Thread de Controle (DirectX SendInput + Hardware RP2040)
    t_ctrl = threading.Thread(target=thread_controle_execucao, args=(estado_mestre,), daemon=True)
    t_ctrl.start()

    # 2. Inicia Thread de Visão Computacional (MSS + OpenCV a 60 FPS)
    t_cv = threading.Thread(target=thread_visao_radar, args=(estado_mestre,), daemon=True)
    t_cv.start()

    # 3. Inicia Interface Gráfica (Tkinter na thread principal)
    gui = InterfaceMestre(estado_mestre)
    gui.iniciar()
