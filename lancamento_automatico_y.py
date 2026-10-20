"""
=============================================================================
 CENTRAL DE IA TÁTICA: LANÇAMENTO TELEGUIADO (Y) + CRUZAMENTO FENOMENAL (RT + B)
=============================================================================
1. LANÇAMENTO EM PROFUNDIDADE (Y / W):
   - Força calculada dinamicamente via Visão Computacional (Radar)
   - Controle: [BOTÃO Y] ou [BOTÃO Z]
   - Teclado: Barra de [ESPAÇO] ou Tecla [Z]

2. CRUZAMENTO FENOMENAL / ESPETACULAR (RT + B / BARRA ROXA):
   - O cruzamento mais apelão e efetivo do eFootball (bola tensa e rápida);
   - A IA mede a distância euclidiana exata no Radar até o centroavante;
   - Aciona RT + B com a força contínua calculada milimetricamente;
   - Controle: Pressione [BOTÃO B / BOLINHA] (ou RT + B)
   - Teclado: Tecla [B] ou Tecla [C]
=============================================================================
"""

import cv2
import numpy as np
import time
import json
import os
from PIL import ImageGrab
import pydirectinput
import keyboard
import pygame

# Elimina delay padrão interno do pydirectinput
pydirectinput.PAUSE = 0.001

from visao_radar_passes import RadarPassesEFootball, CONFIG_PATH, calcular_forca_balistica

TECLA_LANCAMENTO_Y  = 'w'  # Passe em Profundidade (Botão Y / Triângulo)
TECLA_CRUZAMENTO_B  = 'd'  # Cruzamento / Passe Longo (Botão B / Bolinha)
TECLA_SPRINT_RT     = 'e'  # Corrida Acelerada / Modificador Fenomenal (Gatilho RT / R2)
TECLA_LB            = 'r'  # Modificador de Lançamento Aéreo (Botão LB / L1)

class CentralTaticaIA:
    def __init__(self):
        self.processador = RadarPassesEFootball()
        self.ultimo_disparo = 0.0
        self.cooldown_disparo = 0.6  # Segundos de proteção contra repetição acidental
        # Histórico de botões para Borda de Subida (Edge Trigger - Dispara só 1 vez por aperto)
        self.btn_y_anterior = False
        self.btn_b_anterior = False
        self.tecla_y_anterior = False
        self.tecla_b_anterior = False
        self.tecla_c_anterior = False

    def detectar_lado_ataque(self, meus_jogadores, largura_radar):
        if not meus_jogadores:
            return True
        x_medio = np.mean([p[0] for p in meus_jogadores])
        return x_medio < (largura_radar / 2)

    def encontrar_ultima_linha_adversaria(self, adversarios, atacando_para_direita=True):
        """
        Calcula a Linha de Impedimento Oficial (IFAB): penúltimo defensor
        (último homem de linha antes do goleiro adversário).
        """
        if not adversarios:
            return None
        adv_ordenados = sorted(adversarios, key=lambda p: p[0], reverse=atacando_para_direita)
        if len(adv_ordenados) >= 2:
            return adv_ordenados[1][0]
        return adv_ordenados[0][0]

    def analisar_melhor_passe(self, meus_jogadores, adversarios, atacando_direita=True, linha_zaga=None):
        """Retorna o companheiro com melhor posicionamento tático e os dados balísticos para o Lançamento Y."""
        if len(meus_jogadores) < 2:
            return None, {
                "tempo_ms": 180, "forca_barra": 0.50, "dist_metros": 25.0,
                "aereo": False, "rompimento": False, "impedido": False, "speed_kmh": 0.0
            }

        portador = meus_jogadores[0]
        companheiros = meus_jogadores[1:]

        livres, bloqueadas = self.processador.analisar_linhas_de_passe(
            portador, companheiros, adversarios, atacando_direita=atacando_direita, linha_zaga=linha_zaga
        )
        if livres:
            # Filtro Dinâmico: prioriza quem está em condição legal (não impedido)
            livres_legais = [p for p in livres if not p.get("impedido", False)]
            melhor = livres_legais[0] if livres_legais else livres[0]
            alvo = melhor["destino"]
            return alvo, melhor
        elif len(companheiros) > 0:
            comp = companheiros[0]
            dist_px = np.hypot(comp[0] - portador[0], comp[1] - portador[1])
            dist_m = dist_px * 0.42
            forca, tempo_ms = calcular_forca_balistica(dist_m, usar_aereo=False)
            return comp, {
                "destino": comp,
                "destino_futuro": comp,
                "tempo_ms": tempo_ms,
                "forca_barra": forca,
                "dist_metros": dist_m,
                "aereo": False,
                "rompimento": False,
                "impedido": False,
                "speed_kmh": 0.0
            }

        return None, {
            "tempo_ms": 180, "forca_barra": 0.50, "dist_metros": 25.0,
            "aereo": False, "rompimento": False, "impedido": False, "speed_kmh": 0.0
        }

    def calcular_cruzamento_dinamico(self, portador, meus_jogadores, largura_radar, altura_radar, atacando_direita=True):
        """
        Visão Computacional com PONTO FUTURO para Cruzamentos.

        O cruzamento não deve mirar onde o atacante está, mas onde ele VAI ESTAR
        quando a bola chegar à área — igual à física real do futebol.

        PONTO FUTURO DO CRUZAMENTO:
          O atacante está sempre em movimento de entrada na área.
          Estimamos que ele avançará ~22% da distância ao centro do gol
          na direção do ataque antes de a bola chegar.

        PREFERÊNCIA CABEÇA/PEITO:
          - Atacante ENTRANDO na área (em movimento): CABEÇA ou FENOMENAL.
          - Atacante JÁ PARADO no fundo da área (costa ao gol): RASTEIRO.
          - Cruzamento longo (> 36m): FENOMENAL (bola tensa a meia-altura).
          - Cruzamento médio (20-36m): CABEÇA (parábola para a cabeça).
          - Cruzamento curto (< 20m): RASTEIRO (só se atacante estiver parado).
        """
        if len(meus_jogadores) < 2:
            return None, {
                "dist_px": 60.0,
                "dist_metros": 25.0,
                "forca_barra": 0.50,
                "tempo_ms": 160,
                "tipo": "CABEÇA",
                "destino_futuro": None
            }

        companheiros = meus_jogadores[1:]
        centro_y = altura_radar / 2
        gol_x = largura_radar if atacando_direita else 0
        limite_area_x = (largura_radar - 70) if atacando_direita else 70

        candidatos = []
        for c in companheiros:
            cx, cy = c
            avanco = (cx >= portador[0] - 10) if atacando_direita else (cx <= portador[0] + 10)
            na_area = (cx >= limite_area_x) if atacando_direita else (cx <= limite_area_x)

            if avanco or na_area:
                dist_px = np.hypot(cx - portador[0], cy - portador[1])
                dist_centro = abs(cy - centro_y)

                # --- PONTO FUTURO DO CRUZAMENTO ---
                # O atacante vai se mover na direção do gol antes da bola chegar.
                # Estimamos o avanço: ~22% da distância restante até o gol.
                dist_ao_gol_px = abs(gol_x - cx)
                avanco_futuro_px = min(20, dist_ao_gol_px * 0.22)

                # Direção de avanço: em direção ao gol adversário
                direcao_ataque = 1 if atacando_direita else -1
                cx_futuro = cx + direcao_ataque * avanco_futuro_px
                # Tendência ao centro: o atacante tende a entrar pelo centro da área
                cy_futuro = cy + (centro_y - cy) * 0.12

                # Score de prioridade: prefere quem está na área e mais central
                score = dist_px - (30 if na_area else 0) + (dist_centro * 0.35)
                candidatos.append((c, dist_px, score, cx_futuro, cy_futuro))

        if candidatos:
            candidatos.sort(key=lambda item: item[2])
            melhor_alvo, dist_px, _, cx_futuro, cy_futuro = candidatos[0]
        else:
            melhor_alvo = companheiros[0]
            cx, cy = melhor_alvo
            dist_px = np.hypot(cx - portador[0], cy - portador[1])
            dist_ao_gol_px = abs(gol_x - cx)
            avanco_futuro_px = min(20, dist_ao_gol_px * 0.22)
            direcao_ataque = 1 if atacando_direita else -1
            cx_futuro = cx + direcao_ataque * avanco_futuro_px
            cy_futuro = cy + (centro_y - cy) * 0.12

        destino_futuro = (int(cx_futuro), int(cy_futuro))

        # Distância ao ponto FUTURO (é isso que calibra a força da barra)
        dist_futuro_px = np.hypot(cx_futuro - portador[0], cy_futuro - portador[1])
        dist_metros = dist_futuro_px * 0.42

        # SELETOR TÁTICO COM PREFERÊNCIA CABEÇA/PEITO:
        dist_alvo_gol_m = abs(gol_x - cx_futuro) * 0.42

        if dist_metros > 38.0:
            # Longa distância: bola tensa e rápida (Fenomenal RT+B a meia-altura)
            tipo = "FENOMENAL"
        elif dist_alvo_gol_m < 12.0:
            # Atacante já está colado ao gol (sem espaço para parábola): rasteiro embaixo
            tipo = "RASTEIRO"
        else:
            # Posição ideal de área (20-38m): CABEÇA/PEITO — preferência do usuário
            tipo = "CABEÇA"

        # Força calibrada pelo modelo balístico não linear
        usar_aereo_cruz = (tipo in ["CABEÇA", "FENOMENAL"])
        forca_ideal, tempo_ms = calcular_forca_balistica(dist_metros, usar_aereo=usar_aereo_cruz)

        return melhor_alvo, {
            "alvo": melhor_alvo,
            "destino_futuro": destino_futuro,
            "tipo": tipo,
            "dist_px": float(dist_px),
            "dist_metros": float(dist_metros),
            "forca_barra": float(forca_ideal),
            "tempo_ms": int(tempo_ms)
        }

    def disparar_lancamento_y(self, tempo_ms, forca_pct=50, dist_m=25.0, aereo=False, rompimento=False, speed_kmh=0.0):
        """
        Dispara o Lançamento em Profundidade com Calibração Balística:
        - Rompimento / Facão: Infiltração em velocidade nas costas da zaga.
        - Rasteiro (Y): Linha limpa detectada pelo Cone Dinâmico.
        - Aéreo (LB + Y): Linha bloqueada no meio por zagueiro → bola cavada por cima.
        """
        agora = time.time()
        if agora - self.ultimo_disparo < self.cooldown_disparo:
            return False

        self.ultimo_disparo = agora
        tempo_sec = max(0.10, min(0.34, tempo_ms / 1000.0))



        if rompimento:
            tipo_str = f"★ FACÃO / ROMPIMENTO ({speed_kmh:.1f} km/h) ★"
        elif aereo:
            tipo_str = "AÉREO (LB + Y) ⬆️"
        else:
            tipo_str = "RASTEIRO (Y) ➡️"

        print(f"\n[🎯 LANÇAMENTO {tipo_str}] Distância: {dist_m:.1f}m | Barra: {forca_pct}% ({int(tempo_sec*1000)}ms)...")
        try:
            if aereo:
                # LB (L1) antes do Y para fazer a bola cavada / lob
                pydirectinput.keyDown(TECLA_LB)
                time.sleep(0.03)

            pydirectinput.keyDown(TECLA_LANCAMENTO_Y)
            time.sleep(tempo_sec)
            pydirectinput.keyUp(TECLA_LANCAMENTO_Y)

            if aereo:
                time.sleep(0.01)
                pydirectinput.keyUp(TECLA_LB)

            status = "Bola enfiada nas costas da zaga!" if rompimento else ("Bola cavada por cima!" if aereo else "Passe em profundidade executado!")
            print(f"[OK] {status}\n")
            return True
        except Exception as e:
            print(f"[ERRO] {e}")
            return False

    def disparar_cruzamento_inteligente(self, tipo, tempo_ms, forca_pct=50, dist_m=25.0):
        """
        Executa automaticamente o tipo mais letal selecionado pela IA:
        - RASTEIRO: Toque duplo veloz pelo chão da pequena área.
        - CABEÇA: Parábola na cabeça do centroavante na grande área.
        - FENOMENAL: RT + B míssil tenso rasgando a zaga.
        """
        agora = time.time()
        if agora - self.ultimo_disparo < self.cooldown_disparo:
            return False

        self.ultimo_disparo = agora
        tempo_sec = max(0.10, min(0.35, tempo_ms / 1000.0))

        if tipo == "RASTEIRO":

            print(f"\n[👟 IA: CRUZAMENTO RASTEIRO (B+B)!] Distância: {dist_m:.1f}m | Rasgando a pequena área...")
            try:
                pydirectinput.keyDown(TECLA_CRUZAMENTO_B)
                time.sleep(0.04)
                pydirectinput.keyUp(TECLA_CRUZAMENTO_B)
                time.sleep(0.03)
                pydirectinput.keyDown(TECLA_CRUZAMENTO_B)
                time.sleep(max(0.08, tempo_sec * 0.75))
                pydirectinput.keyUp(TECLA_CRUZAMENTO_B)
                print("[GOL!] Bola cortante rasteira na cara do gol!\n")
                return True
            except Exception as e:
                print(f"[ERRO] {e}")
                return False

        elif tipo == "FENOMENAL":

            print(f"\n[⚡ IA: CRUZAMENTO FENOMENAL (RT + B)!] Distância: {dist_m:.1f}m | Barra: {forca_pct}% ({int(tempo_sec*1000)}ms)...")
            try:
                pydirectinput.keyDown(TECLA_SPRINT_RT)
                time.sleep(0.03)
                pydirectinput.keyDown(TECLA_CRUZAMENTO_B)
                time.sleep(tempo_sec)
                pydirectinput.keyUp(TECLA_CRUZAMENTO_B)
                time.sleep(0.02)
                pydirectinput.keyUp(TECLA_SPRINT_RT)
                print("[GOL!] Cruzamento Fenomenal disparado!\n")
                return True
            except Exception as e:
                print(f"[ERRO] {e}")
                return False

        else: # "CABEÇA"

            print(f"\n[⚽ IA: CRUZAMENTO NA CABEÇA (B)!] Distância: {dist_m:.1f}m | Barra: {forca_pct}% ({int(tempo_sec*1000)}ms)...")
            try:
                pydirectinput.keyDown(TECLA_CRUZAMENTO_B)
                time.sleep(tempo_sec)
                pydirectinput.keyUp(TECLA_CRUZAMENTO_B)
                print("[GOL!] Bola colocada na cabeça do centroavante!\n")
                return True
            except Exception as e:
                print(f"[ERRO] {e}")
                return False


def main():
    print("=" * 70)
    print(" CENTRAL DE IA TÁTICA EFOOTBALL: LANÇAMENTO (Y) + CRUZAMENTO FENOMENAL (RT + B)")
    print("=" * 70)

    # Inicializa Pygame Joystick
    pygame.init()
    pygame.joystick.init()
    vader = None
    if pygame.joystick.get_count() > 0:
        vader = pygame.joystick.Joystick(0)
        vader.init()
        print(f"[OK] Controle Vader Conectado: {vader.get_name()}")
    else:
        print("[AVISO] Controle físico não detectado pelo Pygame. Usando modo teclado.")

    print("\nComandos Ativos (Disparo Manual Calibrado por Visão Computacional):")
    print("  -> LANÇAMENTO TELEGUIADO (Y): Barra de [ESPAÇO] ou Botão [Z/Y] no controle")
    print("  -> CRUZAMENTO FENOMENAL (RT + B / BARRA ROXA): Botão [B/Bolinha] no controle ou Tecla [B]/[C]")
    print("\n[PRONTO] Monitorando radar... Pressione 'Q' ou 'ESC' para sair.\n")

    sistema = CentralTaticaIA()
    nome_janela = "IA Radar eFootball - Tatica e Cruzamentos"
    cv2.namedWindow(nome_janela, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(nome_janela, 640, 350)

    while True:
        try:
            pygame.event.pump()

            tela_pil = ImageGrab.grab()
            frame_tela = cv2.cvtColor(np.array(tela_pil), cv2.COLOR_RGB2BGR)

            radar_img = sistema.processador.capturar_radar(frame_tela)
            if radar_img is None or radar_img.size == 0:
                time.sleep(0.04)
                continue

            meus_jogadores, adversarios = sistema.processador.detectar_jogadores(radar_img)
            overlay = radar_img.copy()

            for adv in adversarios:
                cv2.circle(overlay, adv, 4, (0, 0, 255), -1)
            for jog in meus_jogadores:
                cv2.circle(overlay, jog, 4, (0, 255, 0), -1)

            largura_r = overlay.shape[1]
            altura_r = overlay.shape[0]
            atacando_direita = sistema.detectar_lado_ataque(meus_jogadores, largura_r)

            linha_x = sistema.encontrar_ultima_linha_adversaria(adversarios, atacando_para_direita=atacando_direita)
            if linha_x is not None:
                cv2.line(overlay, (linha_x, 0), (linha_x, altura_r), (0, 140, 255), 2)
                cv2.putText(overlay, "ZAGA", (linha_x - 18, 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 140, 255), 1)

            alvo_passe, dados_passe = sistema.analisar_melhor_passe(
                meus_jogadores, adversarios, atacando_direita=atacando_direita, linha_zaga=linha_x
            )
            alvo_cruz, dados_cruz = None, None

            if len(meus_jogadores) > 0:
                portador = meus_jogadores[0]

                # Desenha linha de lançamento tático (Y / LB+Y / Facão)
                if alvo_passe:
                    is_aereo = dados_passe.get('aereo', False)
                    is_rompimento = dados_passe.get('rompimento', False)
                    is_impedido = dados_passe.get('impedido', False)
                    speed_kmh = dados_passe.get('speed_kmh', 0.0)
                    alvo_draw = dados_passe.get('destino_futuro', alvo_passe)
                    p_passe = int(dados_passe['forca_barra'] * 100)

                    if is_impedido:
                        cor_y = (0, 0, 255)       # Vermelho = Impedimento
                        tipo_y = f"[IMPEDIDO!] {p_passe}%"
                    elif is_rompimento:
                        cor_y = (0, 240, 255)     # Amarelo Ouro / Ciano = Rompimento nas costas da zaga
                        tipo_y = f"★ FACÃO {p_passe}% ({dados_passe['dist_metros']:.1f}m)"
                    elif is_aereo:
                        cor_y = (0, 165, 255)     # Laranja = Bola cavada por cima
                        tipo_y = f"LB+Y AEREO {p_passe}% ({dados_passe['dist_metros']:.1f}m)"
                    else:
                        cor_y = (0, 255, 200)     # Verde-água = Rasteiro limpo
                        tipo_y = f"Y RASTEIRO {p_passe}% ({dados_passe['dist_metros']:.1f}m)"

                    # Linha do passe (da bola ao ponto futuro interceptado)
                    cv2.line(overlay, portador, alvo_draw, cor_y, 2)
                    cv2.circle(overlay, alvo_draw, 9, cor_y, 2)

                    # Vetor de corrida instantânea do companheiro (seta em direção ao ponto futuro)
                    if speed_kmh > 4.0:
                        cv2.arrowedLine(overlay, alvo_passe, alvo_draw, (0, 255, 255), 1, tipLength=0.25)

                    if is_rompimento:
                        cv2.circle(overlay, alvo_draw, 14, cor_y, 1)  # Halo duplo para rompimento
                    elif is_aereo:
                        cv2.circle(overlay, alvo_draw, 14, cor_y, 1)  # Halo para aéreo

                    txt_speed = f" | {speed_kmh:.0f}km/h" if speed_kmh > 4.0 else ""
                    cv2.putText(overlay, f"{tipo_y}{txt_speed}",
                                (alvo_draw[0] - 38, alvo_draw[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.38, cor_y, 1)

                # Análise Tática de Cruzamento com PONTO FUTURO (Rasteiro, Cabeça ou Fenomenal)
                alvo_cruz, dados_cruz = sistema.calcular_cruzamento_dinamico(portador, meus_jogadores, largura_r, altura_r, atacando_direita)
                if alvo_cruz:
                    tipo_cruz = dados_cruz["tipo"]
                    p_cruz = int(dados_cruz['forca_barra'] * 100)
                    d_m = dados_cruz['dist_metros']

                    # Ponto futuro: onde o atacante vai estar quando a bola chegar
                    alvo_futuro = dados_cruz.get('destino_futuro', alvo_cruz)

                    if tipo_cruz == "RASTEIRO":
                        cor_cruz = (0, 200, 255)   # Laranja claro (rasteiro = urgência)
                        txt_cruz = f"IA: RASTEIRO B+B ({d_m:.1f}m)"
                    elif tipo_cruz == "FENOMENAL":
                        cor_cruz = (255, 0, 255)   # Magenta/Roxo (bola tensa RT+B)
                        txt_cruz = f"IA: FENOMENAL RT+B {p_cruz}% ({d_m:.1f}m)"
                    else:  # "CABEÇA" — preferência
                        cor_cruz = (0, 255, 128)   # Verde brilhante (cabeça = preferido)
                        txt_cruz = f"IA: CABECA/PEITO {p_cruz}% ({d_m:.1f}m)"

                    # Linha da posição atual ao ponto futuro do atacante
                    cv2.line(overlay, portador, alvo_futuro, cor_cruz, 2)
                    # Marcador na posição ATUAL do atacante (círculo pequeno)
                    cv2.circle(overlay, alvo_cruz, 5, cor_cruz, 1)
                    # Marcador no PONTO FUTURO (onde a bola deve chegar — círculo maior + X)
                    cv2.circle(overlay, alvo_futuro, 9, cor_cruz, 2)
                    cv2.line(overlay, (alvo_futuro[0]-5, alvo_futuro[1]-5),
                                      (alvo_futuro[0]+5, alvo_futuro[1]+5), cor_cruz, 1)
                    cv2.line(overlay, (alvo_futuro[0]+5, alvo_futuro[1]-5),
                                      (alvo_futuro[0]-5, alvo_futuro[1]+5), cor_cruz, 1)
                    cv2.putText(overlay, txt_cruz, (10, 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.44, cor_cruz, 1)

            cv2.putText(overlay, "[ESPACO/Z] Lancar Y | [B/C/6] Cruzamento Inteligente", (10, altura_r - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 255, 0), 1)

            zoom = cv2.resize(overlay, (largura_r * 3, altura_r * 3), interpolation=cv2.INTER_NEAREST)
            cv2.imshow(nome_janela, zoom)

            tecla = cv2.waitKey(20) & 0xFF
            if tecla == ord('q') or tecla == 27:
                break

            # --- Leitura com Borda de Subida (Edge Trigger: Dispara 1 única vez por clique) ---
            # 1. Lançamento Y (Triângulo / Botão Z / Espaço)
            btn_y_atual = vader.get_button(3) if vader else False
            tecla_y_atual = (
                keyboard.is_pressed('5') or 
                keyboard.is_pressed('num 5') or 
                keyboard.is_pressed('z') or 
                keyboard.is_pressed('space')
            )

            disparar_y = False
            if (btn_y_atual and not sistema.btn_y_anterior) or (tecla_y_atual and not sistema.tecla_y_anterior):
                disparar_y = True

            sistema.btn_y_anterior = btn_y_atual
            sistema.tecla_y_anterior = tecla_y_atual

            if disparar_y:
                t_ms = dados_passe["tempo_ms"] if dados_passe else 180
                f_pct = int(dados_passe["forca_barra"] * 100) if dados_passe else 50
                d_m = dados_passe["dist_metros"] if dados_passe else 25.0
                e_aereo = dados_passe.get("aereo", False) if dados_passe else False
                e_romp = dados_passe.get("rompimento", False) if dados_passe else False
                spd = dados_passe.get("speed_kmh", 0.0) if dados_passe else 0.0
                sistema.disparar_lancamento_y(t_ms, forca_pct=f_pct, dist_m=d_m, aereo=e_aereo, rompimento=e_romp, speed_kmh=spd)

            # 2. Cruzamento Inteligente da IA (Botão C do Vader ou tecla C)
            btn_b_atual = False  # Desabilitado no botão B físico para não interferir na marcação/bote
            tecla_b_atual = (
                keyboard.is_pressed('6') or 
                keyboard.is_pressed('num 6') or 
                keyboard.is_pressed('c')
            )

            # NUNCA monitorar a tecla 'd' ou 'e' (chaves da IA) nem a tecla 'b' (Start no eFootball PC)
            disparar_b = False
            if ((btn_b_atual and not sistema.btn_b_anterior) or 
                (tecla_b_atual and not sistema.tecla_b_anterior)):
                disparar_b = True

            sistema.btn_b_anterior = btn_b_atual
            sistema.tecla_b_anterior = tecla_b_atual

            if disparar_b:
                tipo_cruz = dados_cruz["tipo"] if dados_cruz else "CABEÇA"
                t_ms = dados_cruz["tempo_ms"] if dados_cruz else 170
                f_pct = int(dados_cruz["forca_barra"] * 100) if dados_cruz else 55
                d_m = dados_cruz["dist_metros"] if dados_cruz else 25.0
                sistema.disparar_cruzamento_inteligente(tipo_cruz, t_ms, forca_pct=f_pct, dist_m=d_m)

        except Exception as e:
            time.sleep(0.04)

    cv2.destroyAllWindows()
    print("Módulo encerrado.")

if __name__ == "__main__":
    main()
