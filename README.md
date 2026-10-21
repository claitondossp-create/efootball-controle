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

### 2. ⚡ Central Inteligente de Cruzamentos (1ª Trave, 2ª Trave, Meia-Lua)
- Analisa a movimentação dos atacantes e o posicionamento dos zagueiros:
  - **RASTEIRO (D + D duplo toque veloz)**: Atacante colado à pequena área ou entrada da área sem bloqueio na trajetória.
  - **CABEÇA / PEITO (D com parábola)**: Bola colocada no tempo certo para finalização aérea na 1ª ou 2ª trave.
  - **BALÃO ALTO (LB + D / Q + D)**: Encobre a cabeça da zaga no segundo pau quando há zagueiro cortando a trajetória.
  - **ANTECIPADO (LB + D)**: Cruzamento antes da linha de fundo nas costas dos laterais.
  - **FENOMENAL (RT + D / Barra Roxa)**: Cruzamento tenso e rápido de longa distância (> 44m) em campo aberto.
- **Monitoramento Defensivo 360° dos Zagueiros**:
  - Distância de marcação individual de cada recebedor. Se a 1ª trave estiver marcada (< 3.8m), a IA vira automaticamente para a 2ª trave livre.
  - Bloqueio frontal no cruzador: anula cruzamento rasteiro para a bola não bater na canela da zaga.
  - Bloqueio de trajetória: força cruzamento por cobertura (`LB + D`).

### 3. 🛡️ Segurança Competitiva e Mapeamento Limpo
- **Zero conflito de teclas nativas**: Hotkeys configuradas nas teclas neutras `5` e `6`, que o eFootball não utiliza, evitando qualquer ativação acidental de corrida nativa.
- **Detecção com Borda de Subida (Edge Trigger) & Anti-Stuck**: Leitura em nível de kernel via `GetAsyncKeyState`, garantindo que teclas nunca fiquem presas.
- **Suporte Total a Mandante e Visitante**: Regra IFAB oficial simétrica com tecla `F10` para alternar e salvar o time (Verde / Vermelho).

---

## 🎮 Mapeamento de Comandos

| Comando | Controle (Flydigi Vader 4 Pro) | Teclado | Ação Realizada |
| :--- | :--- | :--- | :--- |
| **Lançamento IA** | Botão **Z** | Tecla `5` | Lançamento balístico teleguiado (Rasteiro, Cavado em arco LB+Y ou Trivela RT+Y) |
| **Cruzamento IA** | Botão **C** | Tecla `6` | Seleciona automaticamente o melhor setor (1ª/2ª trave) e o tipo ideal de cruzamento |
| **Inverter Time** | Teclado / Macro | Tecla `F10` | Alterna entre Mandante (Verde) e Visitante (Vermelho) com salvamento automático |
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

3. Execute a central de IA unificada:
   ```powershell
   python efootball_mestre.py
   ```

4. Uma janela OpenCV com zoom 3x do radar exibirá o rastreamento tático, linha de impedimento e alvos em tempo real. Pressione `Q` ou `ESC` para encerrar.

---

## 📁 Estrutura do Repositório

```text
├── efootball_mestre.py    # Sistema completo: Visão Computacional, IA balística, injeção DirectX e RP2040
├── config_visao.json      # Configurações de ROI do radar, hotkeys e time
├── firmware/              # Firmware CircuitPython UF2 para Raspberry Pi Pico RP2040 (1000Hz)
├── requirements.txt       # Dependências Python
└── README.md              # Documentação completa
```

---

## ⚖️ Licença e Uso
Desenvolvido para fins de pesquisa, estudo de Visão Computacional aplicada a jogos e engenharia de periféricos de entrada.
