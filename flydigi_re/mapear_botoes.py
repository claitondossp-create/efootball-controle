"""
=============================================================================
MAPEAMENTO DE BOTOES VIA XINPUT RAW - VADER 4 PRO
=============================================================================
Analisa os pacotes HID brutos XInput para descobrir onde os paddles 
(M1/M2/M3/M4) e botoes extras (C, Z) estao no relatorio de bytes.

Fica em modo de escuta: aperte cada botao uma vez e solte.
O script detecta mudancas entre pacotes e mostra QUAIS BITS MUDARAM.

Uso: python mapear_botoes.py
=============================================================================
"""

import hid
import time

VADER_VID = 0x045E
VADER_PID = 0x028E


def bits_diferentes(a: bytes, b: bytes) -> list:
    """Retorna lista de (byte_idx, bit_mask, old_val, new_val) que mudaram."""
    diffs = []
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            xor = a[i] ^ b[i]
            for bit in range(8):
                mask = 1 << bit
                if xor & mask:
                    diffs.append((i, mask, bool(a[i] & mask), bool(b[i] & mask)))
    return diffs


def abrir_vader():
    dev = hid.device()
    dev.open(VADER_VID, VADER_PID)
    dev.set_nonblocking(0)
    return dev


def bit_num(mask: int) -> int:
    for i in range(8):
        if mask == (1 << i):
            return i
    return -1


if __name__ == "__main__":
    print("=" * 60)
    print(" MAPEAMENTO DE BOTOES - Flydigi Vader 4 Pro (XInput RAW)")
    print("=" * 60)
    print("Aperte cada botao EXTRA do controle (M1, M2, M3, M4, C, Z)")
    print("O script mostrara qual byte/bit muda em cada pressionamento.")
    print("Pressione Ctrl+C para encerrar.\n")

    try:
        dev = abrir_vader()
        print("[OK] Vader 4 Pro conectado!\n")
    except Exception as e:
        print(f"[ERRO] Nao foi possivel conectar: {e}")
        exit(1)

    # Le pacote inicial como referencia
    anterior = bytes(dev.read(64))
    print(f"Pacote base: {anterior.hex()}\n")
    print("Aguardando pressionamento de botoes...\n")

    evento_num = 0

    try:
        while True:
            atual = bytes(dev.read(64))
            diffs = bits_diferentes(anterior, atual)

            if diffs:
                evento_num += 1
                hora = time.strftime('%H:%M:%S.') + str(int(time.time() * 1000) % 1000).zfill(3)
                print(f"[EVENTO #{evento_num}] {hora}")
                for byte_idx, mask, era, agora in diffs:
                    acao = "PRESSIONADO" if agora else "SOLTO     "
                    print(f"  Byte[{byte_idx:2d}] bit 0x{mask:02X} (bit {bit_num(mask)}) -> {acao}")
                    print(f"    Byte completo: antes={hex(anterior[byte_idx])} depois={hex(atual[byte_idx])}")

                print(f"  RAW completo: {atual.hex()}\n")
                anterior = atual

    except KeyboardInterrupt:
        print("\n[INFO] Mapeamento encerrado.")
        dev.close()

    print("\n=== RESUMO DO MAPEAMENTO ===")
    print("Use os dados acima para identificar byte/bit de cada botao extra.")

