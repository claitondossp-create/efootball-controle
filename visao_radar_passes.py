"""
=============================================================================
 MÓDULO DE VISÃO COMPUTACIONAL: RADAR E ASSISTÊNCIA DE PASSES
=============================================================================
Analisa o radar (minimapa) do eFootball em tempo real com OpenCV:
1. Localiza os jogadores do seu time e os adversários no radar.
2. Calcula as linhas de passe limpas (sem interceptação de defensores).
3. Calcula a distância e o ângulo em 360° para o companheiro melhor posicionado.
4. Calcula a força milimétrica exata da barra de passe.
=============================================================================
"""

import cv2
import numpy as np
import time
import os
import json

CONFIG_PATH = "d:/Efootball controle/config_visao.json"

# Coordenadas padrão do Radar para 1920x1080 (centro inferior)
RADAR_ROI_PADRAO = {
    "top": 890,
    "left": 830,
    "width": 260,
    "height": 130
}

class KinematicPlayerTracker:
    """
    Rastreador Cinemático com Filtro Exponencial Móvel (EMA).
    Calcula vetores de velocidade instantânea v = (vx, vy) em pixels/segundo
    para prever a trajetória de sprint e corridas em facão.
    """
    def __init__(self, alpha=0.65, max_match_dist=25.0):
        self.alpha = alpha
        self.max_match_dist = max_match_dist
        self.tracks = {}  # tid -> {'pos': (x, y), 'vel': (vx, vy), 'lost': 0}
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

        # Casamento guloso por proximidade euclidiana
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
                # Trava física: limita velocidade a ~19 m/s (45 px/s) para evitar saltos irreais
                if speed > 45.0:
                    scale = 45.0 / speed
                    vx_raw *= scale
                    vy_raw *= scale

                # Banda morta contra micro-ruído de contorno (< 2.5 px/s parado)
                if speed < 2.5:
                    vx_raw, vy_raw = 0.0, 0.0

                # Suavização EMA
                vx_smooth = self.alpha * vx_raw + (1.0 - self.alpha) * track['vel'][0]
                vy_smooth = self.alpha * vy_raw + (1.0 - self.alpha) * track['vel'][1]

                self.tracks[tid] = {
                    'pos': pt,
                    'vel': (vx_smooth, vy_smooth),
                    'lost': 0
                }
                matched_velocities[pt] = (vx_smooth, vy_smooth)
            else:
                track['lost'] += 1
                if track['lost'] > 4:
                    del self.tracks[tid]

        # Novos pontos detectados
        for pt in unmatched_dets:
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = {
                'pos': pt,
                'vel': (0.0, 0.0),
                'lost': 0
            }
            matched_velocities[pt] = (0.0, 0.0)

        return matched_velocities

def calcular_intersecao_cinematica(pos_passador, pos_alvo, vel_alvo, v_bola=115.0):
    """
    Resolve a interceptação cinemática quadrática (Bhaskara) para antecipar
    o ponto exato onde a bola encontrará o jogador em corrida (sprint / facão).

    Equação do Encontro: |R_0 + v * t - P_0|^2 = (v_bola * t)^2
    => A*t^2 + B*t + C = 0
    """
    bx, by = pos_passador
    ax, ay = pos_alvo
    vax, vay = vel_alvo

    dx = ax - bx
    dy = ay - by

    speed_sq = vax**2 + vay**2
    A = speed_sq - (v_bola**2)
    B = 2.0 * (dx * vax + dy * vay)
    C = dx**2 + dy**2

    disc = B**2 - 4.0 * A * C

    if disc < 0 or abs(A) < 1e-5:
        t_voo = np.hypot(dx, dy) / v_bola
    else:
        sqrt_disc = np.sqrt(disc)
        t1 = (-B - sqrt_disc) / (2.0 * A)
        t2 = (-B + sqrt_disc) / (2.0 * A)
        
        candidatos_t = [t for t in (t1, t2) if t > 0.05]
        if candidatos_t:
            t_voo = min(candidatos_t)
        else:
            t_voo = np.hypot(dx, dy) / v_bola

    t_voo = max(0.10, min(1.15, t_voo))
    px_int = int(ax + vax * t_voo)
    py_int = int(ay + vay * t_voo)
    p_intersecao = (px_int, py_int)

    dist_px = np.hypot(p_intersecao[0] - bx, p_intersecao[1] - by)
    dist_m = dist_px * 0.42

    return t_voo, p_intersecao, dist_px, dist_m

def calcular_forca_balistica(dist_metros, usar_aereo=False):
    """
    Modelo Balístico Não Linear com Resistência ao Rolamento do Gramado:
    - Curva sublinear com expoente 0.86 compensa desaceleração por atrito.
    - Barra % calibrada milimetricamente para o buffer de teclado/controle do eFootball.
    """
    dist_norm = np.clip((dist_metros - 6.0) / (52.0 - 6.0), 0.0, 1.0)
    forca_barra = 0.20 + 0.76 * (dist_norm ** 0.86)
    
    if usar_aereo:
        forca_barra = min(0.98, forca_barra * 1.08 + 0.04)
    else:
        forca_barra = min(0.96, max(0.20, forca_barra))

    tempo_ms = int(95.0 + forca_barra * 250.0)
    return float(forca_barra), int(tempo_ms)

def avaliar_penetracao_impedimento(pos_atual, pos_futuro, linha_impedimento, atacando_direita=True):
    """
    Filtro Anti-Impedimento Dinâmico e Pontuação de Infiltração:
    - Penaliza severamente jogadores que já estão adiantados (em banheira).
    - Bonifica ao máximo quem parte de trás (posição legal) e rompe a zaga no ponto futuro.
    """
    if linha_impedimento is None:
        return False, False, 0.0

    ax, _ = pos_atual
    fx, _ = pos_futuro

    if atacando_direita:
        ja_impedido = ax > (linha_impedimento + 1.0)
        rompimento = (ax <= (linha_impedimento + 1.0)) and (fx > linha_impedimento)
    else:
        ja_impedido = ax < (linha_impedimento - 1.0)
        rompimento = (ax >= (linha_impedimento - 1.0)) and (fx < linha_impedimento)

    score_delta = 0.0
    if ja_impedido:
        score_delta -= 60.0  # Penalidade severa por impedimento
    elif rompimento:
        score_delta += 35.0  # Bônus máximo por rompimento da zaga em posição legal

    return ja_impedido, rompimento, score_delta

class RadarPassesEFootball:
    def __init__(self):
        self.roi = RADAR_ROI_PADRAO
        self.carregar_config()
        self.portador_pos = None          # posição do anel amarelo no radar
        self.bola_pos = None              # posição da bola branca no radar
        self.adversario_com_bola = False  # True quando adversário tem a posse
        self.tracker = KinematicPlayerTracker(alpha=0.65)
        self.velocidades = {}             # pos -> (vx, vy)

    def carregar_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "roi_radar" in cfg:
                        self.roi = cfg["roi_radar"]
            except Exception:
                pass

    def capturar_radar(self, frame_tela):
        """Recorta a região do radar a partir do frame da tela cheia."""
        top = self.roi["top"]
        left = self.roi["left"]
        w = self.roi["width"]
        h = self.roi["height"]
        return frame_tela[top:top+h, left:left+w]

    def radar_visivel(self, img_radar):
        """
        Verifica se o minimapa está REALMENTE visível e mostrando o jogo.

        O radar do eFootball tem fundo escuro (quase preto) com pontos coloridos.
        Critérios para considerar o radar ativo:
          1. Há pixels verdes (nosso time) suficientes → mínimo 3 jogadores detectáveis
          2. Há pixels vermelhos (adversário) suficientes → mínimo 3 adversários
          3. A imagem NÃO é majoritariamente preta ou branca (menu/replay/loading)

        Se o radar estiver escondido/em menu → retorna False e TODAS as funções são pausadas.
        """
        if img_radar is None or img_radar.size == 0:
            return False

        hsv = cv2.cvtColor(img_radar, cv2.COLOR_BGR2HSV)

        # Conta pixels verdes (nosso time)
        mask_verde = cv2.inRange(hsv, np.array([46, 85, 85]), np.array([80, 255, 255]))
        pixels_verdes = cv2.countNonZero(mask_verde)

        # Conta pixels vermelhos / rosas (adversário)
        mask_verm1 = cv2.inRange(hsv, np.array([0, 70, 70]), np.array([12, 255, 255]))
        mask_verm2 = cv2.inRange(hsv, np.array([145, 70, 70]), np.array([180, 255, 255]))
        pixels_vermelhos = cv2.countNonZero(mask_verm1 | mask_verm2)

        # Verifica luminosidade média (radar muito brilhante = menu/loading)
        brilho_medio = np.mean(img_radar)

        # Radar válido: tem verde E vermelho suficientes E não está em tela de loading
        radar_ok = (pixels_verdes >= 8 and       # pelo menos ~2-3 jogadores verdes
                    pixels_vermelhos >= 8 and    # pelo menos ~2-3 adversários
                    brilho_medio < 160)          # fundo escuro (não é menu/replay)

        return radar_ok

    def detectar_jogadores(self, img_radar):
        """
        Segmenta os jogadores no radar com filtro de circularidade rigoroso:
        - Portador da bola: Anel Dourado/Amarelo
        - Time Mandante: Pontos Verdes Circulares
        - Time Visitante: Pontos Vermelhos Circulares
        """
        hsv = cv2.cvtColor(img_radar, cv2.COLOR_BGR2HSV)

        # 1. Detecta o anel amarelo/dourado do portador da bola
        lower_amarelo = np.array([20, 150, 150])
        upper_amarelo = np.array([35, 255, 255])
        mask_amarelo = cv2.inRange(hsv, lower_amarelo, upper_amarelo)

        # 2. Máscara para o seu time (VERDE LIMA - Hue 46..80 exclui o gramado Hue 35..44)
        lower_verde = np.array([46, 85, 85])
        upper_verde = np.array([80, 255, 255])
        mask_verde = cv2.inRange(hsv, lower_verde, upper_verde)

        # 3. Máscara para o adversário (VERMELHO / MAGENTA / ROSA)
        lower_vermelho1 = np.array([0, 70, 70])
        upper_vermelho1 = np.array([12, 255, 255])
        lower_vermelho2 = np.array([145, 70, 70])
        upper_vermelho2 = np.array([180, 255, 255])
        mask_vermelho = cv2.inRange(hsv, lower_vermelho1, upper_vermelho1) | cv2.inRange(hsv, lower_vermelho2, upper_vermelho2)

        # 4. Máscara para a BOLA (ponto branco brilhante no radar)
        # Saturação baixa e brilho alto, excluindo verde, vermelho e amarelo
        mask_jogadores = mask_amarelo | mask_verde | mask_vermelho
        lower_branco = np.array([0, 0, 190])
        upper_branco = np.array([180, 60, 255])
        mask_branco = cv2.inRange(hsv, lower_branco, upper_branco)
        # Remove jogadores da máscara de branco para isolar a bola e linhas do campo
        mask_bola_cand = cv2.bitwise_and(mask_branco, cv2.bitwise_not(mask_jogadores))

        def extrair_pontos_circulares(mask):
            contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            pontos = []
            for c in contornos:
                area = cv2.contourArea(c)
                perimetro = cv2.arcLength(c, True)
                if perimetro == 0:
                    continue
                # Circularidade = 4 * pi * Area / Perimetro^2 (círculo perfeito = ~1.0)
                circularidade = 4 * np.pi * (area / (perimetro * perimetro))
                if 4 < area < 85 and circularidade > 0.45:
                    M = cv2.moments(c)
                    if M["m00"] != 0:
                        pontos.append((int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])))
            return pontos

        portador_pos = None
        contornos_amarelo, _ = cv2.findContours(mask_amarelo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contornos_amarelo:
            if 10 < cv2.contourArea(c) < 300:
                M = cv2.moments(c)
                if M["m00"] != 0:
                    portador_pos = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                    break

        # Detecta a bola branca
        bola_pos = None
        contornos_bola, _ = cv2.findContours(mask_bola_cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidatos_bola = []
        for c in contornos_bola:
            area = cv2.contourArea(c)
            if 1 <= area <= 45:
                bx, by, bw, bh = cv2.boundingRect(c)
                aspecto = float(bw) / (bh + 1e-5)
                if 0.35 <= aspecto <= 2.8:  # Não é linha comprida de campo
                    M = cv2.moments(c)
                    if M["m00"] != 0:
                        pt = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        candidatos_bola.append((pt, area))

        if candidatos_bola:
            # Bola é geralmente o ponto compacto mais nítido
            candidatos_bola.sort(key=lambda x: x[1], reverse=True)
            bola_pos = candidatos_bola[0][0]

        meus_jogadores = extrair_pontos_circulares(mask_verde)
        adversarios = extrair_pontos_circulares(mask_vermelho)

        self.portador_pos = portador_pos
        self.bola_pos = bola_pos

        # Determinação precisa da POSSE (Ataque vs Defesa):
        # 1. Se a bola branca foi localizada, quem está mais próximo dela tem a posse
        if bola_pos:
            dist_verde_bola = min(
                (np.hypot(j[0]-bola_pos[0], j[1]-bola_pos[1]) for j in meus_jogadores),
                default=9999
            )
            dist_adv_bola = min(
                (np.hypot(a[0]-bola_pos[0], a[1]-bola_pos[1]) for a in adversarios),
                default=9999
            )

            if dist_adv_bola < dist_verde_bola and dist_adv_bola < 28:
                self.adversario_com_bola = True
            elif dist_verde_bola < dist_adv_bola and dist_verde_bola < 28:
                self.adversario_com_bola = False
        else:
            # 2. Se a bola estiver temporariamente encoberta:
            # Se o cursor do usuário (anel amarelo) está muito longe dos nossos atacantes
            # e colado na nossa defesa, ou sem anel, mantém consistência
            pass

        # Ordena a lista colocando quem está com a bola na posição [0]
        if self.adversario_com_bola and adversarios:
            ponto_ref = bola_pos if bola_pos else (portador_pos if portador_pos else None)
            if ponto_ref:
                adversarios.sort(key=lambda p: np.hypot(p[0]-ponto_ref[0], p[1]-ponto_ref[1]))
        elif meus_jogadores:
            ponto_ref = bola_pos if bola_pos else (portador_pos if portador_pos else None)
            if ponto_ref:
                meus_jogadores.sort(key=lambda p: np.hypot(p[0]-ponto_ref[0], p[1]-ponto_ref[1]))

        # Atualiza rastreamento cinemático dos companheiros
        self.velocidades = self.tracker.update(meus_jogadores)

        return meus_jogadores, adversarios

    def analisar_linhas_de_passe(self, portador_bola, companheiros, adversarios, atacando_direita=True, linha_zaga=None):
        """
        Análise Tática Balística & Cinemática Avançada de Lançamento (Y):
        
        1. VETOR DE VELOCIDADE REAL E INTERCEPTAÇÃO QUADRÁTICA (Bhaskara):
           Rastreia a corrida instantânea do jogador (v = dp/dt). Em vez de projetar
           cegamente na reta da bola, antecipa a corrida diagonal (facão) resolvendo
           o encontro da bola com o atleta.
        
        2. CONE DINÂMICO DE INTERCEPTAÇÃO:
           Testa a trajetória entre a bola e o ponto futuro interceptado. Margem se
           alarga realisticamente com a distância do defensor à bola.
        
        3. CURVA BALÍSTICA NÃO LINEAR (Atrito da Grama):
           Substitui proporção linear por desaceleração real do gramado, calibrando
           a barra de força % e tempo de aperto (ms) no PC.
        
        4. FILTRO ANTI-IMPEDIMENTO DINÂMICO & PONTUAÇÃO DE INFILTRAÇÃO:
           Penaliza severamente atacantes em impedimento e pontua com bônus máximo
           o atacante em posição legal que rompe as costas da linha defensiva.
        """
        linhas_livres = []
        linhas_bloqueadas = []

        bx, by = portador_bola
        w_radar = self.roi.get("width", 260)
        h_radar = self.roi.get("height", 130)

        # Parâmetros do Cone Dinâmico
        RAIO_BASE = 8.0          # Margem mínima próxima à bola (pixels)
        COEF_ALARGAMENTO = 0.10  # Alargamento do cone por pixel de distância do adv à bola

        for comp in companheiros:
            cx, cy = comp
            distancia = np.hypot(cx - bx, cy - by)
            if distancia < 10:
                continue

            angulo = np.arctan2(cy - by, cx - bx)

            # 1. Vetor de Velocidade Instantânea e Ponto Futuro Cinemático (Bhaskara)
            vel = self.velocidades.get(comp, (0.0, 0.0))
            vx, vy = vel
            speed = np.hypot(vx, vy)
            speed_kmh = speed * 0.42 * 3.6

            if speed >= 3.0:
                # Jogador em movimento / sprint: resolve encontro quadrático
                t_voo, p_int, dist_futura, dist_metros = calcular_intersecao_cinematica(
                    (bx, by), (cx, cy), (vx, vy), v_bola=115.0
                )
                cx_futuro, cy_futuro = p_int
            else:
                # Jogador parado: avanço natural na passada em direção ao ataque
                dir_x = 1.0 if atacando_direita else -1.0
                avanco_px = min(9.0, max(2.5, distancia * 0.10))
                cx_futuro = int(cx + dir_x * avanco_px)
                cy_futuro = cy
                dist_futura = np.hypot(cx_futuro - bx, cy_futuro - by)
                dist_metros = dist_futura * 0.42

            # Trava dentro dos limites físicos do radar
            cx_futuro = int(max(4, min(w_radar - 4, cx_futuro)))
            cy_futuro = int(max(4, min(h_radar - 4, cy_futuro)))
            dist_futura = float(np.hypot(cx_futuro - bx, cy_futuro - by))
            dist_metros = float(dist_futura * 0.42)

            # 2. Cone Dinâmico de Bloqueio (testando a linha até o ponto futuro interceptado)
            bloqueado_rasteiro = False
            bloqueio_mais_proximo = None
            dist_bloqueio_min = float('inf')

            for adv in adversarios:
                ax, ay = adv
                dist_adv_bola = np.hypot(ax - bx, ay - by)

                margem_cone = RAIO_BASE + dist_adv_bola * COEF_ALARGAMENTO

                d_linha = np.abs(
                    (cy_futuro - by) * ax - (cx_futuro - bx) * ay
                    + cx_futuro * by - cy_futuro * bx
                ) / (dist_futura + 1e-5)

                projecao = (
                    (ax - bx) * (cx_futuro - bx) + (ay - by) * (cy_futuro - by)
                ) / (dist_futura**2 + 1e-5)

                if 0.05 < projecao < 0.92 and d_linha < margem_cone:
                    bloqueado_rasteiro = True
                    if dist_adv_bola < dist_bloqueio_min:
                        dist_bloqueio_min = dist_adv_bola
                        bloqueio_mais_proximo = adv
                    break

            # Seletor Rasteiro vs. Aéreo (LB+Y):
            # Se defensor está no primeiro terço/meio do caminho, bola cavada passa por cima
            usar_aereo = False
            if bloqueado_rasteiro and bloqueio_mais_proximo is not None:
                ax_bl, ay_bl = bloqueio_mais_proximo
                projecao_bl = (
                    (ax_bl - bx) * (cx_futuro - bx) + (ay_bl - by) * (cy_futuro - by)
                ) / (dist_futura**2 + 1e-5)
                if projecao_bl < 0.75:
                    usar_aereo = True

            # 3. Força Balística Não Linear com Atrito da Grama
            forca_ideal, tempo_ms = calcular_forca_balistica(dist_metros, usar_aereo=usar_aereo)

            # 4. Avaliação de Impedimento e Rompimento de Linha
            ja_impedido, rompimento, bonus_zaga = avaliar_penetracao_impedimento(
                comp, (cx_futuro, cy_futuro), linha_zaga, atacando_direita=atacando_direita
            )

            # Pontuação Tática Holística:
            # - Ganho de território na direção do gol
            progresso_x = (cx_futuro - bx) if atacando_direita else (bx - cx_futuro)
            progresso_m = progresso_x * 0.42
            score_tatico = progresso_m * 1.5

            # - Bônus de passe rasteiro livre (mais rápido e seguro que aéreo)
            score_tatico += 20.0 if not usar_aereo else 8.0

            # - Bônus/Penalidade de Linha Defensiva
            score_tatico += bonus_zaga

            # - Bônus de velocidade do atacante na direção do ataque (embalado)
            vx_ataque = vx if atacando_direita else -vx
            if vx_ataque > 3.0:
                score_tatico += min(15.0, vx_ataque * 0.5)

            # - Penalidade de proximidade de defensores no destino
            dist_adv_alvo = min((np.hypot(adv[0] - cx_futuro, adv[1] - cy_futuro) for adv in adversarios), default=999.0)
            if dist_adv_alvo < 14.0:
                score_tatico -= 12.0

            info_passe = {
                "destino": comp,
                "destino_futuro": (int(cx_futuro), int(cy_futuro)),
                "vel": (float(vx), float(vy)),
                "speed_kmh": float(speed_kmh),
                "distancia": float(distancia),
                "dist_futura": float(dist_futura),
                "dist_metros": float(dist_metros),
                "angulo_rad": float(angulo),
                "angulo_graus": float(np.degrees(angulo)),
                "forca_barra": float(forca_ideal),
                "tempo_ms": int(tempo_ms),
                "aereo": usar_aereo,
                "impedido": ja_impedido,
                "rompimento": rompimento,
                "score_tatico": float(score_tatico),
            }

            if bloqueado_rasteiro and not usar_aereo:
                linhas_bloqueadas.append(info_passe)
            else:
                linhas_livres.append(info_passe)

        # Ordena as linhas livres pelo Score Tático (maior pontuação = melhor passe)
        linhas_livres.sort(key=lambda p: p["score_tatico"], reverse=True)
        linhas_bloqueadas.sort(key=lambda p: p["distancia"])

        return linhas_livres, linhas_bloqueadas