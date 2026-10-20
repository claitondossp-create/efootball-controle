# ⚽ eFootball Tactical AI & Controller Hub

Sistema avançado de assistência tática em tempo real para **eFootball (PC)** combinando **Visão Computacional (OpenCV)**, **Modelagem Cinemática & Balística**, e integração de hardware de alta performance (**Flydigi Vader 4 Pro**).

---

## 🌟 Principais Funcionalidades

### 1. 🎯 Lançamento em Profundidade Teleguiado (Y / W)
- **Rastreamento Cinemático com Filtro EMA ($\alpha=0.65$)**: Mede o vetor de velocidade real $\vec{v} = (\Delta x / \Delta t, \Delta y / \Delta t)$ de cada companheiro em sprint, convertendo em km/h no HUD.
- **Interceptação Quadrática (Bhaskara)**: Resolve analiticamente a equação de encontro da bola com o atleta:
  $$A(t^*)^2 + B t^* + C = 0$$
  Antecipa corridas em diagonal (**facão**) e sprints pela ponta, mirando onde o jogador **vai estar**.
- **Curva Balística Não Linear com Atrito do Gramado**:
  $$\text{dist\_norm} = \text{clamp}\left(\frac{\text{dist\_metros} - 6.0}{52.0 - 6.0}, 0.0, 1.0\right)$$
  $$\text{forca\_barra} = 0.20 + 0.76 \times (\text{dist\_norm})^{0.86}$$
  $$\text{tempo\_ms} = \text{int}(95.0 + \text{forca\_barra} \times 250.0)$$
  Elimina passes curtos fracos que morrem no caminho e evita que bolas longas estourem para fora.
- **Filtro Anti-Impedimento Dinâmico (Regra Oficial IFAB)**:
  - Localiza a linha do penúltimo defensor adversário.
  - Penaliza severamente jogadores adiantados (`-60.0` no score tático, alerta vermelho `[IMPEDIDO!]`).
  - Bonifica com pontuação máxima o atacante que parte de trás em posição legal e rompe a zaga (`+35.0`, destaque dourado `★ FACÃO`).
- **Cone Dinâmico & Seletor Rasteiro vs. Aéreo**:
  - Alargamento dinâmico da margem de bloqueio conforme a distância do defensor.
  - Alternância automática para passe cavado por cima (**LB + Y**) quando há zagueiro bloqueando a linha rasteira.

### 2. ⚡ Central Inteligente de Cruzamentos (RT + B)
- Analisa a movimentação dos atacantes dentro e na entrada da grande área:
  - **RASTEIRO (B + B duplo toque veloz)**: Atacante colado à pequena área para corte seco.
  - **CABEÇA / PEITO (B com parábola)**: Bola colocada no tempo certo para finalização aérea.
  - **FENOMENAL (RT + B / Barra Roxa)**: Cruzamento tenso e rápido de longa distância (> 36m).

### 3. 🛡️ Segurança Competitiva e Mapeamento Limpo
- **Zero interferência na defesa**: Botão B físico do controle mantido livre para botes e desarme manual.
- **Zero auto-switching defensivo**: Nenhum cursor indesejado durante a marcação.
- **Detecção com Borda de Subida (Edge Trigger)**: Dispara rigorosamente 1 única vez por acionamento.
- **Zero latência de áudio**: Execução silenciosa e instantânea sem delays de som.

---

## 🎮 Mapeamento de Comandos

| Comando | Controle (Flydigi Vader 4 Pro) | Teclado | Ação Realizada |
| :--- | :--- | :--- | :--- |
| **Lançamento Y** | Botão **Z** ou Botão **Y** | `Espaço` / `Z` / `Numpad 5` | Lançamento com força balística calculada milimetricamente |
| **Cruzamento IA** | Botão **C** | Tecla `C` / `Numpad 6` | Seleciona automaticamente Rasteiro, Cabeça ou Fenomenal |
| **Desarme / Bote** | Botão **B** | Padrão do jogo | Ação defensiva normal do usuário sem interferência |

---

## 🚀 Instalação e Execução

### Requisitos:
- Python 3.10+ (Windows 10/11)
- eFootball (PC / Steam) configurado em **1080p (Janela em Tela Cheia)**
- Cores do radar no jogo: **Mandante = Verde**, **Visitante = Vermelho**

### Passo a Passo:
1. Clone o repositório:
   ```powershell
   git clone https://github.com/claitondossp-create/efootball-controle.git
   cd efootball-controle
   ```

2. Instale as dependências:
   ```powershell
   pip install -r requirements.txt
   ```

3. Execute a central de IA:
   ```powershell
   python lancamento_automatico_y.py
   ```

4. Uma janela OpenCV com zoom 3x do radar exibirá o rastreamento tático, linha de impedimento e alvos em tempo real. Pressione `Q` ou `ESC` para encerrar.

---

## 📁 Estrutura do Repositório

```text
├── lancamento_automatico_y.py   # Script principal: interface Pygame, triggers e injeção
├── visao_radar_passes.py         # Módulo OpenCV: rastreamento cinemático, Bhaskara e cone dinâmico
├── firmware_bridge.py            # Ponte serial / RP2040 para automações em nível de hardware
├── flydigi_re/                   # Scripts de engenharia reversa do protocolo Flydigi Vader 4 Pro
├── firmware/                     # Firmware CircuitPython UF2
├── requirements.txt              # Dependências Python
└── README.md                     # Documentação completa
```

---

## ⚖️ Licença e Uso
Desenvolvido para fins de pesquisa, estudo de Visão Computacional aplicada a jogos e engenharia de periféricos de entrada.
