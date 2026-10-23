# ⚽ eFootball Master AI & Controller Hub (V3.3 Elite Dual-Mode)

Sistema integrado de assistência tática em tempo real para **eFootball (PC — Steam / Microsoft Store)** combinando **Visão Computacional a 60 FPS (MSS + OpenCV)**, **Cinemática Dupla Anisotrópica ($105\text{m} \times 68\text{m}$)**, **Motor de Reposição Defensiva & Sombra Anti-Tabela (1-2)**, **Expected Goals (xG)** e leitura direta de hardware **Flydigi Vader 4 Pro (Dongle 2.4GHz + Cabo USB Hot-Plug a 1000Hz)** + **RP2040 Bridge**.

---

## 🌟 Principais Funcionalidades da Versão V3.3 Elite

### 1. 🛡️ Motor de Reposição Defensiva & Marcação Anti-Tabela (1-2)
- **Rastreamento Cinemático Duplo (`kinematic_tracker_adv`)**: Calcula em tempo real o vetor de velocidade $(v_x, v_y)$ em metros por segundo de todos os atacantes adversários e mantém histórico de $1.85\text{s}$ dos portadores da bola rivais para identificar tabelas (*Pass & Run* / 1-2).
- **Geometria de Sombra de Cobertura (*Cover Shadow* via Bhaskara)**:
  - Quando um adversário toca a bola e dispara em profundidade ($v_{\text{ataque}} \ge 2.1\text{ m/s}$), o sistema resolve a equação quadrática de interceptação para localizar o ponto futuro de devolução ($P_{\text{dev}}$).
  - Posiciona o seu marcador no Ponto de Sombra ($P_{\text{sombra}}$) sobre a bissetriz do passe (entre $38\%$ e $75\%$ da trajetória, com margem Goal-Side de $0.9\text{m}$), mudando o indicador visual para `SOMBRA OK!` assim que o corredor da tabela está fechado ($\le 1.45\text{m}$).
- **Recomposição em Funil Defensivo (Goal-Side)**:
  - Se o seu defensor estiver batido atrás da linha da bola, projeta uma diagonal de retorno acelerado (`RT`) $5.0\text{m}$ à frente do portador rival, puxando $25\%$ para o eixo central para proteger a entrada da área.
- **Override Manual Suave (Blend $70\%$ Mão / $30\%$ IA)**:
  - Se você segurar o gatilho de defesa mas empurrar fortemente o analógico físico ($> 78\%$) em direção divergente para dar um bote manual, o sistema cede prioridade imediata à sua mão.

---

### 2. ⚡ Acesso Direto Dual-Mode ao Flydigi Vader 4 Pro (Dongle 2.4GHz + Cabo USB)
- **Leitura `XInputGetState` em 5 Microssegundos (1000Hz Real)**: Lê diretamente os analógicos Hall Effect em 16-bit (-32768 a +32767, zona morta de $3.5\%$) e os gatilhos LT/RT em 8-bit (0 a 255) sem passar pela fila de eventos SDL.
- **Transição Hot-Plug Automática (Dongle $\leftrightarrow$ Cabo)**: Monitora os VIDs `0x04B4` e `0x37D7` e varre automaticamente os slots XInput 0..3 caso você conecte ou desconecte o cabo USB durante a partida.
- **Gatilho LT de 2 Estágios**:
  - **Estágio 1 (LT entre $20\%$ e $70\%$)**: Contenção manual livre (*Match-up*).
  - **Estágio 2 (LT $\ge 72\%$ ou trava Micro-Switch traseira)**: Ativa a guiagem automática 360° para a Sombra da Tabela 1-2 ou Funil de Recomposição.
- **Leitura Nativa dos 6 Botões Extras (C, Z, M1, M2, M3, M4)**: Suporte via canal secundário `hidapi` (Raw HID) e fallback de teclas do Flydigi Space Station.

---

### 3. 🎯 Lançamento Balístico 360° (PA1/PA2 vs PA3/Manual) & Finalização xG
- **Isolamento Puro RP2040**: Quando a placa RP2040 está conectada, os disparos usam 100% os botões e eixos do gamepad virtual (sem enviar teclas DirectX simultâneas), impedindo que a engine do eFootball perca o ângulo 360° da mira.
- **Histerese Anti-Flicker de Posse (4 frames / ~65ms) & Inércia da Bola**: Mantém a estabilidade do estado de ataque/defesa mesmo quando a bola sofre oclusão sob ícones de jogadores no radar.

---

## 🎮 Tabela de Comandos e Gatilhos Táticos

| Ação Tática | Botão Nativo Vader 4 Pro | Teclado / Controle Padrão | Comportamento no Jogo |
| :--- | :--- | :--- | :--- |
| **Finalização Inteligente xG** | Botão Frontal **C** | Tecla `4` ou Botão **X** (no ataque) | Mira 360° no canto descoberto do goleiro (`X`, `LB+X`, `RB+X` ou `RT+X`). |
| **Lançamento Tático / Facão** | Botão Traseiro **M1** | Tecla `5` ou `LB + Y` | Passe em profundidade teleguiado 360° com Bhaskara (`Y`, `LB+Y` ou `RT+Y`). |
| **Passe Curto Mirado** | Botão **Y** Simples | Botão **Y** (sem LB) | Lançamento curto e rasteiro ($115\text{ms}$–$170\text{ms}$) no companheiro apontado pelo analógico. |
| **Cruzamento Inteligente IA** | Botão Frontal **Z** | Tecla `6` ou Botão **B** (na área) | Cruzamento setorial 1ª/2ª trave ou meia-lua (`D`, `D+D`, `LB+D` ou `RT+D`). |
| **Reposição & Sombra 1-2** | Botão Traseiro **M2** | Tecla `7` ou `LT` Fundo ($\ge 72\%$) | Guia o marcador para fechar a tabela 1-2 (`SOMBRA_TABELA`) ou recompor o funil (`RT/LT`). |
| **Troca de Cursor Anti-Tabela** | Botão Traseiro **M3** | Automático (opcional na GUI) | Pulso direcionado em `LB` apontando para o zagueiro que cobre o corredor da tabela. |
| **Inverter Cor do Time** | Macro / Teclado | Tecla `F10` | Alterna entre Mandante (VERDE) e Visitante (VERMELHO) e salva no JSON. |
| **Ocultar / Exibir HUD** | Macro / Teclado | Tecla `F11` | Liga ou desliga o Overlay Flutuante transparente in-game. |

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
