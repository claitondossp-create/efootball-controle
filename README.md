# ⚽ eFootball Tactical AI & Controller Hub (V2.2 xG)

Sistema avançado de assistência tática em tempo real para **eFootball (PC)** combinando **Visão Computacional a 60 FPS (MSS + OpenCV)**, **Modelagem Cinemática & Balística Anisotrópica ($105\text{m} \times 68\text{m}$)**, **Motor de Expected Goals (xG)** e integração de hardware de ultra-baixa latência (**Flydigi Vader 4 Pro + RP2040 Bridge a 1000Hz**).

---

## 🌟 Principais Funcionalidades (V2.2)

### 1. ⚽ Finalização Inteligente Baseada em Expected Goals (xG)
- **Modelo Estatístico de xG Logístico em Tempo Real**:
  $$\text{xG} = \frac{1}{1 + e^{-z}} \times 100\%$$
  $$z = 2.45 \cdot \theta - 0.082 \cdot d_{\text{gol}} - 0.40 \cdot N_{\text{bloqueio}} + 0.90 \cdot \left(\frac{\delta_{\text{gk}}}{3.0}\right) - 0.25$$
  - $\theta$: Ângulo de visão aberto para a baliza (radianos).
  - $d_{\text{gol}}$: Distância euclidiana eu e o centro do gol (escala real 105m x 68m).
  - $N_{\text{bloqueio}}$: Zagueiros interceptando a linha do chute (cone com largura de bloqueio de 1.85m).
  - $\delta_{\text{gk}}$: Adiantamento do goleiro além da linha de fundo.
- **Mira 360° no Canto Descoberto (Contra-Pé do Goleiro)**:
  - Baliza oficial IFAB ($7.32$m) com margem de segurança interna de $1.1$m das traves.
  - Detecta o quadrante do goleiro e projeta o vetor analógico 360° no poste descoberto.
- **Seleção Dinâmica de Modalidade de Chute**:
  - **Cavadinha (`LB + X` / `Q + A`)**: Quando o goleiro sai da linha ($\ge 3.8$m) em distâncias entre 6m e 22m ($135$ms a $175$ms).
  - **Chute Colocado (`RB + X` / `C + A`)**: Em ângulo aberto com offset diagonal ($\ge 3.5$m) entre 12m e 24m ($160$ms a $210$ms).
  - **Chute Fenomenal / Stunner (`RT + X` / `E + A`)**: Com corredor limpo à frente ($\ge 2.4$m) de média distância entre 20m e 32m ($225$ms a $265$ms).
  - **Rasteiro Seco (`X` / `A`)**: Cara a cara na grande área ou sob pressão imediata de zagueiros ($110$ms a $145$ms).
- **Curva de Barra Calibrada com Hard Cap Anti-Isolada**:
  - Teto rígido em $265$ms de carregamento, garantindo que a bola nunca passe por cima do travessão.
- **Gatilho Inteligente Duplo**:
  - **Gamepad**: Disparado pelo botão **X** nativo do controle quando no ataque ($d \le 36$m) com posse de bola. Na defesa ou meio-campo sem posse, o botão **X** opera nativamente para divididas e desarmes manuais.
  - **Teclado**: Disparado pela hotkey configurável (padrão Tecla `4`).

---

### 2. 🎯 Lançamento em Profundidade Teleguiado 360° (`Y` / `W`)
- **Escala Anisotrópica Oficial FIFA/IFAB ($105\text{m} \times 68\text{m}$)**: Converte independentemente os eixos horizontal e vertical do radar para metros reais, eliminando distorções angulares em viradas de jogo e passes diagonais.
- **Rastreamento Cinemático Global ($\alpha=0.60$) & Desaglutinação por Distance Transform**:
  - Associação global por menor distância preditiva (*Global Nearest Neighbor*), impedindo que jogadores troquem de ID ao se cruzarem.
  - Subdivisão morfológica com `cv2.distanceTransform` para isolar de 2 a 6 atletas aglutinados na pequena área em escanteios.
- **Interceptação Quadrática de Bhaskara em 2 Estágios**:
  - Resolve analiticamente $A(t^*)^2 + B t^* + C = 0$ usando a velocidade balística específica de cada tipo de passe (`RASTEIRO`, `CAVADO_ARCO` ou `FENOMENAL_CURVA`).
- **Ponderação de Alinhamento Corporal (Contra-Pé) & Modo Desafogo Rápido**:
  - Memoriza a última orientação corporal do portador da bola, bonificando passes a favor do movimento (`+15.0`) e penalizando giros cegos de 180° (`-20.0`).
  - **Quick-Release (< 1.9m)**: Quando pressionado de perto por um marcador, cancela animações longas (`RT`) e solta o passe rapidamente antes do desarme.
- **Filtro Anti-Impedimento Oficial IFAB (Lei 11)**:
  - Respeita a linha de meio-campo e compensa automaticamente a oclusão do goleiro sobre a linha de fundo do radar.

---

### 3. ⚡ Central Inteligente de Cruzamentos (1ª Trave, 2ª Trave, Meia-Lua)
- Analisa a movimentação dos atacantes na área e o posicionamento dos defensores:
  - **RASTEIRO (`D + D` duplo toque sincronizado)**: Atacante livre próximo à pequena área ou infiltrando na meia-lua.
  - **CABEÇA / PEITO (`D` com parábola)**: Bola colocada na 1ª ou 2ª trave.
  - **BALÃO ALTO / ANTECIPADO (`LB + D` / `Q + D`)**: Encobre o primeiro zagueiro quando o corredor rasteiro está bloqueado.
  - **FENOMENAL (`RT + D` / `E + D`)**: Cruzamento tenso e rápido de longa distância (> 34m) sem bloqueio frontal.

---

### 4. ⚙️ Máquina de Estados Não-Bloqueante a 1000Hz (`timeBeginPeriod(1)`)
- **Zero Freeze do Controle**: Nenhuma ação usa `time.sleep` bloqueante na thread de input. Todos os eventos de teclado DirectX (`SendInput` 64-bit) e bits da ponte serial RP2040 são chaveados bit-a-bit por timestamps de alta precisão (`time.perf_counter()`).
- **Máscara Anti-Bleedthrough**: Durante a execução assíncrona, a IA mascara a leitura dos botões físicos no gamepad para evitar que botões mantidos pressionados manualmente vazem após a liberação da barra.

---

## 🎮 Mapeamento de Comandos

| Comando | Controle (Flydigi Vader 4 Pro) | Teclado | Ação Realizada |
| :--- | :--- | :--- | :--- |
| **Finalização xG IA** | Botão **X** (No Ataque com Posse) | Tecla `4` | Mira 360° no canto descoberto com xG (`A`, `LB+A`, `RB+A` ou `RT+A`) |
| **Lançamento IA** | Botão **Z** (Macro Space Station) | Tecla `5` | Lançamento balístico teleguiado 360° (`W`, `LB+W` ou `RT+W`) |
| **Cruzamento IA** | Botão **C** (Macro Space Station) | Tecla `6` | Cruzamento tático setorial 1ª/2ª trave (`D`, `D+D`, `LB+D` ou `RT+D`) |
| **Inverter Time** | Teclado / Macro | Tecla `F10` | Alterna entre Mandante (Verde) e Visitante (Vermelho) e salva no JSON |

---

## 🚀 Instalação e Execução

1. Instale as dependências:
   ```powershell
   pip install -r requirements.txt
   ```

2. Execute a central unificada:
   ```powershell
   python efootball_mestre.py
   ```

3. Uma janela OpenCV com zoom 3x do radar exibirá o rastreamento tático, alvos de passe, cone de bloqueio e finalização xG em tempo real. Pressione `ESC` para encerrar.

---

## 📁 Estrutura do Repositório

```text
├── efootball_mestre.py    # Sistema completo V2.2: Visão Computacional, xG, balística, injeção DirectX e RP2040
├── config_visao.json      # Configurações de ROI do radar, hotkeys e toggles
├── firmware/              # Firmware CircuitPython UF2 para Raspberry Pi Pico RP2040 (1000Hz)
├── requirements.txt       # Dependências Python
└── README.md              # Documentação completa
```
