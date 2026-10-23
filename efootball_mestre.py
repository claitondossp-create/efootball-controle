"""
================================================================================
   EFOOTBALL MASTER AI & CONTROLLER HUB - ALL-IN-ONE (VERSÃO V2.3 AUTÔNOMA)
================================================================================
Projeto Unificado de Assistência Tática em Tempo Real para eFootball (PC).
Compatível com versões MICROSOFT STORE / XBOX APP e STEAM.

Novidades da V2.3 (Direcionamento 100% IA & Alta Assertividade):
- Pipeline de Mira com Pre-Aim Lead-In (18ms antes do passe) + Post-Release Hold (65ms após soltar a barra):
  Garante que a engine do eFootball leia 100% o vetor da IA e nunca desvie pela posição da mão no controle.
- Vetor Híbrido de Seleção de Recebedor (70% Ponto Futuro + 30% Posição Atual):
  Impede que a assistência do jogo (PA1/PA2/PA3) troque o alvo para o jogador errado em lançamentos longos.
- Injeção Dupla Sincronizada (RP2040 360° + Setas DirectX com Supressão de Conflito).
- Modo Opcional Auto-Trigger de Facão (Dispara sozinho quando um atacante rompe a linha de impedimento livre).
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

# ==============================================================================
# MOTOR HÁPTICO DE VIBRAÇÃO XINPUT (FLYDIGI VADER 4 PRO TRIGGER RUMBLE)
# ==============================================================================
try:
    _xinput_dll = (
        ctypes.windll.xinput1_4 if hasattr(ctypes.windll, "xinput1_4")
        else (ctypes.windll.xinput1_3 if hasattr(ctypes.windll, "xinput1_3")
        else ctypes.windll.xinput9_1_0)
    )
except Exception:
    _xinput_dll = None

class _XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", ctypes.c_ushort), ("wRightMotorSpeed", ctypes.c_ushort)]

_rumble_fim_ts = 0.0

def disparar_rumble_haptico(left_speed=0, right_speed=0, duracao_s=0.15):
    """Dispara pulso tátil de vibração no controle Flydigi Vader 4 Pro via XInput sem travar a thread."""
    global _rumble_fim_ts
    if _xinput_dll is None:
        return
    try:
        vib = _XINPUT_VIBRATION(int(left_speed), int(right_speed))
        _xinput_dll.XInputSetState(0, ctypes.byref(vib))
        _rumble_fim_ts = time.perf_counter() + duracao_s
    except Exception:
        pass

def atualizar_rumble_haptico():
    """Garante que a vibração háptica desligue com precisão de milissegundos."""
    global _rumble_fim_ts
    if _rumble_fim_ts > 0.0 and time.perf_counter() >= _rumble_fim_ts:
        _rumble_fim_ts = 0.0
        if _xinput_dll is not None:
            try:
                vib = _XINPUT_VIBRATION(0, 0)
                _xinput_dll.XInputSetState(0, ctypes.byref(vib))
            except Exception:
                pass

# ==============================================================================
# MAPEAMENTO OFICIAL CALIBRADO PELA TELA DO EFOOTBALL (CIRCUITPYTHON HID)
# ==============================================================================
# Índices exatos conforme configurado no Settings.exe do eFootball:
RP_BTN_X  = 0   # Botão 0 -> X (Chuto / Finalização)
RP_BTN_A  = 1   # Botão 1 -> A (Passe Curto)
RP_BTN_B  = 2   # Botão 2 -> B (Cruzamento / Passe Longo)
RP_BTN_Y  = 3   # Botão 3 -> Y (Lançamento em Profundidade)
RP_BTN_LB = 4   # Botão 4 -> LB (Troca de Cursor / Modificador Cavado)
RP_BTN_RB = 5   # Botão 5 -> RB (Chuto Colocado / Finesse)
RP_BTN_LT = 6   # Botão 6 -> LT (Controle Manual)
RP_BTN_RT = 7   # Botão 7 -> RT (Sprint / Passe e Chuto Fenomenal)
RP_BTN_BACK  = 8  # Botão 8 -> Back / Select
RP_BTN_START = 9  # Botão 9 -> Start / Menu
RP_BTN_LS = 10  # Botão 10 -> L3 (Clique Analógico Esquerdo)
RP_BTN_RS = 11  # Botão 11 -> R3 (Clique Analógico Direito)

# Índices de leitura do controle físico Flydigi Vader 4 Pro no Pygame (Padrão XInput):
VADER_BTN_A  = 0
VADER_BTN_B  = 1
VADER_BTN_X  = 2
VADER_BTN_Y  = 3
VADER_BTN_LB = 4
VADER_BTN_RB = 5
VADER_BTN_BACK  = 6
VADER_BTN_START = 7
VADER_BTN_LS = 8
VADER_BTN_RS = 9

# Tradução automática de Scancode -> Bit exato do CircuitPython HID (RP2040)
SCANCODE_TO_RP2040_BTN = {
    SCAN_A: (1 << RP_BTN_X),   # Chuto -> Botão 0
    SCAN_S: (1 << RP_BTN_A),   # Passe -> Botão 1
    SCAN_D: (1 << RP_BTN_B),   # Cruzamento -> Botão 2
    SCAN_W: (1 << RP_BTN_Y),   # Lançamento -> Botão 3
    SCAN_Q: (1 << RP_BTN_LB),  # Cavada (LB) -> Botão 4
    SCAN_C: (1 << RP_BTN_RB),  # Colocado (RB) -> Botão 5
    SCAN_Z: (1 << RP_BTN_LT),  # Manual (LT) -> Botão 6
    SCAN_E: (1 << RP_BTN_RT),  # Fenomenal (RT) -> Botão 7
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
        "inverter_cor_time": "f10",
        "toggle_overlay":    "f11"
    },
    "modo_cor_time": "AUTO",
    "usar_mira_automatica_360": True,
    "modo_desafogo_pressao": True,
    "usar_finalizacao_inteligente": True,
    "auto_disparo_facao": True,
    "perfil_assistencia": "PA1_PA2",
    "feedback_haptico": True,
    "overlay_ingame": True
}

CAMPO_LARGURA_M = 105.0
CAMPO_ALTURA_M = 68.0


# ==============================================================================
# 3. MOTOR DE VISÃO COMPUTACIONAL, CINEMÁTICA E BALÍSTICA (OPENCV)
# ==============================================================================
class KinematicPlayerTracker:
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


def calcular_forca_balistica(distancia_metros, tipo_passe="RASTEIRO", tipo_cruz=None):
    if tipo_cruz is not None:
        tipo_passe = tipo_cruz
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

        self.verde_min = np.array([35, 45, 45])
        self.verde_max = np.array([85, 255, 255])
        self.verm_min1 = np.array([0, 70, 70])
        self.verm_max1 = np.array([10, 255, 255])
        self.verm_min2 = np.array([165, 70, 70])
        self.verm_max2 = np.array([180, 255, 255])

    def dist_metros(self, p1, p2):
        return math.hypot((p1[0] - p2[0]) * self.scale_x, (p1[1] - p2[1]) * self.scale_y)

    def _resolver_intercepcao_bhaskara(self, portador, comp, vx_m, vy_m, v_bola_mps):
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
        t_star = max(0.08, min(1.05, t_star))

        pred_x = int(round(comp[0] + (vx_m * t_star) / self.scale_x))
        pred_y = int(round(comp[1] + (vy_m * t_star) / self.scale_y))
        return (
            max(3, min(largura_campo - 3, pred_x)),
            max(3, min(altura_campo - 3, pred_y))
        )

    def _extrair_pontos_de_mascara(self, mascara, area_min=4, area_single_max=52, area_merged_max=420):
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

        masc_verde = cv2.inRange(hsv, self.verde_min, self.verde_max)
        masc_verde = cv2.morphologyEx(masc_verde, cv2.MORPH_OPEN, kernel)
        verdes = self._extrair_pontos_de_mascara(masc_verde)

        masc_v1 = cv2.inRange(hsv, self.verm_min1, self.verm_max1)
        masc_v2 = cv2.inRange(hsv, self.verm_min2, self.verm_max2)
        masc_verm = cv2.bitwise_or(masc_v1, masc_v2)
        masc_verm = cv2.morphologyEx(masc_verm, cv2.MORPH_OPEN, kernel)
        vermelhos = self._extrair_pontos_de_mascara(masc_verm)

        todos_jogadores = verdes + vermelhos

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
        if not adversarios or len(adversarios) < 2:
            return None
        largura_campo = self.roi["width"]
        meio_campo = int(largura_campo / 2.0)

        # Filtra adversários válidos (descarta eventuais ruídos de borda absoluta do radar)
        adv_validos = [adv for adv in adversarios if 3 < adv[0] < (largura_campo - 3)]
        if len(adv_validos) < 2:
            adv_validos = adversarios

        xs_adv = sorted([adv[0] for adv in adv_validos], reverse=atacando_direita)

        # Pela Regra 11 da IFAB:
        # A linha de impedimento é SEMPRE no PENÚLTIMO adversário (xs_adv[1]).
        # O último adversário mais próximo do próprio gol (xs_adv[0]) é o goleiro!
        # Portanto, a linha de impedimento NUNCA deve ser no goleiro (xs_adv[0]), e sim no último zagueiro (xs_adv[1])!
        # Além disso, o jogador NÃO pode estar impedido no seu próprio campo de defesa.
        linha_penultimo = xs_adv[1]

        if atacando_direita:
            return int(max(meio_campo, linha_penultimo))
        else:
            return int(min(meio_campo, linha_penultimo))

    def analisar_linhas_de_passe(self, portador, companheiros, adversarios, atacando_direita=True, linha_zaga=None, analog_dir=(0.0, 0.0), modo_desafogo=True, perfil_assist="PA1_PA2"):
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

        an_x, an_y = analog_dir
        an_norm = math.hypot(an_x, an_y)
        if portador_speed_mps > 1.2:
            self.ultima_orientacao_portador = (vx_port_m / portador_speed_mps, vy_port_m / portador_speed_mps)
        elif an_norm > 0.18:
            self.ultima_orientacao_portador = (an_x / an_norm, an_y / an_norm)

        orient_x, orient_y = self.ultima_orientacao_portador

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

            _, _, v_bola_rasteira = calcular_forca_balistica(dist_atual_m, "RASTEIRO")
            destino_futuro = self._resolver_intercepcao_bhaskara(portador, comp, vx_m, vy_m, v_bola_rasteira)

            dx_fut_m = (destino_futuro[0] - portador[0]) * self.scale_x
            dy_fut_m = (destino_futuro[1] - portador[1]) * self.scale_y
            dist_fut_m = math.hypot(dx_fut_m, dy_fut_m)
            if dist_fut_m < 2.0:
                continue

            ang_passe_m = math.atan2(dy_fut_m, dx_fut_m)

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

            if (bloqueio_muito_proximo or bloqueado) and dist_fut_m > 12.0:
                tipo_passe = "CAVADO_ARCO"
            elif dist_fut_m > 48.0 and not bloqueado:
                tipo_passe = "FENOMENAL_CURVA"
            else:
                tipo_passe = "RASTEIRO"

            if tipo_passe != "RASTEIRO":
                _, _, v_bola_real = calcular_forca_balistica(dist_fut_m, tipo_passe)
                destino_futuro = self._resolver_intercepcao_bhaskara(portador, comp, vx_m, vy_m, v_bola_real)
                dx_fut_m = (destino_futuro[0] - portador[0]) * self.scale_x
                dy_fut_m = (destino_futuro[1] - portador[1]) * self.scale_y
                dist_fut_m = max(2.0, math.hypot(dx_fut_m, dy_fut_m))

            # VETOR HÍBRIDO CALIBRADO POR PERFIL DE ASSISTÊNCIA (PA1/PA2 vs PA3/Manual)
            dx_atual_m = (comp[0] - portador[0]) * self.scale_x
            dy_atual_m = (comp[1] - portador[1]) * self.scale_y
            if perfil_assist == "PA3_MANUAL":
                peso_futuro, peso_atual = 0.92, 0.08
            else:
                peso_futuro, peso_atual = 0.65, 0.35
            hx_m = peso_futuro * dx_fut_m + peso_atual * dx_atual_m
            hy_m = peso_futuro * dy_fut_m + peso_atual * dy_atual_m
            h_norm = max(1e-4, math.hypot(hx_m, hy_m))
            vetor_direcao = (hx_m / h_norm, hy_m / h_norm)

            forca_b, tempo_ms, _ = calcular_forca_balistica(dist_fut_m, tipo_passe=tipo_passe)

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

            cos_alinhamento = orient_x * vetor_direcao[0] + orient_y * vetor_direcao[1]

            sob_pressao_alta = False
            if modo_desafogo and adv_mais_prox is not None and dist_adv_mais_proximo < 1.9:
                sob_pressao_alta = True
                if tipo_passe == "FENOMENAL_CURVA":
                    tipo_passe = "RASTEIRO"
                    forca_b, tempo_ms, _ = calcular_forca_balistica(dist_fut_m, tipo_passe="RASTEIRO")
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
                "bloqueado": bloqueado,
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

        no_campo_ataque = (portador[0] >= meio_campo_x) if atacando_direita else (portador[0] <= meio_campo_x)
        if not no_campo_ataque or dist_gol_m > 28.0 or dist_gol_m < 1.0:
            return None

        adv_ordenados = sorted(adversarios, key=lambda a: abs(gol_alvo_x - a[0])) if adversarios else []
        goleiro = adv_ordenados[0] if adv_ordenados else None
        dist_gk_linha_m = abs(gol_alvo_x - goleiro[0]) * self.scale_x if goleiro else 1.0
        gk_y = goleiro[1] if goleiro else centro_y

        trave_metade_m = 3.66
        offset_trave_px = trave_metade_m / self.scale_y
        y_trave_sup = centro_y - offset_trave_px
        y_trave_inf = centro_y + offset_trave_px

        margem_trave_px = 1.1 / self.scale_y
        y_canto_sup = y_trave_sup + margem_trave_px
        y_canto_inf = y_trave_inf - margem_trave_px

        if gk_y <= centro_y:
            alvo_canto = (int(gol_alvo_x), int(round(y_canto_inf)))
            canto_nome = "CANTO INFERIOR"
        else:
            alvo_canto = (int(gol_alvo_x), int(round(y_canto_sup)))
            canto_nome = "CANTO SUPERIOR"

        dx_alvo_m = (alvo_canto[0] - portador[0]) * self.scale_x
        dy_alvo_m = (alvo_canto[1] - portador[1]) * self.scale_y
        dist_alvo_m = math.hypot(dx_alvo_m, dy_alvo_m)
        vetor_mira = (dx_alvo_m / (dist_alvo_m + 1e-5), dy_alvo_m / (dist_alvo_m + 1e-5))

        ang1 = math.atan2((y_trave_sup - portador[1]) * self.scale_y, (gol_alvo_x - portador[0]) * self.scale_x)
        ang2 = math.atan2((y_trave_inf - portador[1]) * self.scale_y, (gol_alvo_x - portador[0]) * self.scale_x)
        theta = abs(ang2 - ang1)
        if theta > math.pi:
            theta = 2.0 * math.pi - theta

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

        espaco_livre_frente_m = min([self.dist_metros(portador, a) for a in adversarios], default=99.0)

        delta_gk = max(0.0, min(5.0, dist_gk_linha_m - 2.0))
        z = 2.45 * theta - 0.082 * dist_gol_m - 0.40 * n_bloqueadores + 0.90 * (delta_gk / 3.0) - 0.25
        xg_percent = (1.0 / (1.0 + math.exp(-max(-6.0, min(6.0, z))))) * 100.0

        if dist_gk_linha_m >= 3.8 and 6.0 <= dist_gol_m <= 22.0:
            tipo_chute = "CAVADA"
            tag_hud = "CAVADINHA (LB+X)"
            modificador = SCAN_Q
            duracao_ms = int(135.0 + ((dist_gol_m - 6.0) / 16.0) * 40.0)
        elif abs(dy_gol_m) >= 3.5 and 12.0 <= dist_gol_m <= 24.0 and not bloqueio_critico:
            tipo_chute = "COLOCADO"
            tag_hud = "COLOCADO (RB+X)"
            modificador = SCAN_C
            duracao_ms = int(160.0 + ((dist_gol_m - 12.0) / 12.0) * 50.0)
        elif espaco_livre_frente_m >= 2.4 and 20.0 <= dist_gol_m <= 28.0 and not bloqueio_critico:
            tipo_chute = "FENOMENAL"
            tag_hud = "FENOMENAL (RT+X)"
            modificador = SCAN_E
            duracao_ms = int(225.0 + ((dist_gol_m - 20.0) / 8.0) * 40.0)
        else:
            tipo_chute = "RASTEIRO"
            tag_hud = "RASTEIRO FORTE (X)"
            modificador = None
            duracao_ms = int(110.0 + (min(dist_gol_m, 20.0) / 20.0) * 35.0)

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
_teclas_latched = {}

def _on_key_down(event):
    if _ignorando_hook:
        return
    nome = event.name.lower() if event.name else ""
    agora = time.perf_counter()
    with _lock_teclas:
        _teclas_ativas.add(nome)
        _teclas_latched[nome] = agora
        if nome.startswith("num ") and len(nome) == 5:
            dig = nome[-1]
            _teclas_ativas.add(dig)
            _teclas_latched[dig] = agora
        elif nome.isdigit():
            num_k = f"num {nome}"
            _teclas_ativas.add(num_k)
            _teclas_latched[num_k] = agora
    _ultima_tecla[0] = nome

def _on_key_up(event):
    if _ignorando_hook:
        return
    nome = event.name.lower() if event.name else ""
    with _lock_teclas:
        _teclas_ativas.discard(nome)
        if nome.isdigit():
            _teclas_ativas.discard(f"num {nome}")
        if nome.startswith("num ") and len(nome) == 5:
            _teclas_ativas.discard(nome[-1])

def tecla_foi_pressionada(nome_tecla):
    if not nome_tecla:
        return False
    t = str(nome_tecla).strip().lower()
    t_num = f"num {t}" if t.isdigit() else None
    agora = time.perf_counter()

    # 1. Verifica no conjunto ativo ou no latch recente (< 350ms para garantir pulsos ultra-rápidos)
    with _lock_teclas:
        if t in _teclas_ativas or (t_num and t_num in _teclas_ativas):
            _ultima_tecla[0] = t
            return True
        t_latch = max(_teclas_latched.get(t, 0.0), _teclas_latched.get(t_num, 0.0) if t_num else 0.0)
        if (agora - t_latch) < 0.350:
            _ultima_tecla[0] = t
            return True

    # 2. Verifica GetAsyncKeyState (Windows API) com máscara 0x8001 (Pressionado agora OU pulsado desde última checagem)
    try:
        vk = None
        if len(t) == 1:
            if '0' <= t <= '9':
                vk = 0x30 + int(t)
            elif 'a' <= t <= 'z':
                vk = 0x41 + (ord(t) - ord('a'))
        elif t.startswith("f") and t[1:].isdigit():
            fn_n = int(t[1:])
            if 1 <= fn_n <= 12:
                vk = 0x6F + fn_n

        if vk is not None:
            down_std = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8001)
            down_num = bool(ctypes.windll.user32.GetAsyncKeyState(0x60 + int(t)) & 0x8001) if t.isdigit() else False
            if down_std or down_num:
                with _lock_teclas:
                    _teclas_latched[t] = agora
                    if t_num:
                        _teclas_latched[t_num] = agora
                _ultima_tecla[0] = t
                return True
    except Exception:
        pass

    # 3. Fallback com keyboard.is_pressed
    try:
        if keyboard.is_pressed(t) or (t_num and keyboard.is_pressed(t_num)):
            _ultima_tecla[0] = t
            return True
    except Exception:
        pass

    return False

def consumir_tecla(*nomes_tecla):
    with _lock_teclas:
        for item in nomes_tecla:
            if not item:
                continue
            t = str(item).strip().lower()
            _teclas_ativas.discard(t)
            _teclas_latched.pop(t, None)
            if t.isdigit():
                _teclas_ativas.discard(f"num {t}")
                _teclas_latched.pop(f"num {t}", None)


class TelemetriaPasses:
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
        self.tenho_posse_bola = False
        self.sou_time_verde = True
        self.atacando_direita = True
        self.radar_ativo = False
        self.rp2040_conectado = False
        self.analog_dir = (0.0, 0.0)
        self.candidatos_passe = []
        self.scale_x = CAMPO_LARGURA_M / 260.0
        self.scale_y = CAMPO_ALTURA_M / 130.0
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
                    if "auto_disparo_facao" in salvo:
                        cfg["auto_disparo_facao"] = salvo["auto_disparo_facao"]
                    if "perfil_assistencia" in salvo:
                        cfg["perfil_assistencia"] = salvo["perfil_assistencia"]
                    if "feedback_haptico" in salvo:
                        cfg["feedback_haptico"] = salvo["feedback_haptico"]
                    if "overlay_ingame" in salvo:
                        cfg["overlay_ingame"] = salvo["overlay_ingame"]
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
# 5. PONTE DE HARDWARE RP2040 & EXECUTOR ASSÍNCRONO COM PRE-AIM E FOLLOW-THROUGH
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
    Máquina de estados não-bloqueante com Pre-Aim Lead-In (25ms antes do passe)
    e Post-Release Follow-Through (75ms após soltar a barra).
    Se o RP2040 estiver ativo, envia 100% via CircuitPython HID (sem poluir com Teclado),
    garantindo que o eFootball obedeça cegamente ao Eixo X / Eixo Y de 360° da IA!
    """
    PRE_AIM_LEAD_S = 0.025      # 25ms apontando o analógico 360° antes de apertar Y/B/X
    POST_HOLD_DIR_S = 0.075     # 75ms mantendo o analógico 360° travado após soltar a barra

    def __init__(self):
        self.lock = threading.Lock()
        self.ativo = False
        self.rp2040_ativo = False
        self.eventos_dx = []
        self.fim_acao_ts = 0.0
        self.override_lx = None
        self.override_ly = None
        self.override_btns = 0
        self.teclas_direcao_ativas = []

    def agendar_sequencia(self, etapas_dx, duracao_botoes_s, vetor_dir=None, injetar_setas_dx=False, rp2040_ativo=True):
        agora = time.perf_counter()
        with self.lock:
            directx_liberar_tudo()
            self.eventos_dx.clear()

            self.ativo = True
            self.rp2040_ativo = rp2040_ativo
            lead = self.PRE_AIM_LEAD_S if vetor_dir is not None else 0.0
            hold_after = self.POST_HOLD_DIR_S if vetor_dir is not None else 0.010

            self.fim_acao_ts = agora + lead + duracao_botoes_s + hold_after
            self.override_btns = 0

            if vetor_dir is not None:
                # Força amplitude máxima (raio 1.0) no eixo do RP2040 para cravar a direção
                norm = max(1e-4, math.hypot(vetor_dir[0], vetor_dir[1]))
                self.override_lx = vetor_dir[0] / norm
                self.override_ly = vetor_dir[1] / norm

                # Só injeta setas do teclado se NÃO estiver usando o analógico do RP2040
                if injetar_setas_dx and not rp2040_ativo:
                    self.teclas_direcao_ativas = obter_scancodes_direcao(self.override_lx, self.override_ly)
                    for sc_dir in self.teclas_direcao_ativas:
                        directx_press(sc_dir)
            else:
                self.override_lx, self.override_ly = None, None
                self.teclas_direcao_ativas = []

            for delay_s, fn, sc in etapas_dx:
                self.eventos_dx.append((agora + lead + delay_s, fn, sc))
            self.eventos_dx.sort(key=lambda x: x[0])

    def atualizar(self):
        agora = time.perf_counter()
        with self.lock:
            if not self.ativo:
                return False, 0, None, None

            while self.eventos_dx and agora >= self.eventos_dx[0][0]:
                _, fn, sc = self.eventos_dx.pop(0)
                # Dispara SEMPRE o botão de ação no DirectX (SCAN_W, SCAN_D, SCAN_A, etc.)
                # para garantir que o passe/cruzamento nunca falhe!
                fn(sc)
                # E sincroniza os bits para o RP2040 simultaneamente:
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
def selecionar_passe_curto_direcionado(candidatos, analog_dir, atacando_direita, scale_x, scale_y):
    """
    Seleciona o companheiro mais próximo e bem alinhado com a direção mirada pelo analógico esquerdo (lx, ly),
    priorizando um lançamento curto, rasteiro e veloz para o recebedor escolhido.
    """
    if not candidatos:
        return None

    an_x, an_y = analog_dir
    an_norm = math.hypot(an_x, an_y)

    if an_norm >= 0.18:
        u_ax, u_ay = an_x / an_norm, an_y / an_norm
    else:
        # Analógico solto / centro: mira para frente no sentido de ataque
        u_ax = 1.0 if atacando_direita else -1.0
        u_ay = 0.0

    melhor_cand = None
    melhor_score = -9999.0

    for c in candidatos:
        if c.get("impedido", False):
            continue

        # Vetor de passe futuro e vetor para a posição atual
        v_dir = c.get("vetor_direcao", (1.0, 0.0))
        cos_alinh_fut = v_dir[0] * u_ax + v_dir[1] * u_ay

        origem = c["origem"]
        destino = c["destino"]
        dx_comp = (destino[0] - origem[0]) * scale_x
        dy_comp = (destino[1] - origem[1]) * scale_y
        dist_comp = max(0.1, math.hypot(dx_comp, dy_comp))
        cos_alinh_pos = (dx_comp * u_ax + dy_comp * u_ay) / dist_comp

        alinhamento = max(cos_alinh_fut, cos_alinh_pos)

        # Se o usuário está apontando ativamente o analógico, ignora quem estiver fora do cone de mira (~75°)
        if an_norm >= 0.18 and alinhamento < 0.25:
            continue

        dist_m = c.get("dist_metros", dist_comp)

        # Critério específico para "lançamento mais curto para quem eu mirar":
        # 1. Alinhamento direcional da mira é primordial (+85 * alinhamento)
        # 2. Prioriza fortemente opções curtas e médias (7m a 20m)
        # 3. Penaliza fortemente opções longas (> 24m)
        score_curto = 50.0 + (85.0 * alinhamento)

        if dist_m <= 16.0:
            score_curto += 35.0 - (dist_m * 0.8)  # Mais perto = maior prioridade
        elif dist_m <= 24.0:
            score_curto += 15.0 - (dist_m - 16.0) * 1.5
        else:
            score_curto -= 25.0 + (dist_m - 24.0) * 3.5  # Penalidade acentuada para bolas longas

        if c.get("bloqueado", False):
            score_curto -= 14.0
        if c.get("rompimento", False):
            score_curto += 10.0

        if score_curto > melhor_score:
            melhor_score = score_curto
            melhor_cand = c

    if melhor_cand:
        dp = copy.deepcopy(melhor_cand)
        # Força passe rasteiro curto, sem cavadinha e sem fenomenal
        dp["tipo_passe"] = "RASTEIRO"
        dp["aereo"] = False
        dist_final = dp.get("dist_metros", 15.0)
        # Barra calibrada curta para passe rasteiro ágil: 115ms a 170ms
        dur_ms = int(115.0 + (min(dist_final, 28.0) / 28.0) * 55.0)
        dp["tempo_ms"] = dur_ms
        return dp

    return None


def _disparar_lancamento_ia(dp, usar_mira_360, injetar_setas_dx, estado, executor, origem_gatilho="MANUAL"):
    """Função auxiliar unificada para executar o lançamento teleguiado (Manual ou Auto-Facão)."""
    tempo_sec = max(0.125, min(0.350, dp["tempo_ms"] / 1000.0))
    aereo = dp.get("aereo", False)
    tipo_p = dp.get("tipo_passe", "RASTEIRO")
    dist_m = dp.get("dist_metros", 20.0)
    vetor_dir = dp.get("vetor_direcao") if usar_mira_360 else None
    estado.telemetria.registrar_disparo(dp, tempo_sec * 1000.0, aereo)

    ang_graus = math.degrees(math.atan2(vetor_dir[1], vetor_dir[0])) if vetor_dir else 0.0
    rp_ativo = estado.rp2040_conectado

    if tipo_p == "CAVADO_ARCO" or aereo:
        print(f"\n[{origem_gatilho}] 🎯 Lançamento CAVADO EM ARCO (LB+W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms | Mira={ang_graus:.0f}°")
        etapas = [
            (0.000, directx_press, SCAN_Q),
            (0.015, directx_press, SCAN_W),
            (0.015 + tempo_sec, directx_release, SCAN_W),
            (0.025 + tempo_sec, directx_release, SCAN_Q)
        ]
        executor.agendar_sequencia(etapas, tempo_sec + 0.025, vetor_dir, injetar_setas_dx, rp2040_ativo=rp_ativo)
    elif tipo_p == "FENOMENAL_CURVA":
        print(f"\n[{origem_gatilho}] 🌀 Lançamento FENOMENAL (RT+W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms | Mira={ang_graus:.0f}°")
        etapas = [
            (0.000, directx_press, SCAN_E),
            (0.015, directx_press, SCAN_W),
            (0.015 + tempo_sec, directx_release, SCAN_W),
            (0.025 + tempo_sec, directx_release, SCAN_E)
        ]
        executor.agendar_sequencia(etapas, tempo_sec + 0.025, vetor_dir, injetar_setas_dx, rp2040_ativo=rp_ativo)
    else:
        print(f"\n[{origem_gatilho}] 🎯 Lançamento RASTEIRO IA (W): Dist={dist_m:.1f}m | Barra={tempo_sec*1000:.0f}ms | Mira={ang_graus:.0f}°")
        etapas = [
            (0.000, directx_press, SCAN_W),
            (tempo_sec, directx_release, SCAN_W)
        ]
        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, injetar_setas_dx, rp2040_ativo=rp_ativo)


def thread_controle_execucao(estado: EstadoSistema):
    ser = None
    try:
        p = encontrar_porta_rp2040()
        ser = serial.Serial(p, 115200, timeout=0)
        estado.rp2040_conectado = True
        print(f"[RP2040] ✅ Conectado na porta {p} (Bridge 360° de Baixa Latência ativa)")
    except Exception:
        print("[RP2040] ℹ️ Placa não encontrada — operando com injeção nativa DirectX (Teclado + Setas)!")

    pygame.init()
    pygame.joystick.init()
    keyboard.on_press(_on_key_down, suppress=False)
    keyboard.on_release(_on_key_up, suppress=False)

    vader = None
    executor = ExecutorAcaoAssincrono()
    ultimo_disparo = 0.0
    ultimo_auto_facao = 0.0
    cooldown = 0.28

    ant_lanc = False
    ant_btn_y = False
    ant_cruz = False
    ant_btn_b = False
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
            auto_facao = estado.config.get("auto_disparo_facao", False)

            # Injetamos setas do teclado se a mira 360 estiver ativa E (RP2040 desconectado OU analógico físico solto)
            analog_fisico_parado = (math.hypot(lx, ly) < 0.22)
            injetar_setas_dx = usar_mira_360 and ((not estado.rp2040_conectado) or analog_fisico_parado)

            # --- 1A. AUTO-TRIGGER DE FACÃO (100% Automático quando atacante rompe a linha livre) ---
            if auto_facao and (agora - ultimo_disparo > 0.65) and (agora - ultimo_auto_facao > 1.80):
                with estado.lock:
                    dp_auto = copy.deepcopy(estado.dados_passe) if (estado.dados_passe and estado.tenho_posse_bola) else None
                if dp_auto and dp_auto.get("rompimento") and not dp_auto.get("impedido") and not dp_auto.get("bloqueado"):
                    if dp_auto.get("score", 0.0) >= 122.0 and dp_auto.get("velocidade_kmh", 0.0) >= 16.0:
                        ultimo_disparo = agora
                        ultimo_auto_facao = agora
                        if estado.config.get("feedback_haptico", True):
                            disparar_rumble_haptico(left_speed=38000, right_speed=0, duracao_s=0.16)
                        _disparar_lancamento_ia(dp_auto, True, injetar_setas_dx, estado, executor, origem_gatilho="AUTO-FACÃO IA")

            # --- 1B. LANÇAMENTO TELEGUIADO IA (Ao tocar na tecla 5 ou Botão Y do controle) ---
            tecla_lanc = hk.get("lancamento_ia", "5")
            press_lanc = tecla_foi_pressionada(tecla_lanc)
            press_btn_y = vader.get_button(VADER_BTN_Y) if vader else False
            press_btn_lb = vader.get_button(VADER_BTN_LB) if vader else False

            # Combo LB+Y no controle OU Tecla 5 (macro M1/M2/M3/M4/CZ) = Lançamento Tático Profundo (Facão)
            trigger_tatico = press_lanc or (press_btn_y and press_btn_lb)

            # 1B.1 - LANÇAMENTO TÁTICO PROFUNDO / FACÃO IA (Tecla 5 ou LB+Y)
            if trigger_tatico:
                if not ant_lanc and (agora - ultimo_disparo > cooldown):
                    ant_lanc = True
                    ant_btn_y = True
                    ultimo_disparo = agora
                    if press_lanc:
                        consumir_tecla(tecla_lanc)

                    with estado.lock:
                        if estado.dados_passe:
                            dp = copy.deepcopy(estado.dados_passe)
                        elif estado.ultimo_passe_valido and (agora - estado.ultima_validade_ts <= 0.85):
                            dp = copy.deepcopy(estado.ultimo_passe_valido)
                        else:
                            dp = None

                    origem_nome = "TECLA 5 (FACÃO IA)" if press_lanc else "LB+Y CONTROLE (FACÃO IA)"
                    if dp:
                        _disparar_lancamento_ia(dp, usar_mira_360, injetar_setas_dx, estado, executor, origem_gatilho=origem_nome)
                    else:
                        dir_frente = 1.0 if estado.atacando_direita else -1.0
                        an_norm = math.hypot(lx, ly)
                        vetor_disparo = (lx / an_norm, ly / an_norm) if an_norm > 0.22 else (dir_frente, 0.0)
                        alvo_aprox = (int(130 + 38 * vetor_disparo[0]), int(65 + 38 * vetor_disparo[1]))
                        estado.telemetria.registrar_disparo({
                            "dist_metros": 18.0,
                            "destino_futuro": alvo_aprox,
                            "origem": (130, 65),
                            "tipo_passe": "RASTEIRO"
                        }, 175.0, False)
                        print(f"\n[{origem_nome}] 🎯 Lançamento Direto (Direção Analógico) -> Y/W (175ms)")
                        etapas = [
                            (0.000, directx_press, SCAN_W),
                            (0.175, directx_release, SCAN_W)
                        ]
                        executor.agendar_sequencia(etapas, 0.175, vetor_disparo if usar_mira_360 else None, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
            else:
                ant_lanc = False

            # 1B.2 - BOTÃO Y SIMPLES DO CONTROLE (Sem LB): Lançamento curto direcionado ao jogador mirado no analógico
            if press_btn_y and not press_btn_lb:
                if not ant_btn_y and (agora - ultimo_disparo > cooldown):
                    ant_btn_y = True
                    ultimo_disparo = agora
                    with estado.lock:
                        candidatos = list(estado.candidatos_passe) if estado.tenho_posse_bola else []
                        posse = estado.tenho_posse_bola
                        sc_x = estado.scale_x
                        sc_y = estado.scale_y

                    dp_curto = None
                    if posse and candidatos:
                        dp_curto = selecionar_passe_curto_direcionado(
                            candidatos, (lx, ly), estado.atacando_direita, sc_x, sc_y
                        )

                    if dp_curto:
                        _disparar_lancamento_ia(
                            dp_curto, usar_mira_360, injetar_setas_dx, estado, executor,
                            origem_gatilho="Y CONTROLE (MIRA CURTA)"
                        )
                    else:
                        dir_frente = 1.0 if estado.atacando_direita else -1.0
                        an_norm = math.hypot(lx, ly)
                        vetor_disparo = (lx / an_norm, ly / an_norm) if an_norm > 0.20 else (dir_frente, 0.0)
                        alvo_aprox = (int(130 + 30 * vetor_disparo[0]), int(65 + 30 * vetor_disparo[1]))
                        estado.telemetria.registrar_disparo({
                            "dist_metros": 14.0,
                            "destino_futuro": alvo_aprox,
                            "origem": (130, 65),
                            "tipo_passe": "RASTEIRO"
                        }, 140.0, False)
                        ang_d = math.degrees(math.atan2(vetor_disparo[1], vetor_disparo[0]))
                        print(f"\n[Y CONTROLE] 🎯 Lançamento Curto Direto (Analógico {ang_d:.0f}°) -> Y/W (140ms)")
                        etapas = [
                            (0.000, directx_press, SCAN_W),
                            (0.140, directx_release, SCAN_W)
                        ]
                        executor.agendar_sequencia(etapas, 0.140, vetor_disparo if usar_mira_360 else None, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
            elif not press_btn_y:
                ant_btn_y = False

            # --- 2. CRUZAMENTO INTELIGENTE IA (Ao tocar na tecla 6 ou Botão B do controle) ---
            tecla_cruz = hk.get("cruzamento_ia", "6")
            press_cruz = tecla_foi_pressionada(tecla_cruz)
            press_btn_b = vader.get_button(VADER_BTN_B) if vader else False

            with estado.lock:
                dc = copy.deepcopy(estado.dados_cruzamento) if estado.dados_cruzamento else None

            trigger_cruz_key = press_cruz and not ant_cruz
            trigger_cruz_gp = press_btn_b and not ant_btn_b and (dc is not None)

            if (trigger_cruz_key or trigger_cruz_gp) and (agora - ultimo_disparo > cooldown):
                ultimo_disparo = agora
                if trigger_cruz_key:
                    consumir_tecla(tecla_cruz)

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
                        executor.agendar_sequencia(etapas, 0.075 + t2, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    elif tipo in ("BALAO_ALTO", "ANTECIPADO"):
                        etapas = [
                            (0.000, directx_press, SCAN_Q),
                            (0.020, directx_press, SCAN_D),
                            (0.020 + tempo_sec, directx_release, SCAN_D),
                            (0.028 + tempo_sec, directx_release, SCAN_Q)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    elif tipo == "FENOMENAL":
                        etapas = [
                            (0.000, directx_press, SCAN_D),
                            (0.006, directx_press, SCAN_E),
                            (tempo_sec, directx_release, SCAN_D),
                            (tempo_sec + 0.015, directx_release, SCAN_E)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.015, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    else:
                        etapas = [
                            (0.000, directx_press, SCAN_D),
                            (tempo_sec, directx_release, SCAN_D)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                else:
                    print("\n[DISPARO] ⚡ Cruzamento Manual (Sem alvo na área) -> D (170ms)")
                    etapas = [
                        (0.000, directx_press, SCAN_D),
                        (0.170, directx_release, SCAN_D)
                    ]
                    executor.agendar_sequencia(etapas, 0.170, None, False, rp2040_ativo=estado.rp2040_conectado)

            ant_cruz = press_cruz
            ant_btn_b = press_btn_b

            # --- 3. FINALIZAÇÃO INTELIGENTE IA (xG & MIRA 360°) ---
            usar_finalizacao = estado.config.get("usar_finalizacao_inteligente", True)
            tecla_chute = hk.get("chute_ia", "4")
            press_chute_key = tecla_foi_pressionada(tecla_chute)
            press_btn_x = vader.get_button(VADER_BTN_X) if vader else False

            with estado.lock:
                tem_dados_chute = (estado.dados_chute is not None) and estado.tenho_posse_bola

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
                        etapas = [
                            (0.000, directx_press, SCAN_Q),
                            (0.020, directx_press, SCAN_A),
                            (0.020 + tempo_sec, directx_release, SCAN_A),
                            (0.028 + tempo_sec, directx_release, SCAN_Q)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    elif mod == SCAN_C:
                        etapas = [
                            (0.000, directx_press, SCAN_C),
                            (0.020, directx_press, SCAN_A),
                            (0.020 + tempo_sec, directx_release, SCAN_A),
                            (0.028 + tempo_sec, directx_release, SCAN_C)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.028, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    elif mod == SCAN_E:
                        etapas = [
                            (0.000, directx_press, SCAN_E),
                            (0.025, directx_press, SCAN_A),
                            (0.025 + tempo_sec, directx_release, SCAN_A),
                            (0.032 + tempo_sec, directx_release, SCAN_E)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec + 0.032, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                    else:
                        etapas = [
                            (0.000, directx_press, SCAN_A),
                            (tempo_sec, directx_release, SCAN_A)
                        ]
                        executor.agendar_sequencia(etapas, tempo_sec, vetor_dir, injetar_setas_dx, rp2040_ativo=estado.rp2040_conectado)
                else:
                    print("\n[CHUTE] ⚽ Chute Rápido (Sem mira xG ativa) -> A (135ms)")
                    etapas = [
                        (0.000, directx_press, SCAN_A),
                        (0.135, directx_release, SCAN_A)
                    ]
                    executor.agendar_sequencia(etapas, 0.135, None, False, rp2040_ativo=estado.rp2040_conectado)

            ant_chute_key = press_chute_key
            ant_btn_x = press_btn_x

            # --- 4. INVERTER TIME MANUALMENTE (F10) & TOGGLE OVERLAY (F11) ---
            tecla_inv = hk.get("inverter_cor_time", "f10")
            if tecla_foi_pressionada(tecla_inv):
                consumir_tecla(tecla_inv)
                with estado.lock:
                    estado.sou_time_verde = not estado.sou_time_verde
                    novo_modo = "VERDE" if estado.sou_time_verde else "VERMELHO"
                    estado.config["modo_cor_time"] = novo_modo
                    estado.salvar_config()
                    print(f"\n[TIME] Invertido manualmente e salvo: {novo_modo}")

            tecla_ovl = hk.get("toggle_overlay", "f11")
            if tecla_foi_pressionada(tecla_ovl):
                consumir_tecla(tecla_ovl)
                with estado.lock:
                    estado.config["overlay_ingame"] = not estado.config.get("overlay_ingame", True)
                    estado.salvar_config()
                    print(f"\n[OVERLAY] Alternado via F11: {estado.config['overlay_ingame']}")

            # --- 5. ATUALIZA MÁQUINA DE ESTADOS E PASSTHROUGH RP2040 ---
            em_acao, ov_btns, ov_lx, ov_ly = executor.atualizar()

            if ser and ser.is_open:
                buttons = 0
                if vader:
                    # Converte do padrão XInput (Flydigi) para o padrão da sua tela CircuitPython HID:
                    if vader.get_button(VADER_BTN_X):     buttons |= (1 << RP_BTN_X)      # Botão 0
                    if vader.get_button(VADER_BTN_A):     buttons |= (1 << RP_BTN_A)      # Botão 1
                    if vader.get_button(VADER_BTN_B):     buttons |= (1 << RP_BTN_B)      # Botão 2
                    if vader.get_button(VADER_BTN_Y):     buttons |= (1 << RP_BTN_Y)      # Botão 3
                    if vader.get_button(VADER_BTN_LB):    buttons |= (1 << RP_BTN_LB)     # Botão 4
                    if vader.get_button(VADER_BTN_RB):    buttons |= (1 << RP_BTN_RB)     # Botão 5
                    if vader.get_button(VADER_BTN_BACK):  buttons |= (1 << RP_BTN_BACK)   # Botão 8
                    if vader.get_button(VADER_BTN_START): buttons |= (1 << RP_BTN_START)  # Botão 9
                    if vader.get_button(VADER_BTN_LS):    buttons |= (1 << RP_BTN_LS)     # Botão 10
                    if vader.get_button(VADER_BTN_RS):    buttons |= (1 << RP_BTN_RS)     # Botão 11

                    # Gatilhos Analógicos LT (Axis 4) e RT (Axis 5) do Flydigi -> Botão 6 e Botão 7
                    if vader.get_numaxes() >= 6:
                        if vader.get_axis(4) > 0.3:  # LT pressionado
                            buttons |= (1 << RP_BTN_LT)
                        if vader.get_axis(5) > 0.3:  # RT pressionado (Corrida)
                            buttons |= (1 << RP_BTN_RT)

                if em_acao:
                    # Durante o passe/cruzamento/chute da IA:
                    # 1. Limpa os botões de ação física (incluindo RT de corrida) para não conflitar com o comando da IA
                    mascara_ia = (
                        (1 << RP_BTN_X) | (1 << RP_BTN_A) | (1 << RP_BTN_B) | (1 << RP_BTN_Y) |
                        (1 << RP_BTN_LB) | (1 << RP_BTN_RB) | (1 << RP_BTN_RT)
                    )
                    buttons = (buttons & ~mascara_ia) | ov_btns
                    # 2. Substitui 100% o Eixo X e Eixo Y pelo vetor 360° calculado pela IA!
                    out_lx = ov_lx if ov_lx is not None else lx
                    out_ly = ov_ly if ov_ly is not None else ly
                else:
                    out_lx, out_ly = lx, ly

                enviar_relatorio_rp2040(ser, buttons, out_lx, out_ly, rx, ry)

            atualizar_rumble_haptico()
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
    ultimo_rumble_chute = 0.0

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
            melhor_chute = None
            tenho_posse = False
            todos_candidatos = []

            if len(meus_jogadores) >= 2:
                if pos_bola is not None and cursor_usuario is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - cursor_usuario[0], p[1] - cursor_usuario[1]) * 0.7 + math.hypot(p[0] - pos_bola[0], p[1] - pos_bola[1]) * 0.3)
                elif cursor_usuario is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - cursor_usuario[0], p[1] - cursor_usuario[1]))
                elif pos_bola is not None:
                    meus_jogadores.sort(key=lambda p: math.hypot(p[0] - pos_bola[0], p[1] - pos_bola[1]))

                portador = meus_jogadores[0]
                companheiros = meus_jogadores[1:]

                # Confirmação de posse de bola real (evita auto-chute ou auto-facão quando estamos defendendo)
                dist_meu_cursor = math.hypot(portador[0] - cursor_usuario[0], portador[1] - cursor_usuario[1]) if cursor_usuario else 99.0
                dist_meu_bola = math.hypot(portador[0] - pos_bola[0], portador[1] - pos_bola[1]) if pos_bola else 6.0
                dist_adv_bola = min([math.hypot(a[0] - pos_bola[0], a[1] - pos_bola[1]) for a in adversarios], default=99.0) if pos_bola else 99.0
                if cursor_usuario is not None and dist_meu_cursor < 22.0:
                    tenho_posse = True
                elif pos_bola is not None and dist_meu_bola <= dist_adv_bola + 4.0:
                    tenho_posse = True
                else:
                    tenho_posse = (dist_meu_cursor < 32.0) if cursor_usuario else True

                with estado.lock:
                    analog_dir = estado.analog_dir
                    modo_desafogo = estado.config.get("modo_desafogo_pressao", True)
                    perfil_assist = estado.config.get("perfil_assistencia", "PA1_PA2")
                    feedback_haptico = estado.config.get("feedback_haptico", True)

                livres, bloqueados = processador.analisar_linhas_de_passe(
                    portador, companheiros, adversarios,
                    atacando_direita=atacando_direita, linha_zaga=linha_x,
                    analog_dir=analog_dir, modo_desafogo=modo_desafogo,
                    perfil_assist=perfil_assist
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

                    if feedback_haptico and tenho_posse and xg_val >= 65.0:
                        agora_ts = time.perf_counter()
                        if agora_ts - ultimo_rumble_chute > 1.8:
                            ultimo_rumble_chute = agora_ts
                            disparar_rumble_haptico(left_speed=0, right_speed=46000, duracao_s=0.18)

            if cursor_usuario is not None:
                cv2.circle(overlay, cursor_usuario, 7, (0, 255, 255), 2)
            if pos_bola is not None:
                cv2.circle(overlay, pos_bola, 3, (255, 255, 255), -1)

            agora_ts = time.perf_counter()
            with estado.lock:
                estado.radar_ativo = True
                estado.tenho_posse_bola = tenho_posse
                estado.dados_passe = melhor_passe
                estado.candidatos_passe = list(todos_candidatos)
                estado.scale_x = processador.scale_x
                estado.scale_y = processador.scale_y
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
# 8. HUD FLUTUANTE IN-GAME TRANSPARENTE E INTERFACE GRÁFICA MODERNA
# ==============================================================================
class OverlayInGame:
    def __init__(self, master, estado: EstadoSistema):
        self.master = master
        self.estado = estado
        self.top = tk.Toplevel(master)
        self.top.title("eFootball Master HUD")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)

        self.trans_color = "#000001"
        self.top.attributes("-transparentcolor", self.trans_color)
        self.top.config(bg=self.trans_color)

        sw = self.top.winfo_screenwidth()
        pos_x = max(20, sw - 415)
        pos_y = 25
        self.top.geometry(f"395x135+{pos_x}+{pos_y}")
        self.top.update_idletasks()
        self._tornar_click_through()

        self.frame_hud = tk.Frame(self.top, bg="#0d0e17", padx=10, pady=8, highlightbackground="#00e5ff", highlightthickness=1)
        self.frame_hud.pack(fill="both", expand=True)

        self.lbl_titulo = tk.Label(self.frame_hud, text="⚡ EFOOTBALL MASTER V3.0 HUD", font=("Segoe UI", 9, "bold"), fg="#00e5ff", bg="#0d0e17")
        self.lbl_titulo.pack(anchor="w")

        self.lbl_status = tk.Label(self.frame_hud, text="● Conectando...", font=("Consolas", 8), fg="#00ff88", bg="#0d0e17")
        self.lbl_status.pack(anchor="w", pady=(2, 0))

        self.lbl_passe = tk.Label(self.frame_hud, text="🎯 PASSE: --", font=("Consolas", 8), fg="#ffffff", bg="#0d0e17")
        self.lbl_passe.pack(anchor="w")

        self.lbl_chute = tk.Label(self.frame_hud, text="⚽ CHUTE: --", font=("Consolas", 8), fg="#ffcc00", bg="#0d0e17")
        self.lbl_chute.pack(anchor="w")

        self.lbl_perfil = tk.Label(self.frame_hud, text="⚙️ PERFIL: PA1_PA2 | HÁPTICO: SIM", font=("Consolas", 7), fg="#8888aa", bg="#0d0e17")
        self.lbl_perfil.pack(anchor="w")

        self.visivel = True

    def _tornar_click_through(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id())
            if not hwnd:
                hwnd = self.top.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

    def destruir(self):
        try:
            self.top.destroy()
        except Exception:
            pass

    def atualizar(self):
        ativo = self.estado.config.get("overlay_ingame", True)
        if not ativo:
            if self.visivel:
                self.top.withdraw()
                self.visivel = False
            return
        else:
            if not self.visivel:
                self.top.deiconify()
                self.visivel = True

        with self.estado.lock:
            posse = self.estado.tenho_posse_bola
            sou_verde = self.estado.sou_time_verde
            dp = self.estado.dados_passe
            dc = self.estado.dados_chute
            rp = self.estado.rp2040_conectado
            perfil = self.estado.config.get("perfil_assistencia", "PA1_PA2")
            haptico = self.estado.config.get("feedback_haptico", True)
            autofacao = self.estado.config.get("auto_disparo_facao", False)

        time_str = "VERDE" if sou_verde else "VERMELHO"
        posse_str = "🟢 POSSE DE BOLA" if posse else "⚪ DEFENDENDO"
        rp_str = "RP2040 1000Hz" if rp else "DirectX"
        self.lbl_status.configure(
            text=f"{posse_str} | {time_str} | {rp_str}",
            fg="#00ff88" if posse else "#8888aa"
        )

        if dp and posse:
            tp = dp.get("tipo_passe", "RASTEIRO")
            dist = dp.get("dist_metros", 0.0)
            ms = dp.get("tempo_ms", 0)
            score = dp.get("score", 0.0)
            romp = " [FACÃO]" if dp.get("rompimento") else ""
            self.lbl_passe.configure(
                text=f"🎯 PASSE: {tp}{romp} {dist:.1f}m ({ms}ms) Sc:{score:.0f}",
                fg="#00ffcc"
            )
        else:
            self.lbl_passe.configure(text="🎯 PASSE: Monitorando campo...", fg="#666688")

        if dc and posse:
            xg = dc.get("xg_percent", 0.0)
            tag = dc.get("tag_hud", "CHUTE")
            canto = dc.get("canto_nome", "GOL")
            cor = "#00ff88" if xg >= 60 else ("#ffaa00" if xg >= 40 else "#ff5555")
            self.lbl_chute.configure(
                text=f"⚽ CHUTE: {tag} ({canto}) xG: {xg:.0f}%",
                fg=cor
            )
        else:
            self.lbl_chute.configure(text="⚽ CHUTE: Sem linha limpa", fg="#555577")

        hap_str = "ON" if haptico else "OFF"
        fac_str = "ARMADO" if autofacao else "OFF"
        self.lbl_perfil.configure(
            text=f"⚙️ PERFIL: {perfil} | HÁPTICO: {hap_str} | AUTO-FACÃO: {fac_str}"
        )


class InterfaceMestre:
    def __init__(self, estado: EstadoSistema):
        self.estado = estado
        self.root = tk.Tk()
        self.root.title("⚽ eFootball Master AI & Controller Hub (V3.0 Elite)")
        sw = self.root.winfo_screenwidth()
        pos_x = max(20, sw - 670)
        pos_y = 25
        self.root.geometry(f"640x820+{pos_x}+{pos_y}")
        self.root.configure(bg="#0c0c14")
        self.root.resizable(True, True)
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
            topo, text="⚡ EFOOTBALL MASTER AI & CONTROLLER HUB V2.3",
            font=("Segoe UI", 12, "bold"), fg="#00ffcc", bg="#121220"
        ).pack()
        tk.Label(
            topo, text="Pre-Aim 18ms + Follow-Through 65ms + Vetor Híbrido 360° + Auto-Facão",
            font=("Segoe UI", 8), fg="#8888aa", bg="#121220"
        ).pack()

        # 1. Barra de status e monitor empacotados no rodapé ANTES do notebook para NUNCA serem cortados
        self.lbl_tecla_monitor = tk.Label(
            self.root, text="🔑 Monitor: Aguardando toque no controle...",
            bg="#080810", fg="#666688", font=("Consolas", 9), pady=4
        )
        self.lbl_tecla_monitor.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(
            self.root, text="Iniciando...",
            bg="#0f0f1c", fg="#00ff88", font=("Segoe UI", 8), pady=3
        )
        self.lbl_status.pack(fill="x", side="bottom")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=6)

        self.tab_visao = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_visao, text="  👁️ Visão Computacional  ")

        self.tab_stats = tk.Frame(self.notebook, bg="#0c0c14")
        self.notebook.add(self.tab_stats, text="  📊 Estatísticas do Lançamento  ")

        self._construir_aba_visao()
        self._construir_aba_estatisticas()

        self.overlay = OverlayInGame(self.root, self.estado)
        self.atualizar_status()

    def _construir_aba_visao(self):
        frame_time = tk.LabelFrame(
            self.tab_visao, text=" Detecção de Equipe & Assistência Autônoma da IA ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=4
        )
        frame_time.pack(fill="x", padx=10, pady=4)

        self.var_modo = tk.StringVar(value=self.estado.config.get("modo_cor_time", "AUTO"))
        for val, txt in [
            ("AUTO", "Automático (Anel Amarelo sobre jogador com a bola)"),
            ("VERDE", "Forçar Verde (Mandante)"),
            ("VERMELHO", "Forçar Vermelho (Visitante)")
        ]:
            rb = tk.Radiobutton(
                frame_time, text=txt, value=val, variable=self.var_modo,
                command=self.mudar_modo, bg="#0c0c14", fg="#ffffff", selectcolor="#1c1c30",
                activebackground="#0c0c14", font=("Segoe UI", 8)
            )
            rb.pack(anchor="w", pady=1)

        self.var_mira360 = tk.BooleanVar(value=self.estado.config.get("usar_mira_automatica_360", True))
        cb_mira = tk.Checkbutton(
            frame_time, text="Ativar Mira Direcional 100% IA (Pre-Aim 18ms + Follow-Through 65ms)",
            variable=self.var_mira360, command=self.mudar_mira360,
            bg="#0c0c14", fg="#00ff88", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8, "bold")
        )
        cb_mira.pack(anchor="w", pady=1)

        self.var_autofacao = tk.BooleanVar(value=self.estado.config.get("auto_disparo_facao", False))
        cb_autofacao = tk.Checkbutton(
            frame_time, text="Auto-Disparo de Lançamento em Facão Claro (IA passa sozinha na infiltração)",
            variable=self.var_autofacao, command=self.mudar_autofacao,
            bg="#0c0c14", fg="#ff77ff", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8, "bold")
        )
        cb_autofacao.pack(anchor="w", pady=1)

        self.var_desafogo = tk.BooleanVar(value=self.estado.config.get("modo_desafogo_pressao", True))
        cb_desafogo = tk.Checkbutton(
            frame_time, text="Ativar Modo Desafogo Rápido (Quick-Release sob pressão < 1.9m)",
            variable=self.var_desafogo, command=self.mudar_desafogo,
            bg="#0c0c14", fg="#00ffcc", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8)
        )
        cb_desafogo.pack(anchor="w", pady=1)

        self.var_chute = tk.BooleanVar(value=self.estado.config.get("usar_finalizacao_inteligente", True))
        cb_chute = tk.Checkbutton(
            frame_time, text="Ativar Finalização Inteligente xG (Gatilho X no Ataque / Tecla 4)",
            variable=self.var_chute, command=self.mudar_finalizacao,
            bg="#0c0c14", fg="#ffcc00", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8, "bold")
        )
        cb_chute.pack(anchor="w", pady=1)

        frame_perfil = tk.LabelFrame(
            self.tab_visao, text=" Perfil de Assistência do Jogo & Vetor Híbrido ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=4
        )
        frame_perfil.pack(fill="x", padx=10, pady=4)

        self.var_perfil = tk.StringVar(value=self.estado.config.get("perfil_assistencia", "PA1_PA2"))
        for val, txt, desc in [
            ("PA1_PA2", "PA1 / PA2 (Magnético)", "Compensa atração do jogo (65% Ponto Futuro / 35% Atleta)"),
            ("PA3_MANUAL", "PA3 / Manual Puro", "Física Balística Pura Bhaskara (92% Ponto Futuro / 8% Atleta)")
        ]:
            f_rb = tk.Frame(frame_perfil, bg="#0c0c14")
            f_rb.pack(fill="x", pady=1)
            rb = tk.Radiobutton(
                f_rb, text=txt, value=val, variable=self.var_perfil,
                command=self.mudar_perfil, bg="#0c0c14", fg="#ffffff", selectcolor="#1c1c30",
                activebackground="#0c0c14", font=("Segoe UI", 8, "bold")
            )
            rb.pack(side="left")
            tk.Label(f_rb, text=f"- {desc}", font=("Segoe UI", 7), fg="#777799", bg="#0c0c14").pack(side="left", padx=5)

        frame_hw = tk.LabelFrame(
            self.tab_visao, text=" Módulos Avançados (Háptico Flydigi & Overlay In-Game) ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=4
        )
        frame_hw.pack(fill="x", padx=10, pady=4)

        self.var_haptico = tk.BooleanVar(value=self.estado.config.get("feedback_haptico", True))
        cb_hap = tk.Checkbutton(
            frame_hw, text="Ativar Feedback Háptico Vader 4 Pro (Pulsos táteis em xG Alto e Infiltrações)",
            variable=self.var_haptico, command=self.mudar_haptico,
            bg="#0c0c14", fg="#00ff88", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8)
        )
        cb_hap.pack(anchor="w", pady=1)

        self.var_overlay = tk.BooleanVar(value=self.estado.config.get("overlay_ingame", True))
        cb_ovl = tk.Checkbutton(
            frame_hw, text="Exibir HUD Flutuante In-Game Transparente (F11 para Ligar/Desligar)",
            variable=self.var_overlay, command=self.mudar_overlay,
            bg="#0c0c14", fg="#00e5ff", selectcolor="#1c1c30", activebackground="#0c0c14",
            font=("Segoe UI", 8)
        )
        cb_ovl.pack(anchor="w", pady=1)

        frame_keys = tk.LabelFrame(
            self.tab_visao, text=" Atalhos das Ações Táticas da IA (Flydigi Space Station) ",
            bg="#0c0c14", fg="#00ffcc", font=("Segoe UI", 9, "bold"), padx=10, pady=4
        )
        frame_keys.pack(fill="x", padx=10, pady=4)

        self.lbl_tecla_monitor_topo = tk.Label(
            frame_keys, text="🔑 MONITOR DE ENTRADA: Aguardando toque no controle ou teclado...",
            font=("Segoe UI", 9, "bold"), fg="#ffaa00", bg="#141424", pady=4, relief="ridge"
        )
        self.lbl_tecla_monitor_topo.pack(fill="x", pady=(2, 6))

        self.botoes_teclas = {}
        acoes = [
            ("chute_ia", "⚽ Finalização Inteligente xG (X)", "A / LB+A / RB+A / RT+A"),
            ("lancamento_ia", "🎯 Lançamento Tático / Facão (5)", "W / LB+W / RT+W"),
            ("cruzamento_ia", "⚡ Cruzamento Inteligente IA (B)", "D / D+D / LB+D"),
        ]

        for chave, nome, comando_jogo in acoes:
            linha = tk.Frame(frame_keys, bg="#0c0c14")
            linha.pack(fill="x", pady=1)
            tk.Label(linha, text=nome, font=("Segoe UI", 8), fg="#ffffff", bg="#0c0c14", width=30, anchor="w").pack(side="left")
            tk.Label(linha, text=f"-> {comando_jogo}", font=("Segoe UI", 7), fg="#ffaa00", bg="#0c0c14", width=16, anchor="w").pack(side="left")

            tecla_atual = self.estado.config["hotkeys"].get(chave, "?").upper()
            btn = tk.Button(
                linha, text=f"[ {tecla_atual} ]", font=("Consolas", 8, "bold"),
                bg="#1a1a2e", fg="#00ffcc", activebackground="#00ffcc", activeforeground="#000",
                width=8, command=lambda c=chave: self.capturar_tecla(c)
            )
            btn.pack(side="right")
            self.botoes_teclas[chave] = btn

        frame_info = tk.LabelFrame(
            self.tab_visao, text=" Motor Tático V3.0 Elite ",
            bg="#0c0c14", fg="#8888aa", font=("Segoe UI", 8, "bold"), padx=10, pady=3
        )
        frame_info.pack(fill="x", padx=10, pady=3)
        tk.Label(
            frame_info,
            text="• RP2040 1000Hz C++ Nativo | XInput Haptic Rumble Flydigi | HUD In-Game Direct3D.\n• Pre-Aim 18ms + Follow-Through 65ms + Vetor Híbrido adaptativo PA1/PA2/PA3.\n• Botão Y do Controle: Lançamento curto e rasteiro teleguiado no jogador mirado no analógico.",
            bg="#0c0c14", fg="#777799", font=("Segoe UI", 7), justify="left"
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

    def mudar_autofacao(self):
        with self.estado.lock:
            self.estado.config["auto_disparo_facao"] = bool(self.var_autofacao.get())
            self.estado.salvar_config()

    def mudar_desafogo(self):
        with self.estado.lock:
            self.estado.config["modo_desafogo_pressao"] = bool(self.var_desafogo.get())
            self.estado.salvar_config()

    def mudar_finalizacao(self):
        with self.estado.lock:
            self.estado.config["usar_finalizacao_inteligente"] = bool(self.var_chute.get())
            self.estado.salvar_config()

    def mudar_perfil(self):
        with self.estado.lock:
            self.estado.config["perfil_assistencia"] = self.var_perfil.get()
            self.estado.salvar_config()

    def mudar_haptico(self):
        with self.estado.lock:
            self.estado.config["feedback_haptico"] = bool(self.var_haptico.get())
            self.estado.salvar_config()

    def mudar_overlay(self):
        with self.estado.lock:
            self.estado.config["overlay_ingame"] = bool(self.var_overlay.get())
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
            self.overlay.destruir()
            self.root.destroy()
            return

        # Sincroniza estado de overlay se alternado via F11
        cfg_ovl = self.estado.config.get("overlay_ingame", True)
        if self.var_overlay.get() != cfg_ovl:
            self.var_overlay.set(cfg_ovl)
        self.overlay.atualizar()

        cor_str = "VERDE" if self.estado.sou_time_verde else "VERMELHO"
        dir_str = "Direita (->)" if self.estado.atacando_direita else "Esquerda (<-)"
        rp_str = "RP2040 360° Ativo" if self.estado.rp2040_conectado else "DirectX Nativo"
        self.lbl_status.configure(
            text=f"Time: {cor_str} | Ataque: {dir_str} | Modo: {rp_str}"
        )

        ultima = _ultima_tecla[0]
        if ultima:
            hotkeys = self.estado.config.get("hotkeys", {})
            mapeadas = {}
            for k, v in hotkeys.items():
                mapeadas[str(v).lower()] = k
                if str(v).isdigit():
                    mapeadas[f"num {v}"] = k
            acao = mapeadas.get(ultima, "")
            if acao:
                txt_mon = f"🔑 Entrada recebida: [{ultima.upper()}] -> ✅ DISPARA: {acao}"
                cor_mon = "#00ff88"
            else:
                txt_mon = f"🔑 Entrada recebida: [{ultima.upper()}] -> Ativa"
                cor_mon = "#00ffcc"
            self.lbl_tecla_monitor.configure(text=txt_mon, fg=cor_mon)
            if hasattr(self, "lbl_tecla_monitor_topo"):
                self.lbl_tecla_monitor_topo.configure(text=txt_mon, fg=cor_mon)

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
        self.overlay.destruir()
        self.root.destroy()

    def iniciar(self):
        self.root.mainloop()


# ==============================================================================
# 9. PONTO DE ENTRADA PRINCIPAL (MAIN)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print("   ⚽ EFOOTBALL MASTER AI & CONTROLLER HUB - V3.0 ELITE")
    print("   1000Hz C++ RP2040 + XInput Haptic Rumble + HUD In-Game + Perfil PA")
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
