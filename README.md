# ⚽ eFootball Tactical AI & Controller Hub (V2.1)

Sistema avançado de assistência tática em tempo real para **eFootball (PC)** combinando **Visão Computacional a 60 FPS (MSS + OpenCV)**, **Modelagem Cinemática & Balística Anisotrópica ($105\text{m} \times 68\text{m}$)**, e integração de hardware de ultra-baixa latência (**Flydigi Vader 4 Pro + RP2040 Bridge a 1000Hz**).

---

## 🌟 Principais Funcionalidades (V2.1)

### 1. 🎯 Lançamento em Profundidade Teleguiado 360° (`Y` / `W`)
- **Escala Anisotrópica Oficial FIFA/IFAB ($105\text{m} \times 68\text{m}$)**: Converte independentemente os eixos horizontal e vertical do radar para metros reais, eliminando distorções angulares em viradas de jogo e passes diagonais.
- **Rastreamento Cinemático Global ($\alpha=0.60$) & Desaglutinação por Distance Transform**:
  - Associação global por menor distância preditiva (*Global Nearest Neighbor*), impedindo que jogadores que se cruzam troquem de ID.
  - Subdivisão morfológica com `cv2.distanceTransform` para isolar de 2 a 6 atletas aglutinados na pequena área em escanteios.
- **Interceptação Quadrática de Bhaskara em 2 Estágios**:
  - Resolve analiticamente $A(t^*)^2 + B t^* + C = 0$ usando a velocidade específica da modalidade escolhida (`RASTEIRO`, `CAVADO_ARCO` ou `FENOMENAL_CURVA`), garantindo que o vetor direcional 360° aponte exatamente para o ponto futuro de encontro.
- **Curva Balística Não Linear com Atrito do Gramado**:
  $$\text{dist\_norm} = \text{clamp}\left(\frac{\text{dist\_metros} - 5.0}{58.0 - 5.0}, 0.0, 1.0\right)$$
  $$\text{forca\_barra} = 0.18 + 0.78 \times (\text{dist\_norm})^{0.85}$$
  $$\text{tempo\_ms} = \text{int}(90.0 + \text{forca\_barra} \times 255.0)$$
- **Ponderação de Alinhamento Corporal (Contra-Pé) & Modo Desafogo Rápido**:
  - Memoriza a última orientação corporal do portador da bola, bonificando passes a favor do movimento (`+15.0`) e penalizando giros cegos de 180° (`-20.0`).
  - **Quick-Release (< 1.9m)**: Quando pressionado de perto por um marcador, cancela animações longas (`RT`) e reduz o tempo de barra do passe rasteiro em 18% para soltar a bola antes do desarme.
- **Filtro Anti-Impedimento Oficial IFAB (Lei 11)**:
  - Respeita a linha de meio-campo e compensa automaticamente a oclusão do goleiro sobre a linha de fundo do radar.

### 2. ⚡ Central Inteligente de Cruzamentos (1ª Trave, 2ª Trave, Meia-Lua)
- Analisa a movimentação dos atacantes na área e o posicionamento dos zagueiros:
  - **RASTEIRO (`D + D` duplo toque sincronizado)**: Atacante livre próximo à pequena área ou infiltrando na meia-lua.
  - **CABEÇA / PEITO (`D` com parábola)**: Bola colocada na 1ª ou 2ª trave.
  - **BALÃO ALTO / ANTECIPADO (`LB + D` / `Q + D`)**: Encobre o primeiro zagueiro quando o corredor rasteiro está bloqueado.
  - **FENOMENAL (`RT + D` / `E + D`)**: Cruzamento tenso e rápido de longa distância (> 34m) sem bloqueio frontal.

### 3. ⚙️ Máquina de Estados Não-Bloqueante a 1000Hz (`timeBeginPeriod(1)`)
- **Zero Freeze do Controle**: Nenhuma ação usa `time.sleep` bloqueante na thread de input. Todos os eventos de teclado DirectX (`SendInput` 64-bit) e bits da ponte serial RP2040 são chaveados bit-a-bit por timestamps de alta precisão (`time.perf_counter()`).

---

## 🎮 Mapeamento de Comandos

| Comando | Controle (Flydigi Vader 4 Pro) | Teclado | Ação Realizada |
| :--- | :--- | :--- | :--- |
| **Lançamento IA** | Botão **Z** | Tecla `5` | Lançamento balístico teleguiado 360° (`W`, `LB+W` ou `RT+W`) |
| **Cruzamento IA** | Botão **C** | Tecla `6` | Cruzamento tático setorial 1ª/2ª trave (`D`, `D+D`, `LB+D` ou `RT+D`) |
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

3. Uma janela OpenCV com zoom 3x do radar exibirá o rastreamento tático, linha de impedimento e alvos em tempo real. Pressione `Q` ou `ESC` para encerrar.

---

## 📁 Estrutura do Repositório

```text
├── efootball_mestre.py    # Sistema completo V2.1: Visão Computacional, IA balística, injeção DirectX e RP2040
├── config_visao.json      # Configurações de ROI do radar, hotkeys e time
├── firmware/              # Firmware CircuitPython UF2 para Raspberry Pi Pico RP2040 (1000Hz)
├── requirements.txt       # Dependências Python
└── README.md              # Documentação completa
```
