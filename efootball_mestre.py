"""
================================================================================
   EFOOTBALL MASTER AI & CONTROLLER HUB - ALL-IN-ONE (VERSÃO V2.2 xG)
================================================================================
Projeto Unificado de Assistência Tática em Tempo Real para eFootball (PC).
Compatível com versões MICROSOFT STORE / XBOX APP e STEAM.

Destaques da V2.2:
- Motor Tático de Finalização Inteligente Baseado em Expected Goals (xG Logístico)
- Mira 360° no Canto Descoberto (Contra-Pé do Goleiro)
- Seleção Dinâmica: Cavadinha (LB+X), Colocado (RB+X), Fenomenal (RT+X), Rasteiro (X)
- Calibração de Barra Balística com Hard Cap de 265ms (Anti-Isolada por cima do gol)
- Mira Automática 360° Real (Injeção vetorial no RP2040 e 8-Way no DirectX)
- Máquina de Estados Não-Bloqueante com Sincronia Bit-a-Bit (Suporta Duplo Toque D+D no RP2040)
- Escala Anisotrópica Oficial FIFA/IFAB (105m x 68m)
- Rastreamento Cinemático Global + Desaglutinação por Transformada de Distância (Escanteios)
- Equação de Bhaskara de 2 Estágios (Recalcula interceptação conforme velocidade do passe)
- Memória de Orientação Corporal (Contra-Pé) + Modo Desafogo Direcional Rápido
- Regra de Impedimento IFAB Completa (Meio-Campo + Compensação de Goleiro Ocluso)
================================================================================
"""

import os
import sys
import time
import math
import json
import copy
import struct
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk

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

sys.stdout.reconfigure(line_buffering=True)

# ==============================================================================
# 1. INJEÇÃO DE ENTRADAS NATIVAS DIRECTX (WINDOWS 64-BIT SAFE SENDINPUT)
# ==============================================================================
ULONG_PTR = wintypes.WPARAM

class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR)
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR)
    ]

class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput)
    ]

class Input(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("ii", Input_I)
    ]

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# Scancodes de hardware DirectX (Padrão Oficial eFootball PC):
SCAN_W = 0x11     # Lançamento em Profundidade (Through Ball / Botão Y)
SCAN_D = 0x20     # Cruzamento / Passe Longo (Lofted Pass / Botão B)
SCAN_A = 0x1E     # Chute / Finalização (Shoot / Botão X)
SCAN_S = 0x1F     # Passe Curto (Short Pass / Botão A)
SCAN_Q = 0x10     # Troca de Cursor / Modificador Cavado (Botão LB / L1)
SCAN_E = 0x12     # Sprint / Passe Fenomenal (Botão RT / R2)
SCAN_C = 0x2E     # Controle Especial (Botão RB / R1)
SCAN_Z = 0x2C     # Controle Manual (Botão LT / L2)

# Setas direcionais (Extended Scancodes para Mira 8-Direções no Teclado)
SCAN_UP = 0x48
SCAN_DOWN = 0x50
SCAN_LEFT = 0x4B
SCAN_RIGHT = 0x4D
EXTENDED_SCANS = {SCAN_UP, SCAN_DOWN, SCAN_LEFT, SCAN_RIGHT}

# Constantes de botões do Gamepad (RP2040 Bridge)
BTN_A = 0
BTN_B = 1
BTN_X = 2
BTN_Y = 3
BTN_LB = 4
BTN_RB = 5
BTN_LT_DIGITAL = 10
BTN_RT_DIGITAL = 11

# Mapeamento automático Scancode -> Bit de Botão RP2040 para sincronia de múltiplos toques
SCANCODE_TO_RP2040_BTN = {
    SCAN_S: (1 << BTN_A),
    SCAN_D: (1 << BTN_B),
    SCAN_A: (1 << BTN_X),
    SCAN_W: (1 << BTN_Y),
    SCAN_Q: (1 << BTN_LB),
    SCAN_C: (1 << BTN_RB),
    SCAN_Z: (1 << BTN_LT_DIGITAL),
    SCAN_E: (1 << BTN_RT_DIGITAL),
}

_ignorando_hook = False

def directx_press(scancode):
    """Pressiona tecla a nível de hardware via SendInput DirectX 64-bit."""
    global _ignorando_hook
    _ignorando_hook = True
    try:
        flags = KEYEVENTF_SCANCODE
        if scancode in EXTENDED_SCANS:
            flags |= KEYEVENTF_EXTENDEDKEY
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, flags, 0, 0)
        x = Input(1, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
    except Exception:
        pass
    finally:
        _ignorando_hook = False

def directx_release(scancode):
    """Solta tecla a nível de hardware DirectX."""
    global _ignorando_hook
    _ignorando_hook = True
    try:
        flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        if scancode in EXTENDED_SCANS:
            flags |= KEYEVENTF_EXTENDEDKEY
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, flags, 0, 0)
        x = Input(1, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
    except Exception:
        pass
    finally:
        _ignorando_hook = False

def directx_liberar_tudo():
    """Garante que nenhuma tecla de ação ou direção fique presa no Windows."""
    for sc in (SCAN_W, SCAN_D, SCAN_A, SCAN_S, SCAN_Q, SCAN_E, SCAN_C, SCAN_Z,
               SCAN_UP, SCAN_DOWN, SCAN_LEFT, SCAN_RIGHT):
        directx_release(sc)

def obter_scancodes_direcao(dx, dy):
    """Converte um vetor (dx, dy) nas teclas direcionais (8 direções) do teclado."""
    norm = math.hypot(dx, dy)
    if norm < 1e-3:
        return []
    ux, uy = dx / norm, dy / norm
    teclas = []
    if ux > 0.3826:
        teclas.append(SCAN_RIGHT)
    elif ux < -0.3826:
        teclas.append(SCAN_LEFT)
    if uy > 0.3826:
        teclas.append(SCAN_DOWN)
    elif uy < -0.3826:
        teclas.append(SCAN_UP)
    return teclas


# ==============================================================================
# 2. CONFIGURAÇÕES PADRÃO E ARQUIVO JSON DINÂMICO
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_visao.json")

RADAR_ROI_PADRAO = {
    "top": 890,
    "left": 830,
    "width": 260,
    "height": 130
}

DEFAULT_CONFIG = {
    "radar_roi": RADAR_ROI_PADRAO,
    "hotkeys": {
        "chute_ia":          "4",
        "lancamento_ia":     "5",
        "cruzamento_ia":     "6",
        "inverter_cor_time": "f10"
    },
    "modo_cor_time": "AUTO",
    "usar_mira_automatica_360": True,
    "modo_desafogo_pressao": True,
    "usar_finalizacao_inteligente": True
}

# Dimensões oficiais do gramado IFAB/eFootball em metros
CAMPO_LARGURA_M = 105.0
CAMPO_ALTURA_M = 68.0


# ==============================================================================
# 3. MOTOR DE VISÃO COMPUTACIONAL, CINEMÁTICA E BALÍSTICA (OPENCV)
# ==============================================================================
class KinematicPlayerTracker:
    """
    Rastreador Cinemático com Associação Global por Menor Distância (Global Nearest Neighbor)
    e Filtro Exponencial Móvel (EMA) em metros por segundo (m/s).
    """
    def __init__(self, scale_x, scale_y, alpha=0.60, max_match_dist_m=9.5):
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.alpha = alpha
        self.max_match_dist_m = max_match_dist_m
        self.tracks = {}
        self.next_id = 0
        self.last_time = None

    def atualizar_escala(self, scale_x, scale_y):
        self.scale_x = scale_x
        self.scale_y = scale_y

    def _dist_metros(self, p1, p2):
        return math.hypot((p1[0] - p2[0]) * self.scale_x, (p1[1] - p2[1]) * self.scale_y)

    def update(self, detected_pts, current_time=None):
        if current_time is None:
            current_time = time.perf_counter()

        if self.last_time is None:
            dt = 1.0 / 60.0
        else:
            dt = max(0.008, min(0.20, current_time - self.last_time))
        self.last_time = current_time

        pares_candidatos = []
        for tid, track in self.tracks.items():
            pred_px = (
                track['pos'][0] + (track['vel_mps'][0] * dt) / self.scale_x,
                track['pos'][1] + (track['vel_mps'][1] * dt) / self.scale_y
            )
            for idx, pt in enumerate(detected_pts):
                d_m = self._dist_metros(pred_px, pt)
                if d_m <= self.max_match_dist_m:
                    pares_candidatos.append((d_m, tid, idx))

        pares_candidatos.sort(key=lambda x: x[0])

        tracks_usadas = set()
        dets_usadas = set()
        matched_velocities_mps = {}

        for d_m, tid, idx in pares_candidatos:
            if tid in tracks_usadas or idx in dets_usadas:
                continue
            tracks_usadas.add(tid)
            dets_usadas.add(idx)

            pt = detected_pts[idx]
            track = self.tracks[tid]
            vx_raw = ((pt[0] - track['pos'][0]) * self.scale_x) / dt
            vy_raw = ((pt[1] - track['pos'][1]) * self.scale_y) / dt

            speed_mps = math.hypot(vx_raw, vy_raw)
            if speed_mps > 11.5:
                escala = 11.5 / speed_mps
                vx_raw *= escala
                vy_raw *= escala
            elif speed_mps < 0.8:
                vx_raw, vy_raw = 0.0, 0.0

            vx_smooth = self.alpha * vx_raw + (1.0 - self.alpha) * track['vel_mps'][0]
            vy_smooth = self.alpha * vy_raw + (1.0 - self.alpha) * track['vel_mps'][1]

            self.tracks[tid] = {'pos': pt, 'vel_mps': (vx_smooth, vy_smooth), 'lost': 0}
            matched_velocities_mps[pt] = (vx_smooth, vy_smooth)

        for tid in list(self.tracks.keys()):
            if tid not in tracks_usadas:
                self.tracks[tid]['lost'] += 1
                if self.tracks[tid]['lost'] > 5:
                    del self.tracks[tid]

        for idx, pt in enumerate(detected_pts):
            if idx not in dets_usadas:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = {'pos': pt, 'vel_mps': (0.0, 0.0), 'lost': 0}
                matched_velocities_mps[pt] = (0.0, 0.0)

        return matched_velocities_mps


def calcular_forca_balistica(distancia_metros, tipo_passe="RASTEIRO"):
    """
    Curva balística calibrada com atrito do gramado e velocidade média da bola (m/s).
    Retorna: (forca_barra [0..1], tempo_ms [int], vel_media_bola_mps [float])
    """
    d = max(5.0, min(58.0, float(distancia_metros)))
    dist_norm = (d - 5.0) / (58.0 - 5.0)
    forca_barra = 0.18 + 0.78 * (dist_norm ** 0.85)

    if tipo_passe in ("CAVADO_ARCO", "BALAO_ALTO", "ANTECIPADO"):
        forca_barra = min(1.0, forca_barra * 1.10)
        vel_bola_mps = 14.5 + 7.5 * dist_norm
    elif tipo_passe in ("FENOMENAL_CURVA", "FENOMENAL"):
        forca_barra = min(1.0, forca_barra * 1.05)
        vel_bola_mps = 22.0 + 10.0 * dist_norm
    else:
        vel_bola_mps = 16.5 + 8.5 * dist_norm

    forca_barra = max(0.16, min(1.0, forca_barra))
    tempo_ms = int(90.0 + forca_barra * 255.0)
    return forca_barra, tempo_ms, vel_bola_mps


class RadarPassesEFootball:
    def __init__(self, roi=None):
        self.roi = roi or RADAR_ROI_PADRAO
        self.scale_x = CAMPO_LARGURA_M / float(self.roi["width"])
        self.scale_y = CAMPO_ALTURA_M / float(self.roi["height"])
        self.kinematic_tracker = KinematicPlayerTracker(self.scale_x, self.scale_y, alpha=0.60)
        self.ultima_orientacao_portador = (1.0, 0.0)

        # Faixas de cor HSV calibradas para o eFootball
        self.verde_min = np.array([35, 45, 45])
        self.verde_max = np.array([85, 255, 255])
        self.verm_min1 = np.array([0, 70, 70])
        self.verm_max1 = np.array([10, 255, 255])
        self.verm_min2 = np.array([165, 70, 70])
        self.verm_max2 = np.array([180, 255, 255])

    def dist_metros(self, p1, p2):
        return math.hypot((p1[0] - p2[0]) * self.scale_x, (p1[1] - p2[1]) * self.scale_y)

    def _resolver_intercepcao_bhaskara(self, portador, comp, vx_m, vy_m, v_bola_mps):
        """Resolve analiticamente o ponto futuro (x, y) para uma velocidade de bola específica."""
        largura_campo = self.roi["width"]
        altura_campo = self.roi["height"]
        dx0_m = (comp[0] - portador[0]) * self.scale_x
        dy0_m = (comp[1] - portador[1]) * self.scale_y
        dist_atual_m = math.hypot(dx0_m, dy0_m)

        A = (vx_m**2 + vy_m**2) - (v_bola_mps**2)
        B = 2.0 * (dx0_m * vx_m + dy0_m * vy_m)
        C = dx0_m**2 + dy0_m**2
        discriminante = B**2 - 4.0 * A * C

        t_star = None
        if discriminante >= 0 and abs(A) > 1e-4:
            sqrt_disc = math.sqrt(discriminante)
            t1 = (-B - sqrt_disc) / (2.0 * A)
            t2 = (-B + sqrt_disc) / (2.0 * A)
            candidatos_t = [t for t in (t1, t2) if t > 0.05]
            if candidatos_t:
                t_star = min(candidatos_t)

        if t_star is None or t_star > 1.80:
            t_star = dist_atual_m / max(10.0, v_bola_mps)
        t_star = max(0.08, min(1.15, t_star))

        pred_x = int(round(comp[0] + (vx_m * t_star) / self.scale_x))
        pred_y = int(round(comp[1] + (vy_m * t_star) / self.scale_y))
        return (
            max(3, min(largura_campo - 3, pred_x)),
            max(3, min(altura_campo - 3, pred_y))
        )

    def _extrair_pontos_de_mascara(self, mascara, area_min=4, area_single_max=52, area_merged_max=420):
        """
        Extrai centroides de jogadores e desaglutina aglomerações de 2 a 6 jogadores
        (ex: escanteios na pequena área) usando Transformada de Distância (Distance Transform).
        """
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        pontos = []
        for c in contornos:
            area = cv2.contourArea(c)
            if area < area_min or area > area_merged_max:
                continue
            if area <= area_single_max:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    pontos.append((int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])))
            else:
                # Múltiplos jogadores colados: isola o ROI do contorno e aplica Distance Transform
                x, y, w, h = cv2.boundingRect(c)
                sub_mask = np.zeros((h + 4, w + 4), dtype=np.uint8)
                c_shifted = c - np.array([[x - 2, y - 2]])
                cv2.drawContours(sub_mask, [c_shifted], -1, 255, -1)

                dist_map = cv2.distanceTransform(sub_mask, cv2.DIST_L2, 3)
                kernel_max = np.ones((5, 5), np.uint8)
                dilated = cv2.dilate(dist_map, kernel_max)
                picos_y, picos_x = np.where((dist_map == dilated) & (dist_map >= 1.4))

                picos_filtrados = []
                for px, py in zip(picos_x, picos_y):
                    pt_global = (int(x - 2 + px), int(y - 2 + py))
                    if all(math.hypot(pt_global[0] - p[0], pt_global[1] - p[1]) >= 4.0 for p in picos_filtrados):
                        picos_filtrados.append(pt_global)

                if len(picos_filtrados) >= 2:
                    pontos.extend(picos_filtrados[:6])
                else:
                    # Fallback geométrico proporcional ao número estimado de jogadores
                    n_est = max(2, min(4, int(round(area / 32.0))))
                    for k in range(n_est):
                        frac = (k + 0.5) / n_est
                        if w >= h:
                            pontos.append((int(x + w * frac), int(y + h * 0.50)))
                        else:
                            pontos.append((int(x + w * 0.50), int(y + h * frac)))
        return pontos

    def processar_frame(self, frame_bgr, cursor_anterior=None, bola_anterior=None):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # 1. Jogadores Verdes
        masc_verde = cv2.inRange(hsv, self.verde_min, self.verde_max)
        masc_verde = cv2.morphologyEx(masc_verde, cv2.MORPH_OPEN, kernel)
        verdes = self._extrair_pontos_de_mascara(masc_verde)

        # 2. Jogadores Vermelhos
        masc_v1 = cv2.inRange(hsv, self.verm_min1, self.verm_max1)
        masc_v2 = cv2.inRange(hsv, self.verm_min2, self.verm_max2)
        masc_verm = cv2.bitwise_or(masc_v1, masc_v2)
        masc_verm = cv2.morphologyEx(masc_verm, cv2.MORPH_OPEN, kernel)
        vermelhos = self._extrair_pontos_de_mascara(masc_verm)

        todos_jogadores = verdes + vermelhos

        # 3. Anel Amarelo/Dourado do Cursor
        masc_anel = cv2.inRange(hsv, np.array([16, 65, 115]), np.array([38, 255, 255]))
        masc_anel = cv2.dilate(masc_anel, kernel, iterations=1)
        contornos_a, _ = cv2.findContours(masc_anel, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        cursor_usuario = None
        melhor_score_anel = float('inf')
        for ca in contornos_a:
            area_a = cv2.contourArea(ca)
            if 4 <= area_a <= 380:
                Ma = cv2.moments(ca)
                if Ma["m00"] > 0:
                    cand = (int(Ma["m10"] / Ma["m00"]), int(Ma["m01"] / Ma["m00"]))
                    dist_jog = min([math.hypot(cand[0] - j[0], cand[1] - j[1]) for j in todos_jogadores], default=25.0)
                    dist_ant = math.hypot(cand[0] - cursor_anterior[0], cand[1] - cursor_anterior[1]) if cursor_anterior else 0.0
                    score_a = dist_jog + dist_ant * 0.25
                    if score_a < melhor_score_anel and dist_jog < 16.0:
                        melhor_score_anel = score_a
                        cursor_usuario = cand

        # 4. Ponto da Bola
        masc_bola = cv2.inRange(hsv, np.array([0, 0, 190]), np.array([180, 50, 255]))
        contornos_b, _ = cv2.findContours(masc_bola, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        pos_bola = None
        melhor_score_bola = float('inf')
        for cb in contornos_b:
            area_b = cv2.contourArea(cb)
            if 2 <= area_b <= 32:
                perimetro = cv2.arcLength(cb, True)
                if perimetro <= 0:
                    continue
                circularidade = 4 * math.pi * area_b / (perimetro * perimetro)
                if circularidade < 0.35:
                    continue
                Mb = cv2.moments(cb)
                if Mb["m00"] > 0:
                    cand_b = (int(Mb["m10"] / Mb["m00"]), int(Mb["m01"] / Mb["m00"]))
                    dist_jog = min([math.hypot(cand_b[0] - j[0], cand_b[1] - j[1]) for j in todos_jogadores], default=40.0)
                    dist_ant = math.hypot(cand_b[0] - bola_anterior[0], cand_b[1] - bola_anterior[1]) if bola_anterior else dist_jog
                    score_b = dist_ant * 0.6 + dist_jog * 0.4
                    if score_b < melhor_score_bola:
                        melhor_score_bola = score_b
                        pos_bola = cand_b

        return verdes, vermelhos, cursor_usuario, pos_bola

    def calcular_linha_impedimento_ifab(self, adversarios, atacando_direita=True):
        """
        Calcula a linha do penúltimo defensor (Lei 11 IFAB) compensando
        eventual oclusão do goleiro sobre a linha branca de fundo.
        """
        if not adversarios:
            return None
        largura_campo = self.roi["width"]
        xs_adv = sorted([adv[0] for adv in adversarios], reverse=atacando_direita)

        if atacando_direita:
            tem_goleiro_detectado = (xs_adv[0] >= largura_campo - 14)
        else:
            tem_goleiro_detectado = (xs_adv[0] <= 14)

        if tem_goleiro_detectado and len(xs_adv) >= 2:
            return xs_adv[1]
        else:
            return xs_adv[0]

    def analisar_linhas_de_passe(self, portador, companheiros, adversarios, atacando_direita=True, linha_zaga=None, analog_dir=(0.0, 0.0), modo_desafogo=True):
        livres = []
        bloqueados = []
        largura_campo = self.roi["width"]
        altura_campo = self.roi["height"]
        meio_campo_x = largura_campo / 2.0
        gol_alvo_x = largura_campo if atacando_direita else 0

        todos_meus = [portador] + [c for c in companheiros if c != portador]
        velocidades_mps = self.kinematic_tracker.update(todos_meus)
        vx_port_m, vy_port_m = velocidades_mps.get(portador, (0.0, 0.0))
        portador_speed_mps = math.hypot(vx_port_m, vy_port_m)

        # Atualiza a memória de orientação corporal do portador
        an_x, an_y = analog_dir
        an_norm = math.hypot(an_x, an_y)
        if portador_speed_mps > 1.2:
            self.ultima_orientacao_portador = (vx_port_m / portador_speed_mps, vy_port_m / portador_speed_mps)
        elif an_norm > 0.18:
            self.ultima_orientacao_portador = (an_x / an_norm, an_y / an_norm)

        orient_x, orient_y = self.ultima_orientacao_portador

        # Encontra o adversário mais próximo e seu vetor relativo ao portador
        adv_mais_prox = None
        dist_adv_mais_proximo = 99.0
        for adv in adversarios:
            d_adv = self.dist_metros(portador, adv)
            if d_adv < dist_adv_mais_proximo:
                dist_adv_mais_proximo = d_adv
                adv_mais_prox = adv

        for comp in companheiros:
            dist_atual_m = self.dist_metros(portador, comp)
            if dist_atual_m < 3.0:
                continue

            vx_m, vy_m = velocidades_mps.get(comp, (0.0, 0.0))
            comp_speed_mps = math.hypot(vx_m, vy_m)

            # Passo 1 de Bhaskara: Estimativa com velocidade rasteira
            _, _, v_bola_rasteira = calcular_forca_balistica(dist_atual_m, "RASTEIRO")
            destino_futuro = self._resolver_intercepcao_bhaskara(portador, comp, vx_m, vy_m, v_bola_rasteira)

            dx_fut_m = (destino_futuro[0] - portador[0]) * self.scale_x
            dy_fut_m = (destino_futuro[1] - portador[1]) * self.scale_y
            dist_fut_m = math.hypot(dx_fut_m, dy_fut_m)
            if dist_fut_m < 2.0:
                continue

            ang_passe_m = math.atan2(dy_fut_m, dx_fut_m)

            # Cone anti-bloqueio em metros reais
            bloqueado = False
            bloqueio_muito_proximo = False
            zagueiro_bloqueador = None

            for adv in adversarios:
                dx_adv_m = (adv[0] - portador[0]) * self.scale_x
                dy_adv_m = (adv[1] - portador[1]) * self.scale_y
                dist_adv_m = math.hypot(dx_adv_m, dy_adv_m)
                if dist_adv_m < dist_fut_m:
                    proj_m = (dx_adv_m * dx_fut_m + dy_adv_m * dy_fut_m) / (dist_fut_m + 1e-5)
                    if 0.5 < proj_m < dist_fut_m:
                        perp_m = abs(dx_adv_m * math.sin(ang_passe_m) - dy_adv_m * math.cos(ang_passe_m))
                        margem_seg_m = 1.8 + (proj_m / dist_fut_m) * 2.8
                        if perp_m < margem_seg_m:
                            bloqueado = True
                            zagueiro_bloqueador = adv
                            if proj_m < 4.5 and perp_m < 1.5:
                                bloqueio_muito_proximo = True
                            break

            # Regra Oficial de Impedimento IFAB (Lei 11)
            impedido = False
            rompimento = False

            no_campo_ataque = (comp[0] > meio_campo_x) if atacando_direita else (comp[0] < meio_campo_x)
            atras_da_bola = (comp[0] <= (portador[0] + 1.0)) if atacando_direita else (comp[0] >= (portador[0] - 1.0))

            if linha_zaga is not None and no_campo_ataque and not atras_da_bola:
                if atacando_direita:
                    if comp[0] > (linha_zaga + 1.2):
                        impedido = True
                    elif comp[0] <= (linha_zaga + 1.2) and destino_futuro[0] > (linha_zaga - 1.0) and vx_m > 2.2:
                        rompimento = True
                else:
                    if comp[0] < (linha_zaga - 1.2):
                        impedido = True
                    elif comp[0] >= (linha_zaga - 1.2) and destino_futuro[0] < (linha_zaga + 1.0) and vx_m < -2.2:
                        rompimento = True

            # Seleção Inteligente da Modalidade do Lançamento
            if bloqueado:
                tipo_passe = "CAVADO_ARCO"
            else:
                if (rompimento and dist_fut_m > 20.0) or dist_fut_m > 28.0:
                    tipo_passe = "FENOMENAL_CURVA"
                else:
                    tipo_passe = "RASTEIRO"

            # Passo 2 de Bhaskara: Se o tipo de passe mudou para aéreo ou fenomenal,
            # recalcula o ponto de interceptação futuro e o vetor 360° com a velocidade exata da modalidade!
            if tipo_passe != "RASTEIRO":
                _, _, v_bola_real = calcular_forca_balistica(dist_fut_m, tipo_passe)
                destino_futuro = self._resolver_intercepcao_bhaskara(portador, comp, vx_m, vy_m, v_bola_real)
                dx_fut_m = (destino_futuro[0] - portador[0]) * self.scale_x
                dy_fut_m = (destino_futuro[1] - portador[1]) * self.scale_y
                dist_fut_m = max(2.0, math.hypot(dx_fut_m, dy_fut_m))

            vetor_direcao = (dx_fut_m / dist_fut_m, dy_fut_m / dist_fut_m)
            forca_b, tempo_ms, _ = calcular_forca_balistica(dist_fut_m, tipo_passe=tipo_passe)

            # Gera arco visual no HUD caso o passe seja cavado
            pontos_arco = []
            apex = None
            if tipo_passe == "CAVADO_ARCO":
                dist_px_chord = math.hypot(destino_futuro[0] - portador[0], destino_futuro[1] - portador[1]) + 1e-5
                n_x = -(destino_futuro[1] - portador[1]) / dist_px_chord
                n_y = (destino_futuro[0] - portador[0]) / dist_px_chord
                apx = int((portador[0] + destino_futuro[0]) * 0.5 + n_x * 12.0)
                apy = int((portador[1] + destino_futuro[1]) * 0.5 + n_y * 12.0)
                apex = (max(2, min(largura_campo - 2, apx)), max(2, min(altura_campo - 2, apy)))
                for step in range(8):
                    t_b = step / 7.0
                    bx = int((1.0 - t_b)**2 * portador[0] + 2.0 * (1.0 - t_b) * t_b * apex[0] + t_b**2 * destino_futuro[0])
                    by = int((1.0 - t_b)**2 * portador[1] + 2.0 * (1.0 - t_b) * t_b * apex[1] + t_b**2 * destino_futuro[1])
                    pontos_arco.append((bx, by))

            # 1. Alinhamento Corporal (Contra-Pé com memória de última orientação)
            cos_alinhamento = orient_x * vetor_direcao[0] + orient_y * vetor_direcao[1]

            # 2. Modo Desafogo Direcional Rápido Sob Pressão (< 1.9m)
            sob_pressao_alta = False
            if modo_desafogo and adv_mais_prox is not None and dist_adv_mais_proximo < 1.9:
                sob_pressao_alta = True
                # Se for passe fenomenal, cancela o RT sob pressão para evitar animação longa de 0.6s
                if tipo_passe == "FENOMENAL_CURVA":
                    tipo_passe = "RASTEIRO"
                    forca_b, tempo_ms, _ = calcular_forca_balistica(dist_fut_m, tipo_passe="RASTEIRO")
                # Só encurta o tempo de barra em passes rasteiros (não enfraquece passes cavados)
                if tipo_passe == "RASTEIRO":
                    tempo_ms = max(85, int(tempo_ms * 0.82))

            avanco_ofensivo_m = ((destino_futuro[0] - portador[0]) if atacando_direita else (portador[0] - destino_futuro[0])) * self.scale_x
            dist_gol_m = abs(gol_alvo_x - destino_futuro[0]) * self.scale_x
            folga_rec_m = min([self.dist_metros(destino_futuro, adv) for adv in adversarios], default=25.0)

            score = 100.0 - dist_gol_m * 1.15 + avanco_ofensivo_m * 1.10 + (comp_speed_mps * 3.6) * 0.45 + min(10.0, folga_rec_m * 1.2)
            if bloqueado:
                score -= 28.0 if bloqueio_muito_proximo else 14.0
            if impedido:
                score -= 120.0
            if rompimento:
                score += 35.0

            if cos_alinhamento > 0.50:
                score += 15.0 * cos_alinhamento
            elif cos_alinhamento < -0.30:
                score -= 20.0 * abs(cos_alinhamento)

            item = {
                "origem": portador,
                "destino": comp,
                "destino_futuro": destino_futuro,
                "vetor_direcao": vetor_direcao,
                "velocidade_kmh": comp_speed_mps * 3.6,
                "dist_metros": dist_fut_m,
                "forca_barra": forca_b,
                "tempo_ms": tempo_ms,
                "aereo": (tipo_passe == "CAVADO_ARCO"),
                "tipo_passe": tipo_passe,
                "pontos_arco": pontos_arco,
                "apex": apex,
                "zagueiro_bloqueador": zagueiro_bloqueador,
                "impedido": impedido,
                "rompimento": rompimento,
                "sob_pressao": sob_pressao_alta,
                "cos_alinhamento": cos_alinhamento,
                "score": score
            }

            if bloqueado and not impedido:
                bloqueados.append(item)
            else:
                livres.append(item)

        livres.sort(key=lambda x: x["score"], reverse=True)
        bloqueados.sort(key=lambda x: x["score"], reverse=True)
        return livres, bloqueados

    def analisar_cruzamento_tatico(self, portador, companheiros, adversarios, atacando_direita=True, linha_zaga=None):
        """
        Motor Tático de Cruzamento Inteligente com Escala Anisotrópica Real (105m x 68m)
        e Vetor Direcional 360°.
        """
        largura_campo = self.roi["width"]
        altura_campo = self.roi["height"]
        meio_campo_x = largura_campo / 2.0
        gol_alvo_x = largura_campo if atacando_direita else 0
        centro_y = altura_campo / 2.0
        dir_atq = 1 if atacando_direita else -1

        dist_fundo_m = abs(gol_alvo_x - portador[0]) * self.scale_x

        offset_trave_px = int(9.0 / self.scale_y)
        y_trave_sup = int(centro_y - offset_trave_px)
        y_trave_inf = int(centro_y + offset_trave_px)

        if portador[1] <= centro_y:
            y_1a_trave, y_2a_trave = y_trave_sup, y_trave_inf
        else:
            y_1a_trave, y_2a_trave = y_trave_inf, y_trave_sup

        no_escanteio = (dist_fundo_m <= 6.5 and (portador[1] * self.scale_y <= 11.0 or (altura_campo - portador[1]) * self.scale_y <= 11.0))

        candidatos_cruz = []

        for comp in companheiros:
            dist_gol_x_m = abs(gol_alvo_x - comp[0]) * self.scale_x
            if dist_gol_x_m > 26.0:
                continue

            impedido = False
            no_campo_ataque = (comp[0] > meio_campo_x) if atacando_direita else (comp[0] < meio_campo_x)
            if not no_escanteio and linha_zaga is not None and no_campo_ataque:
                if atacando_direita:
                    if comp[0] > (linha_zaga + 1.2) and comp[0] > (portador[0] + 1.0):
                        impedido = True
                else:
                    if comp[0] < (linha_zaga - 1.2) and comp[0] < (portador[0] - 1.0):
                        impedido = True

            if impedido:
                continue

            dist_1a_m = abs(comp[1] - y_1a_trave) * self.scale_y
            dist_2a_m = abs(comp[1] - y_2a_trave) * self.scale_y

            if dist_gol_x_m > 16.0:
                setor = "ENTRADA_AREA"
            elif dist_1a_m <= dist_2a_m:
                setor = "1A_TRAVE"
            else:
                setor = "2A_TRAVE"

            folga_def_m = min([self.dist_metros(comp, adv) for adv in adversarios], default=30.0)
            marcado = (folga_def_m < 3.8)

            avanco_px = int((min(5.0, dist_gol_x_m * 0.25)) / self.scale_x)
            cx_fut = int(comp[0] + dir_atq * avanco_px)
            alvo_y_setor = y_1a_trave if setor == "1A_TRAVE" else (y_2a_trave if setor == "2A_TRAVE" else int(centro_y))
            cy_fut = int(comp[1] + (alvo_y_setor - comp[1]) * 0.25)
            destino_futuro = (max(2, min(largura_campo - 2, cx_fut)), max(2, min(altura_campo - 2, cy_fut)))

            dx_c_m = (destino_futuro[0] - portador[0]) * self.scale_x
            dy_c_m = (destino_futuro[1] - portador[1]) * self.scale_y
            dist_cruz_m = math.hypot(dx_c_m, dy_c_m)
            if dist_cruz_m < 3.0:
                continue

            vetor_direcao = (dx_c_m / dist_cruz_m, dy_c_m / dist_cruz_m)
            ang_c_m = math.atan2(dy_c_m, dx_c_m)

            bloqueio_frontal = False
            bloqueio_trajetoria = False

            for adv in adversarios:
                dx_a_m = (adv[0] - portador[0]) * self.scale_x
                dy_a_m = (adv[1] - portador[1]) * self.scale_y
                dist_a_m = math.hypot(dx_a_m, dy_a_m)

                if dist_a_m < 3.2:
                    prod_proj = (dx_a_m * dx_c_m + dy_a_m * dy_c_m) / dist_cruz_m
                    if prod_proj > 0:
                        bloqueio_frontal = True

                if dist_a_m < dist_cruz_m:
                    proj_m = (dx_a_m * dx_c_m + dy_a_m * dy_c_m) / dist_cruz_m
                    if 2.5 < proj_m < (dist_cruz_m - 2.5):
                        dist_perp_m = abs(dx_a_m * math.sin(ang_c_m) - dy_a_m * math.cos(ang_c_m))
                        if dist_perp_m < 2.5:
                            bloqueio_trajetoria = True

            tipo_cruz = "CABEÇA"
            tag_hud = "CRUZAMENTO D"

            if no_escanteio:
                if setor == "2A_TRAVE":
                    tipo_cruz, tag_hud = "BALAO_ALTO", "ESCANTEIO 2ª TRAVE LB+D"
                elif setor == "1A_TRAVE":
                    tipo_cruz, tag_hud = "CABEÇA", "ESCANTEIO 1ª TRAVE D"
                else:
                    tipo_cruz, tag_hud = "RASTEIRO", "ESCANTEIO CURTO D+D"
            elif setor == "1A_TRAVE":
                if dist_gol_x_m < 14.0 and not bloqueio_frontal and not bloqueio_trajetoria:
                    tipo_cruz, tag_hud = "RASTEIRO", "1ª TRAVE RASTEIRO D+D"
                elif dist_fundo_m > 20.0:
                    tipo_cruz, tag_hud = "ANTECIPADO", "1ª TRAVE ANTECIPADO LB+D"
                else:
                    tipo_cruz, tag_hud = "CABEÇA", "1ª TRAVE CABEÇA D"
            elif setor == "2A_TRAVE":
                if dist_fundo_m > 22.0:
                    tipo_cruz, tag_hud = "ANTECIPADO", "2ª TRAVE ANTECIPADO LB+D"
                elif dist_fundo_m <= 16.0 or bloqueio_trajetoria or bloqueio_frontal:
                    tipo_cruz, tag_hud = "BALAO_ALTO", "2ª TRAVE BALÃO LB+D"
                elif dist_cruz_m > 34.0 and not bloqueio_frontal:
                    tipo_cruz, tag_hud = "FENOMENAL", "2ª TRAVE FENOMENAL RT+D"
                else:
                    tipo_cruz, tag_hud = "CABEÇA", "2ª TRAVE CABEÇA D"
            else:
                if bloqueio_frontal or bloqueio_trajetoria:
                    tipo_cruz, tag_hud = "CABEÇA", "MEIA-LUA PELO ALTO D"
                else:
                    tipo_cruz, tag_hud = "RASTEIRO", "MEIA-LUA ATRASADO D+D"

            score = 100.0 - dist_gol_x_m * 1.2 + folga_def_m * 4.5
            if setor == "2A_TRAVE" and not marcado:
                score += 28.0
            elif setor == "1A_TRAVE" and not marcado:
                score += 20.0
            if marcado:
                score -= 32.0
            if bloqueio_trajetoria and setor == "1A_TRAVE":
                score -= 25.0
            if bloqueio_frontal:
                score -= 10.0

            forca_c, tempo_c, _ = calcular_forca_balistica(dist_cruz_m, tipo_passe=tipo_cruz)

            candidatos_cruz.append({
                "origem": portador,
                "destino": comp,
                "destino_futuro": destino_futuro,
                "vetor_direcao": vetor_direcao,
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

    def analisar_finalizacao_xg(self, portador, companheiros, adversarios, atacando_direita=True):
        """
        Motor Tático de Finalização Inteligente Baseado em Expected Goals (xG).
        - Mira 360° no Canto Descoberto (Contra-Pé do Goleiro)
        - Seleção Automática de Chute: Cavadinha (LB+X), Colocado (RB+X), Fenomenal (RT+X), Rasteiro Forte (X)
        - Curva de Tempo de Barra Anti-Isolada (Hard Cap 265ms)
        """
        if portador is None:
            return None

        largura_campo = self.roi["width"]
        altura_campo = self.roi["height"]
        centro_y = altura_campo / 2.0
        meio_campo_x = largura_campo / 2.0
        gol_alvo_x = float(largura_campo) if atacando_direita else 0.0

        dx_gol_m = (gol_alvo_x - portador[0]) * self.scale_x
        dy_gol_m = (centro_y - portador[1]) * self.scale_y
        dist_gol_m = math.hypot(dx_gol_m, dy_gol_m)

        # Só finaliza se estiver no campo de ataque e a uma distância viável (<= 36 metros)
        no_campo_ataque = (portador[0] >= meio_campo_x) if atacando_direita else (portador[0] <= meio_campo_x)
        if not no_campo_ataque or dist_gol_m > 36.0 or dist_gol_m < 1.0:
            return None

        # 1. Identificação do Goleiro Adversário (defensor mais próximo da linha de fundo do gol alvo)
        adv_ordenados = sorted(adversarios, key=lambda a: abs(gol_alvo_x - a[0])) if adversarios else []
        goleiro = adv_ordenados[0] if adv_ordenados else None
        dist_gk_linha_m = abs(gol_alvo_x - goleiro[0]) * self.scale_x if goleiro else 1.0
        gk_y = goleiro[1] if goleiro else centro_y

        # 2. Geometria da Baliza Oficial IFAB (7.32m de largura)
        trave_metade_m = 3.66
        offset_trave_px = trave_metade_m / self.scale_y
        y_trave_sup = centro_y - offset_trave_px
        y_trave_inf = centro_y + offset_trave_px

        # Margem de segurança interna da trave (1.1m para garantir bola na rede sem beijar o poste)
        margem_trave_px = 1.1 / self.scale_y
        y_canto_sup = y_trave_sup + margem_trave_px
        y_canto_inf = y_trave_inf - margem_trave_px

        # 3. Mira no Canto Descoberto (Contra-Pé do Goleiro)
        if gk_y <= centro_y:
            # Goleiro cobrindo o setor superior -> bater no canto inferior
            alvo_canto = (int(gol_alvo_x), int(round(y_canto_inf)))
            canto_nome = "CANTO INFERIOR"
        else:
            # Goleiro cobrindo o setor inferior -> bater no canto superior
            alvo_canto = (int(gol_alvo_x), int(round(y_canto_sup)))
            canto_nome = "CANTO SUPERIOR"

        dx_alvo_m = (alvo_canto[0] - portador[0]) * self.scale_x
        dy_alvo_m = (alvo_canto[1] - portador[1]) * self.scale_y
        dist_alvo_m = math.hypot(dx_alvo_m, dy_alvo_m)
        vetor_mira = (dx_alvo_m / (dist_alvo_m + 1e-5), dy_alvo_m / (dist_alvo_m + 1e-5))

        # 4. Ângulo de Visão da Baliza theta (radianos)
        ang1 = math.atan2((y_trave_sup - portador[1]) * self.scale_y, (gol_alvo_x - portador[0]) * self.scale_x)
        ang2 = math.atan2((y_trave_inf - portador[1]) * self.scale_y, (gol_alvo_x - portador[0]) * self.scale_x)
        theta = abs(ang2 - ang1)
        if theta > math.pi:
            theta = 2.0 * math.pi - theta

        # 5. Avaliação do Cone de Bloqueio (Zagueiros na linha de chute)
        n_bloqueadores = 0
        bloqueio_critico = False
        ang_tiro = math.atan2(dy_alvo_m, dx_alvo_m)

        for adv in adversarios:
            if goleiro and adv == goleiro:
                continue
            dx_adv_m = (adv[0] - portador[0]) * self.scale_x
            dy_adv_m = (adv[1] - portador[1]) * self.scale_y
            proj_m = (dx_adv_m * dx_alvo_m + dy_adv_m * dy_alvo_m) / (dist_alvo_m + 1e-5)
            if 0.6 < proj_m < dist_alvo_m:
                perp_m = abs(dx_adv_m * math.sin(ang_tiro) - dy_adv_m * math.cos(ang_tiro))
                if perp_m < 1.85:
                    n_bloqueadores += 1
                    if proj_m < 3.0:
                        bloqueio_critico = True

        # 6. Espaço Livre Imediato do Atleta (para armar o chute Fenomenal/Stunner)
        espaco_livre_frente_m = min([self.dist_metros(portador, a) for a in adversarios], default=99.0)

        # 7. Cálculo Logístico de Expected Goals (xG)
        delta_gk = max(0.0, min(5.0, dist_gk_linha_m - 2.0))
        z = 2.45 * theta - 0.082 * dist_gol_m - 0.40 * n_bloqueadores + 0.90 * (delta_gk / 3.0) - 0.25
        xg_percent = (1.0 / (1.0 + math.exp(-max(-6.0, min(6.0, z))))) * 100.0

        # 8. Árvore de Decisão de Tipo de Finalização & Duração de Barra Calibrada
        # Cavadinha (Chip Shot - LB+X) quando o goleiro sai da linha (>= 3.8m)
        if dist_gk_linha_m >= 3.8 and 6.0 <= dist_gol_m <= 22.0:
            tipo_chute = "CAVADA"
            tag_hud = "CAVADINHA (LB+X)"
            modificador = SCAN_Q
            duracao_ms = int(135.0 + ((dist_gol_m - 6.0) / 16.0) * 40.0)

        # Chute Colocado / Finesse (RB+X) quando em diagonal (offset >= 3.5m)
        elif abs(dy_gol_m) >= 3.5 and 12.0 <= dist_gol_m <= 24.0 and not bloqueio_critico:
            tipo_chute = "COLOCADO"
            tag_hud = "COLOCADO (RB+X)"
            modificador = SCAN_C
            duracao_ms = int(160.0 + ((dist_gol_m - 12.0) / 12.0) * 50.0)

        # Chute Fenomenal / Stunner (RT+X) com espaço livre de frente (>= 2.4m) e média distância (20m - 32m)
        elif espaco_livre_frente_m >= 2.4 and 20.0 <= dist_gol_m <= 32.0 and not bloqueio_critico:
            tipo_chute = "FENOMENAL"
            tag_hud = "FENOMENAL (RT+X)"
            modificador = SCAN_E
            duracao_ms = int(225.0 + ((dist_gol_m - 20.0) / 12.0) * 40.0)

        # Chute Rasteiro Seco / Forte no Canto (X) para finalizações rápidas, cara a cara ou sob pressão
        else:
            tipo_chute = "RASTEIRO"
            tag_hud = "RASTEIRO FORTE (X)"
            modificador = None
            duracao_ms = int(110.0 + (min(dist_gol_m, 20.0) / 20.0) * 35.0)

        # Trava de Segurança Máxima (Hard Cap de 265ms para nunca isolar por cima do travessão)
        duracao_ms = max(100, min(265, duracao_ms))

        return {
            "origem": portador,
            "alvo_canto": alvo_canto,
            "canto_nome": canto_nome,
            "vetor_direcao": vetor_mira,
            "dist_gol_m": dist_gol_m,
            "xg_percent": xg_percent,
            "tipo_chute": tipo_chute,
            "tag_hud": tag_hud,
            "modificador": modificador,
            "tempo_ms": duracao_ms,
            "gk_pos": goleiro,
            "dist_gk_linha_m": dist_gk_linha_m
        }


# ==============================================================================
# 4. HOOK DE TECLADO E TELEMETRIA
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
                with _lock_teclas:
                    _teclas_ativas.discard(t)
                    if t_num:
                        _teclas_ativas.discard(t_num)
                return False
    except Exception:
        pass

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
        self.historico = []
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
            tipo_p = dados_passe.get("tipo_passe", "RASTEIRO") if dados_passe else "RASTEIRO"
            _, _, vel_bola_mps = calcular_forca_balistica(dist, tipo_p)
            t_voo = max(0.30, min(2.4, dist / max(10.0, vel_bola_mps)))
            agora = time.perf_counter()
            self.passe_em_voo = {
                "id": self.total_disparados,
                "hora": time.strftime("%H:%M:%S"),
                "dist_m": dist,
                "tempo_ms": int(tempo_ms),
                "aereo": aereo,
                "tipo_passe": tipo_p,
                "origem": origem,
                "alvo_pos": alvo,
                "destino_futuro": df,
                "t_disparo": agora,
                "t_chegada": agora + t_voo,
                "t_limite": agora + t_voo + 1.25,
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

            if adversarios and t_decorrido >= 0.25 and not pv.get("aereo", False):
                dx_p = df[0] - origem[0]
                dy_p = df[1] - origem[1]
                dist_linha = math.hypot(dx_p, dy_p) + 1e-5
                for adv in adversarios:
                    dx_a = adv[0] - origem[0]
                    dy_a = adv[1] - origem[1]
                    proj = (dx_a * dx_p + dy_a * dy_p) / dist_linha
                    if 8.0 < proj < (dist_linha - 10.0):
                        perp = abs(dx_a * (dy_p / dist_linha) - dy_a * (dx_p / dist_linha))
                        if perp < 7.0:
                            if pos_bola and math.hypot(pos_bola[0] - adv[0], pos_bola[1] - adv[1]) < 10.0:
                                pv["status"] = "❌ BLOQUEADO (Zagueiro)"
                                self.erros += 1
                                self.historico.insert(0, dict(pv))
                                if len(self.historico) > 50:
                                    self.historico.pop()
                                self.passe_em_voo = None
                                return "ERRO"

            if cursor_usuario is not None and t_decorrido >= 0.20:
                dist_cursor_df = math.hypot(cursor_usuario[0] - df[0], cursor_usuario[1] - df[1])
                dist_cursor_alvo = math.hypot(cursor_usuario[0] - alvo_p[0], cursor_usuario[1] - alvo_p[1])
                dist_cursor_origem = math.hypot(cursor_usuario[0] - origem[0], cursor_usuario[1] - origem[1])

                if (dist_cursor_df < 24.0 or dist_cursor_alvo < 18.0) and dist_cursor_origem > 14.0:
                    pv["status"] = "✅ CONCLUÍDO (No Alvo)"
                    self.acertos += 1
                    self.historico.insert(0, dict(pv))
                    if len(self.historico) > 50:
                        self.historico.pop()
                    self.passe_em_voo = None
                    return "ACERTO"

            if pos_bola is not None and t_decorrido >= 0.35:
                dist_bola_df = math.hypot(pos_bola[0] - df[0], pos_bola[1] - df[1])
                dist_bola_alvo = math.hypot(pos_bola[0] - alvo_p[0], pos_bola[1] - alvo_p[1])
                dist_bola_origem = math.hypot(pos_bola[0] - origem[0], pos_bola[1] - origem[1])

                if (dist_bola_df < 15.0 or dist_bola_alvo < 13.0) and dist_bola_origem > 15.0:
                    pv["status"] = "✅ CONCLUÍDO (Bola no Alvo)"
                    self.acertos += 1
                    self.historico.insert(0, dict(pv))
                    if len(self.historico) > 50:
                        self.historico.pop()
                    self.passe_em_voo = None
                    return "ACERTO"

            if pos_bola is not None and t_decorrido >= 0.30:
                dist_bola_origem = math.hypot(pos_bola[0] - origem[0], pos_bola[1] - origem[1])
                if dist_bola_origem > 15.0:
                    for adv in adversarios:
                        if math.hypot(pos_bola[0] - adv[0], pos_bola[1] - adv[1]) < 8.0:
                            pv["status"] = "❌ INTERCEPTADO"
                            self.erros += 1
                            self.historico.insert(0, dict(pv))
                            if len(self.historico) > 50:
                                self.historico.pop()
                            self.passe_em_voo = None
                            return "ERRO"

            if agora >= pv["t_limite"]:
                interceptado = any(math.hypot(adv[0] - df[0], adv[1] - df[1]) < 18.0 for adv in adversarios)
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
        self.ultima_validade_ts = 0.0
        self.dados_cruzamento = None
        self.dados_chute = None
        self.pos_bola = None
        self.cursor_usuario = None
        self.sou_time_verde = True
        self.atacando_direita = True
        self.radar_ativo = False
        self.rp2040_conectado = False
        self.analog_dir = (0.0, 0.0)
        self.telemetria = TelemetriaPasses()

    def carregar_config(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    salvo = json.load(f)
                    if "radar_roi" in salvo:
                        cfg["radar_roi"].update(salvo["radar_roi"])
                    if "hotkeys" in salvo:
                        cfg["hotkeys"].update(salvo["hotkeys"])
                    if "modo_cor_time" in salvo:
                        cfg["modo_cor_time"] = salvo["modo_cor_time"]
                    if "usar_mira_automatica_360" in salvo:
                        cfg["usar_mira_automatica_360"] = salvo["usar_mira_automatica_360"]
                    if "modo_desafogo_pressao" in salvo:
                        cfg["modo_desafogo_pressao"] = salvo["modo_desafogo_pressao"]
                    if "usar_finalizacao_inteligente" in salvo:
                        cfg["usar_finalizacao_inteligente"] = salvo["usar_finalizacao_inteligente"]
            except Exception:
                pass
        return cfg

    def salvar_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[AVISO] Falha ao salvar {CONFIG_PATH}: {e}")


# ==============================================================================
# 5. PONTE DE HARDWARE RP2040 & EXECUTOR ASSÍNCRONO BIT-A-BIT
# ==============================================================================
def encontrar_porta_rp2040():
    portas = list(serial.tools.list_ports.comports())
    for p in portas:
        if "239A" in p.hwid and ("MI_02" in p.hwid or "x.2" in p.hwid):
            return p.device
    for p in portas:
        if "239A" in p.hwid:
            return p.device
    return "COM9"

def enviar_relatorio_rp2040(ser, buttons, lx, ly, rx, ry):
    if ser and ser.is_open:
        try:
            clamp = lambda v: max(-127, min(127, int(round(v * 127))))
            pacote = struct.pack("<Hbbbb", buttons, clamp(lx), clamp(ly), clamp(rx), clamp(ry))
            ser.write(pacote)
        except Exception:
            pass


class ExecutorAcaoAssincrono:
    """
    Máquina de estados não-bloqueante que sincroniza os eventos de DirectX e os
    bits de botão do RP2040 em tempo real (permitindo toques duplos D+D perfeitos).
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.ativo = False
        self.eventos_dx = []
        self.fim_acao_ts = 0.0
        self.override_lx = None
        self.override_ly = None
        self.override_btns = 0
        self.teclas_direcao_ativas = []

    def agendar_sequencia(self, etapas_dx, duracao_total_s, vetor_dir=None, usar_mira_teclado=False):
        agora = time.perf_counter()
        with self.lock:
            directx_liberar_tudo()
            self.eventos_dx.clear()

            self.ativo = True
            self.fim_acao_ts = agora + duracao_total_s
            self.override_btns = 0

            if vetor_dir is not None:
                self.override_lx, self.override_ly = vetor_dir[0], vetor_dir[1]
                if usar_mira_teclado:
                    self.teclas_direcao_ativas = obter_scancodes_direcao(vetor_dir[0], vetor_dir[1])
                    for sc_dir in self.teclas_direcao_ativas:
                        directx_press(sc_dir)
            else:
                self.override_lx, self.override_ly = None, None
                self.teclas_direcao_ativas = []

            for delay_s, fn, sc in etapas_dx:
                self.eventos_dx.append((agora + delay_s, fn, sc))
            self.eventos_dx.sort(key=lambda x: x[0])

    def atualizar(self):
        """Chamado a cada ciclo de ~1ms da thread de controle."""
        agora = time.perf_counter()
        with self.lock:
            if not self.ativo:
                return False, 0, None, None

            while self.eventos_dx and agora >= self.eventos_dx[0][0]:
                _, fn, sc = self.eventos_dx.pop(0)
                fn(sc)
                # Atualiza os bits de botão do RP2040 sincronizados com cada press/release
                bit_rp = SCANCODE_TO_RP2040_BTN.get(sc, 0)
                if fn == directx_press:
                    self.override_btns |= bit_rp
                elif fn == directx_release:
                    self.override_btns &= ~bit_rp

            if agora >= self.fim_acao_ts and not self.eventos_dx:
                directx_liberar_tudo()
                self.ativo = False
                self.override_lx = None
                self.override_ly = None
                self.override_btns = 0
                self.teclas_direcao_ativas.clear()
                return False, 0, None, None

            return True, self.override_btns, self.override_lx, self.override_ly


# ==============================================================================
# 6. THREAD DE CONTROLE E DISPARO DE AÇÕES (DIRECTX + RP2040 A ~1000Hz)
# ==============================================================================
def thread_controle_execucao(estado: EstadoSistema):
    ser = None
    try:
        p = encontrar_porta_rp2040()
        ser = serial.Serial(p, 115200, timeout=0)
        estado.rp2040_conectado = True
        print(f"[RP2040] ✅ Conectado na porta {p} (Bridge de Baixa Latência ativa)")
    except Exception:
        print("[RP2040] ℹ️ Placa não encontrada — operando com injeção nativa DirectX para o eFootball!")

    pygame.init()
    pygame.joystick.init()
    keyboard.on_press(_on_key_down, suppress=False)
    keyboard.on_release(_on_key_up, suppress=False)

    vader = None
    executor = ExecutorAcaoAssincrono()
    ultimo_disparo = 0.0
    cooldown = 0.28

    ant_lanc = False
    ant_cruz = False
    ant_chute_key = False
    ant_btn_x = False

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

            lx = vader.get_axis(0) if vader else 0.0
            ly = vader.get_axis(1) if vader else 0.0
            rx = vader.get_axis(2) if (vader and vader.get_numaxes() > 2) else 0.0
            ry = vader.get_axis(3) if (vader and vader.get_numaxes() > 3) else 0.0
            with estado.lock:
                estado.analog_dir = (lx, ly)

            agora = time.perf_counter()
            hk = estado.config["hotkeys"]
            usar_mira_360 = estado.config.get("usar_mira_automatica_360", True)
            usar_mira_teclado = usar_mira_360 and (not estado.rp2040_conectado) and (vader is None)

            # --- 1. LANÇAMENTO TELEGUIADO IA ---
            tecla_lanc = hk.get("lancamento_ia", "5")
            press_lanc = tecla_foi_pressionada(tecla_lanc)

            if press_lanc and not ant_lanc and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                consumir_tecla(tecla_lanc)

                with estado.lock:
                    if estado.dados_passe:
                        dp = copy.deepcopy(estado.dados_passe)
                    elif estado.ultimo_passe_valido and (agora - estado.ultima_validade_ts <= 0.50):
                        dp = copy.deepcopy(estado.ultimo_passe_valido)
                    else:
                        dp = None

                if dp:
                    tempo_sec = max(0.085, min(0.350, dp["tempo_ms"] / 1000.0))
                    aereo = dp.get("aereo", False)
                    tipo_p = dp.get("tipo_passe", "RASTEIRO")
                    dist_m = dp.get("dist_metros", 20.0)
                    vetor_dir = dp.get("vetor_direcao") if usar_mira_360 else None
                    estado.telemetria.registrar_disparo(dp, tempo_sec * 1000.0, aereo)

                    if tipo_p == "FENOMENAL_CURVA":
                        print(f"\n[DISPARO] 🌀 Lançamento FENOMENAL (RT+W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")
                        etapas = [
                            (0.000, directx_press, SCAN_E),
                            (0.022, directx_press, SCAN_W),
                            (0.022 + tempo_sec, directx_release, SCAN_W),
                            (0.030 + tempo_sec, directx_release, SCAN_E)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.030, vetor_dir, usar_mira_teclado)
                    elif tipo_p == "CAVADO_ARCO" or aereo:
                        print(f"\n[DISPARO] 🎯 Lançamento CAVADO EM ARCO (LB+W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")
                        etapas = [
                            (0.000, directx_press, SCAN_Q),
                            (0.020, directx_press, SCAN_W),
                            (0.020 + tempo_sec, directx_release, SCAN_W),
                            (0.028 + tempo_sec, directx_release, SCAN_Q)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, usar_mira_teclado)
                    else:
                        print(f"\n[DISPARO] 🎯 Lançamento RASTEIRO IA (W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")
                        etapas = [
                            (0.000, directx_press, SCAN_W),
                            (tempo_sec, directx_release, SCAN_W)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, usar_mira_teclado)
                else:
                    dir_frente = 1.0 if estado.atacando_direita else -1.0
                    alvo_aprox = (130 + int(38 * dir_frente), 65)
                    estado.telemetria.registrar_disparo({
                        "dist_metros": 18.0,
                        "destino_futuro": alvo_aprox,
                        "origem": (130, 65),
                        "tipo_passe": "RASTEIRO"
                    }, 165.0, False)
                    print("\n[DISPARO] 🎯 Lançamento Padrão (Sem alvo livre no radar) -> W (165ms)")
                    etapas = [
                        (0.000, directx_press, SCAN_W),
                        (0.165, directx_release, SCAN_W)
                    ]
                    executor.agendar_sequencia(etapas, 0.165, None, False)

            ant_lanc = press_lanc

            # --- 2. CRUZAMENTO INTELIGENTE IA ---
            tecla_cruz = hk.get("cruzamento_ia", "6")
            press_cruz = tecla_foi_pressionada(tecla_cruz)

            if press_cruz and not ant_cruz and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                consumir_tecla(tecla_cruz)

                with estado.lock:
                    dc = copy.deepcopy(estado.dados_cruzamento) if estado.dados_cruzamento else None

                if dc:
                    tipo = dc.get("tipo", "CABEÇA")
                    setor = dc.get("setor", "ÁREA")
                    tag = dc.get("tag_hud", tipo)
                    dist_m = dc.get("dist_metros", 25.0)
                    tempo_sec = max(0.095, min(0.350, dc["tempo_ms"] / 1000.0))
                    vetor_dir = dc.get("vetor_direcao") if usar_mira_360 else None
                    print(f"\n[DISPARO] ⚡ Cruzamento IA: {tag} ({setor}) | Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")

                    if tipo == "RASTEIRO":
                        t2 = max(0.065, tempo_sec * 0.70)
                        etapas = [
                            (0.000, directx_press, SCAN_D),
                            (0.040, directx_release, SCAN_D),
                            (0.075, directx_press, SCAN_D),
                            (0.075 + t2, directx_release, SCAN_D)
                        ]
                        executor.agendar_sequencia(etapas, 0.075 + t2, vetor_dir, usar_mira_teclado)
                    elif tipo in ("BALAO_ALTO", "ANTECIPADO"):
                        etapas = [
                            (0.000, directx_press, SCAN_Q),
                            (0.020, directx_press, SCAN_D),
                            (0.020 + tempo_sec, directx_release, SCAN_D),
                            (0.028 + tempo_sec, directx_release, SCAN_Q)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, usar_mira_teclado)
                    elif tipo == "FENOMENAL":
                        etapas = [
                            (0.000, directx_press, SCAN_E),
                            (0.025, directx_press, SCAN_D),
                            (0.025 + tempo_sec, directx_release, SCAN_D),
                            (0.032 + tempo_sec, directx_release, SCAN_E)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.032, vetor_dir, usar_mira_teclado)
                    else:
                        etapas = [
                            (0.000, directx_press, SCAN_D),
                            (tempo_sec, directx_release, SCAN_D)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, usar_mira_teclado)
                else:
                    print("\n[DISPARO] ⚡ Cruzamento Manual (Sem alvo na área) -> D (170ms)")
                    etapas = [
                        (0.000, directx_press, SCAN_D),
                        (0.170, directx_release, SCAN_D)
                    ]
                    executor.agendar_sequencia(etapas, 0.170, None, False)

            ant_cruz = press_cruz

            # --- 3. FINALIZAÇÃO INTELIGENTE IA (xG & MIRA 360°) ---
            usar_finalizacao = estado.config.get("usar_finalizacao_inteligente", True)
            tecla_chute = hk.get("chute_ia", "4")
            press_chute_key = tecla_foi_pressionada(tecla_chute)
            press_btn_x = vader.get_button(BTN_X) if vader else False

            with estado.lock:
                tem_dados_chute = (estado.dados_chute is not None)

            trigger_chute_key = press_chute_key and not ant_chute_key
            trigger_chute_gp = press_btn_x and not ant_btn_x and usar_finalizacao and tem_dados_chute

            if (trigger_chute_key or trigger_chute_gp) and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                if trigger_chute_key:
                    consumir_tecla(tecla_chute)

                with estado.lock:
                    dch = copy.deepcopy(estado.dados_chute) if estado.dados_chute else None

                if dch:
                    tempo_sec = max(0.090, min(0.265, dch["tempo_ms"] / 1000.0))
                    vetor_dir = dch.get("vetor_direcao") if usar_mira_360 else None
                    mod = dch.get("modificador")
                    tag = dch.get("tag_hud", "CHUTE")
                    xg = dch.get("xg_percent", 0.0)
                    dist_m = dch.get("dist_gol_m", 0.0)
                    canto = dch.get("canto_nome", "GOL")
                    print(f"\n[CHUTE IA] ⚽ {tag} ({canto}) | xG={xg:.0f}% | Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms")

                    if mod == SCAN_Q:
                        # Cavadinha (LB + X)
                        etapas = [
                            (0.000, directx_press, SCAN_Q),
                            (0.020, directx_press, SCAN_A),
                            (0.020 + tempo_sec, directx_release, SCAN_A),
                            (0.028 + tempo_sec, directx_release, SCAN_Q)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, usar_mira_teclado)
                    elif mod == SCAN_C:
                        # Colocado / Finesse (RB + X)
                        etapas = [
                            (0.000, directx_press, SCAN_C),
                            (0.020, directx_press, SCAN_A),
                            (0.020 + tempo_sec, directx_release, SCAN_A),
                            (0.028 + tempo_sec, directx_release, SCAN_C)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, usar_mira_teclado)
                    elif mod == SCAN_E:
                        # Fenomenal / Stunner (RT + X)
                        etapas = [
                            (0.000, directx_press, SCAN_E),
                            (0.025, directx_press, SCAN_A),
                            (0.025 + tempo_sec, directx_release, SCAN_A),
                            (0.032 + tempo_sec, directx_release, SCAN_E)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.032, vetor_dir, usar_mira_teclado)
                    else:
                        # Rasteiro Seco / Forte no Canto (X)
                        etapas = [
                            (0.000, directx_press, SCAN_A),
                            (tempo_sec, directx_release, SCAN_A)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, usar_mira_teclado)
                else:
                    print("\n[CHUTE] ⚽ Chute Rápido (Sem mira xG ativa) -> A (135ms)")
                    etapas = [
                        (0.000, directx_press, SCAN_A),
                        (0.135, directx_release, SCAN_A)
                    ]
                    executor.agendar_sequencia(etapas, 0.135, None, False)

            ant_chute_key = press_chute_key
            ant_btn_x = press_btn_x

            # --- 4. INVERTER TIME MANUALMENTE (F10) ---
            tecla_inv = hk.get("inverter_cor_time", "f10")
            if tecla_foi_pressionada(tecla_inv):
                consumir_tecla(tecla_inv)
                with estado.lock:
                    estado.sou_time_verde = not estado.sou_time_verde
                    novo_modo = "VERDE" if estado.sou_time_verde else "VERMELHO"
                    estado.config["modo_cor_time"] = novo_modo
                    estado.salvar_config()
                    print(f"\n[TIME] Invertido manualmente e salvo: {novo_modo}")

            # --- 5. ATUALIZA MÁQUINA DE ESTADOS E PASSTHROUGH RP2040 ---
            em_acao, ov_btns, ov_lx, ov_ly = executor.atualizar()

            if ser and ser.is_open:
                buttons = 0
                if vader:
                    for b in range(min(16, vader.get_numbuttons())):
                        if vader.get_button(b):
                            buttons |= (1 << b)
                if em_acao:
                    mascara_ia = (1 << BTN_X) | (1 << BTN_Y) | (1 << BTN_B) | (1 << BTN_LB) | (1 << BTN_RB) | (1 << BTN_RT_DIGITAL)
                    buttons = (buttons & ~mascara_ia) | ov_btns
                    out_lx = ov_lx if ov_lx is not None else lx
                    out_ly = ov_ly if ov_ly is not None else ly
                else:
                    out_lx, out_ly = lx, ly
                enviar_relatorio_rp2040(ser, buttons, out_lx, out_ly, rx, ry)

            time.sleep(0.001)

        except Exception:
            time.sleep(0.005)

    directx_liberar_tudo()
    if ser and ser.is_open:
        ser.close()


# ==============================================================================
# 7. THREAD DE VISÃO COMPUTACIONAL A 60 FPS (MSS + OPENCV)
# ==============================================================================
def thread_visao_radar(estado: EstadoSistema):
    sct = mss.mss()
    roi = estado.config.get("radar_roi", RADAR_ROI_PADRAO)
    processador = RadarPassesEFootball(roi)
    print(f"[RADAR] Visão Computacional iniciada na ROI: {roi} (Escala: {processador.scale_x:.2f}m/px X, {processador.scale_y:.2f}m/px Y)")
    votos_verde = 0
    votos_verm = 0
    cursor_ant = None
    bola_ant = None

    while estado.rodando:
        try:
            t_inicio = time.perf_counter()
            screenshot = np.array(sct.grab(roi))
            img_bgr = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            verdes, vermelhos, cursor_usuario, pos_bola = processador.processar_frame(
                img_bgr, cursor_anterior=cursor_ant, bola_anterior=bola_ant
            )
            if cursor_usuario is not None:
                cursor_ant = cursor_usuario
            if pos_bola is not None:
                bola_ant = pos_bola

            modo = estado.config.get("modo_cor_time", "AUTO")
            if modo == "VERDE":
                estado.sou_time_verde = True
            elif modo == "VERMELHO":
                estado.sou_time_verde = False
            else:
                if cursor_usuario is not None:
                    dist_verde = min([math.hypot(cursor_usuario[0] - v[0], cursor_usuario[1] - v[1]) for v in verdes], default=999)
                    dist_verm = min([math.hypot(cursor_usuario[0] - r[0], cursor_usuario[1] - r[1]) for r in vermelhos], default=999)
                    if dist_verde < dist_verm and dist_verde < 14:
                        votos_verde += 1
                        votos_verm = 0
                        if votos_verde >= 10:
                            estado.sou_time_verde = True
                    elif dist_verm < dist_verde and dist_verm < 14:
                        votos_verm += 1
                        votos_verde = 0
                        if votos_verm >= 10:
                            estado.sou_time_verde = False

            meus_jogadores = list(verdes if estado.sou_time_verde else vermelhos)
            adversarios = list(vermelhos if estado.sou_time_verde else verdes)

            atacando_direita = estado.atacando_direita
            if len(meus_jogadores) >= 5 and len(adversarios) >= 5:
                media_meu_x = np.mean([p[0] for p in meus_jogadores])
                media_adv_x = np.mean([p[0] for p in adversarios])
                if abs(media_meu_x - media_adv_x) > 8.0:
                    atacando_direita = (media_meu_x < media_adv_x)
            estado.atacando_direita = atacando_direita

            linha_x = processador.calcular_linha_impedimento_ifab(adversarios, atacando_direita=atacando_direita)

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
                if pos_bola is not None and cursor_usuario is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - cursor_usuario[0], p[1] - cursor_usuario[1]) * 0.7 + math.hypot(p[0] - pos_bola[0], p[1] - pos_bola[1]) * 0.3)
                elif cursor_usuario is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - cursor_usuario[0], p[1] - cursor_usuario[1]))
                elif pos_bola is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - pos_bola[0], p[1] - pos_bola[1]))

                portador = meus_jogadores[0]
                companheiros = meus_jogadores[1:]

                with estado.lock:
                    analog_dir = estado.analog_dir
                    modo_desafogo = estado.config.get("modo_desafogo_pressao", True)

                livres, bloqueados = processador.analisar_linhas_de_passe(
                    portador, companheiros, adversarios,
                    atacando_direita=atacando_direita, linha_zaga=linha_x,
                    analog_dir=analog_dir, modo_desafogo=modo_desafogo
                )
                todos_candidatos = [p for p in (livres + bloqueados) if not p.get("impedido", False)]
                todos_candidatos.sort(key=lambda x: x["score"], reverse=True)

                if todos_candidatos:
                    melhor_passe = todos_candidatos[0]
                    df = melhor_passe["destino_futuro"]
                    pts_arco = melhor_passe.get("pontos_arco", [])
                    tipo_p = melhor_passe.get("tipo_passe", "RASTEIRO")
                    if melhor_passe.get("sob_pressao"):
                        cv2.putText(overlay, "! DESAFOGO !", (max(2, portador[0] - 22), max(10, portador[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 140, 255), 1)
                    if pts_arco and len(pts_arco) >= 2:
                        pts_arr = np.array(pts_arco, dtype=np.int32).reshape((-1, 1, 2))
                        cor_arco = (0, 180, 255)
                        cv2.polylines(overlay, [pts_arr], isClosed=False, color=cor_arco, thickness=2, lineType=cv2.LINE_AA)
                        cv2.circle(overlay, df, 7, cor_arco, 2)
                        cv2.putText(overlay, "CAVADO LB+W", (max(2, df[0] - 22), max(12, df[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, cor_arco, 1)
                    else:
                        cor_linha = (0, 240, 255) if melhor_passe.get("rompimento") else ((255, 0, 200) if tipo_p == "FENOMENAL_CURVA" else (0, 255, 180))
                        cv2.line(overlay, portador, df, cor_linha, 2)
                        cv2.circle(overlay, df, 7, cor_linha, 2)

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

                melhor_chute = processador.analisar_finalizacao_xg(
                    portador, companheiros, adversarios, atacando_direita=atacando_direita
                )
                if melhor_chute:
                    alvo_k = melhor_chute["alvo_canto"]
                    tag_k = melhor_chute["tag_hud"]
                    xg_val = melhor_chute["xg_percent"]
                    cor_k = (0, 255, 100) if xg_val >= 50 else ((0, 220, 255) if xg_val >= 30 else (0, 100, 255))
                    cv2.line(overlay, portador, alvo_k, cor_k, 2, cv2.LINE_AA)
                    cv2.circle(overlay, alvo_k, 4, cor_k, -1)
                    txt_chute = f"xG:{xg_val:.0f}% {tag_k}"
                    cv2.putText(overlay, txt_chute, (max(2, portador[0] - 25), max(12, portador[1] + 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.32, cor_k, 1)

            if cursor_usuario is not None:
                cv2.circle(overlay, cursor_usuario, 7, (0, 255, 255), 2)
            if pos_bola is not None:
                cv2.circle(overlay, pos_bola, 3, (255, 255, 255), -1)

            agora_ts = time.perf_counter()
            with estado.lock:
                estado.radar_ativo = True
                estado.dados_passe = melhor_passe
                if melhor_passe:
                    estado.ultimo_passe_valido = melhor_passe
                    estado.ultima_validade_ts = agora_ts
                estado.dados_cruzamento = melhor_cruz
                estado.dados_chute = melhor_chute
                estado.cursor_usuario = cursor_usuario
                estado.pos_bola = pos_bola

            estado.telemetria.avaliar_frame(cursor_usuario, meus_jogadores, adversarios, pos_bola=pos_bola)

            hud_zoom = cv2.resize(overlay, (largura_r * 3, altura_r * 3), interpolation=cv2.INTER_NEAREST)
            time_txt = "MANDANTE (VERDE)" if estado.sou_time_verde else "VISITANTE (VERMELHO)"
            dir_txt = "ATQ -> DIR" if atacando_direita else "ATQ <- ESQ"
            cv2.putText(hud_zoom, f"{time_txt} | {dir_txt}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            st_hud = estado.telemetria.obter_estatisticas()
            if st_hud["total"] > 0:
                txt_hud = f"ASSERTIVIDADE: {st_hud['taxa']:.0f}% ({st_hud['acertos']}/{st_hud['total']})"
                cor_hud = (0, 255, 100) if st_hud['taxa'] >= 70 else ((0, 220, 255) if st_hud['taxa'] >= 50 else (0, 80, 255))
                cv2.putText(hud_zoom, txt_hud, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor_hud, 2)

            if melhor_chute:
                txt_hud_chute = f"FINALIZACAO: xG {melhor_chute['xg_percent']:.0f}% | {melhor_chute['tag_hud']} ({melhor_chute['canto_nome']})"
                cor_hud_chute = (0, 255, 100) if melhor_chute['xg_percent'] >= 50 else ((0, 220, 255) if melhor_chute['xg_percent'] >= 30 else (0, 120, 255))
                cv2.putText(hud_zoom, txt_hud_chute, (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.50, cor_hud_chute, 2)

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
        self.root.title("⚽ eFootball Master AI & Controller Hub (V2.2 xG)")
        self.root.geometry("600x575")
        self.root.configure(bg="#0c0c14")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.encerrar)

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

        topo = tk.Frame(self.root, bg="#121220", pady=8)
        topo.pack(fill="x")
        tk.Label(
            topo, text="⚡ EFOOTBALL MASTER AI & CONTROLLER HUB V2.1",
            font=("Segoe UI", 12, "bold"), fg="#00ffcc", bg="#121220"
        ).pack()
        tk.Label(
            topo, text="Mira Vetorial 360° + Máquina Bit-a-Bit 1000Hz + Escala IFAB 105x68m",
            font=("Segoe UI", 8), fg="#8888aa", bg="#121220"
        ).pack()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=8)

        self.tab_visao = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_visao, text="  👁️ Visão Computacional  ")

        self.tab_stats = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_stats, text="  📊 Estatísticas do Lançamento  ")

        self._construir_aba_visao()
        self._construir_aba_estatisticas()

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
        frame_time = tk.LabelFrame(
            self.tab_visao, text=" Detecção de Equipe & Assistência de Mira ",
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

        self.var_mira360 = tk.BooleanVar(value=self.estado.config.get("usar_mira_automatica_360", True))
        cb_mira = tk.Checkbutton(
            frame_time, text="Ativar Mira Direcional Automática 360° (RP2040 Analógico / Setas DirectX)",
            variable=self.var_mira360, command=self.mudar_mira360,
            bg="#0c0c14", fg="#00ff88", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 9, "bold")
        )
        cb_mira.pack(anchor="w", pady=2)

        self.var_desafogo = tk.BooleanVar(value=self.estado.config.get("modo_desafogo_pressao", True))
        cb_desafogo = tk.Checkbutton(
            frame_time, text="Ativar Modo Desafogo Rápido (Quick-Release sob pressão < 1.9m)",
            variable=self.var_desafogo, command=self.mudar_desafogo,
            bg="#0c0c14", fg="#00ffcc", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 9)
        )
        cb_desafogo.pack(anchor="w", pady=2)

        self.var_chute = tk.BooleanVar(value=self.estado.config.get("usar_finalizacao_inteligente", True))
        cb_chute = tk.Checkbutton(
            frame_time, text="Ativar Finalização Inteligente xG (Gatilho X no Ataque / Tecla 4)",
            variable=self.var_chute, command=self.mudar_finalizacao,
            bg="#0c0c14", fg="#ffcc00", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 9, "bold")
        )
        cb_chute.pack(anchor="w", pady=2)

        frame_keys = tk.LabelFrame(
            self.tab_visao, text=" Atalhos das Ações Táticas da IA (Flydigi Space Station) ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=6
        )
        frame_keys.pack(fill="x", padx=10, pady=6)

        self.botoes_teclas = {}
        acoes = [
            ("chute_ia", "⚽ Finalização Inteligente xG (X)", "A / LB+A / RB+A / RT+A"),
            ("lancamento_ia", "🎯 Lançamento Teleguiado IA (Y)", "W / LB+W / RT+W"),
            ("cruzamento_ia", "⚡ Cruzamento Inteligente IA (B)", "D / D+D / LB+D"),
        ]

        for chave, nome, comando_jogo in acoes:
            linha = tk.Frame(frame_keys, bg="#0c0c14")
            linha.pack(fill="x", pady=2)
            tk.Label(linha, text=nome, font=("Segoe UI", 9), fg="#ffffff", bg="#0c0c14", width=30, anchor="w").pack(side="left")
            tk.Label(linha, text=f"-> {comando_jogo}", font=("Segoe UI", 8), fg="#ffaa00", bg="#0c0c14", width=16, anchor="w").pack(side="left")

            tecla_atual = self.estado.config["hotkeys"].get(chave, "?").upper()
            btn = tk.Button(
                linha, text=f"[ {tecla_atual} ]", font=("Consolas", 9, "bold"),
                bg="#1a1a2e", fg="#00ffcc", activebackground="#00ffcc", activeforeground="#000",
                width=8, command=lambda c=chave: self.capturar_tecla(c)
            )
            btn.pack(side="right")
            self.botoes_teclas[chave] = btn

        frame_info = tk.LabelFrame(
            self.tab_visao, text=" Motor Tático V2.1 ",
            bg="#0c0c14", fg="#8888aa", font=("Segoe UI", 8, "bold"), padx=10, pady=4
        )
        frame_info.pack(fill="x", padx=10, pady=4)
        tk.Label(
            frame_info,
            text="• Bhaskara de 2 estágios com recálculo por modalidade + Desaglutinação Distance Transform.\n• Máquina de estados bit-a-bit: suporta duplo toque rápido (D+D) tanto no DirectX quanto no RP2040.",
            bg="#0c0c14", fg="#777799", font=("Segoe UI", 8), justify="left"
        ).pack(anchor="w")

    def _construir_aba_estatisticas(self):
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

        self.lbl_status_voo = tk.Label(
            self.tab_stats, text="🎯 Pronto. Dispare o lançamento no controle para registrar...",
            bg="#10101c", fg="#aaaacc", font=("Segoe UI", 8, "italic"), pady=3
        )
        self.lbl_status_voo.pack(fill="x", padx=14, pady=3)

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
        self.tree.column("tipo", width=95, anchor="center")
        self.tree.column("status", width=130, anchor="center")

        scroll = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.tag_configure("concluido", foreground="#00ff88")
        self.tree.tag_configure("interceptado", foreground="#ff5555")
        self.tree.tag_configure("fora", foreground="#ffaa00")
        self.tree.tag_configure("em_voo", foreground="#00e5ff")

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
            text="* Acerto medido pela posse no recebedor pretendido.",
            bg="#0c0c14", fg="#666688", font=("Segoe UI", 7)
        ).pack(side="right")

    def mudar_modo(self):
        with self.estado.lock:
            self.estado.config["modo_cor_time"] = self.var_modo.get()
            self.estado.salvar_config()

    def mudar_mira360(self):
        with self.estado.lock:
            self.estado.config["usar_mira_automatica_360"] = bool(self.var_mira360.get())
            self.estado.salvar_config()

    def mudar_desafogo(self):
        with self.estado.lock:
            self.estado.config["modo_desafogo_pressao"] = bool(self.var_desafogo.get())
            self.estado.salvar_config()

    def mudar_finalizacao(self):
        with self.estado.lock:
            self.estado.config["usar_finalizacao_inteligente"] = bool(self.var_chute.get())
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
        rp_str = "RP2040 360° Ativo" if self.estado.rp2040_conectado else "DirectX Nativo"
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

        pv = self.estado.telemetria.passe_em_voo
        if pv and pv.get("status") == "EM_VOO":
            t_passado = time.perf_counter() - pv["t_disparo"]
            self.lbl_status_voo.configure(
                text=f"🚀 Lançamento em voo #{pv['id']} ({pv['dist_m']:.1f}m)... {t_passado:.1f}s",
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
                tp = p.get("tipo_passe", "RASTEIRO")
                if tp == "FENOMENAL_CURVA":
                    tipo_str = "Fenomenal (RT)"
                elif p.get("aereo") or tp == "CAVADO_ARCO":
                    tipo_str = "Aéreo (Cavado)"
                else:
                    tipo_str = "Rasteiro"
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
        directx_liberar_tudo()
        self.root.destroy()

    def iniciar(self):
        self.root.mainloop()


# ==============================================================================
# 9. PONTO DE ENTRADA PRINCIPAL (MAIN)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print("   ⚽ EFOOTBALL MASTER AI & CONTROLLER HUB - V2.2 (FINALIZAÇÃO xG)")
    print("   Mira 360° no Canto + Barra Balística + Assistência Tática")
    print("=" * 65)

    ctypes.windll.winmm.timeBeginPeriod(1)
    print("[TIMER] Resolução de timer Windows definida para 1ms (~1000Hz)")

    estado_mestre = EstadoSistema()

    t_ctrl = threading.Thread(target=thread_controle_execucao, args=(estado_mestre,), daemon=True)
    t_ctrl.start()

    t_cv = threading.Thread(target=thread_visao_radar, args=(estado_mestre,), daemon=True)
    t_cv.start()

    try:
        gui = InterfaceMestre(estado_mestre)
        gui.iniciar()
    finally:
        ctypes.windll.winmm.timeEndPeriod(1)
        print("[TIMER] Resolução de timer restaurada.")
