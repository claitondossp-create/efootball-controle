"""
=============================================================================
SCAN COMPLETO DO VADER 4 PRO - DESCOBRE TODAS AS INTERFACES HID
=============================================================================
Execute este script com o controle conectado para:
1. Listar TODAS as interfaces HID do Vader 4 Pro
2. Identificar qual interface e a proprietaria Flydigi (canal de config)
3. Tentar abrir cada interface e ler pacotes brutos
4. Confirmar o PID exato e o mapa de bytes no Windows

Uso: python scan_vader.py
=============================================================================
"""

import hid
import time
import sys

MAGIC = b"\x5a\xa5"

# Nomes que identificam o Vader
VADER_NAMES = ["vader", "flydigi"]

# VIDs conhecidos do Flydigi
FLYDIGI_VIDS = {
    0x37D7: "Flydigi (nativo - Vader 5 / interfaces extras)",
    0x045E: "Microsoft XInput (modo Xbox - Vader 4 padrao)",
}


def encontrar_vader():
    """Retorna lista de todos os dispositivos HID relacionados ao Vader."""
    dispositivos = []
    for d in hid.enumerate():
        nome = d.get("product_string", "").lower()
        fab  = d.get("manufacturer_string", "").lower()
        vid  = d["vendor_id"]
        e_vader = any(t in nome or t in fab for t in VADER_NAMES) or vid in FLYDIGI_VIDS
        if e_vader:
            dispositivos.append(d)
    return dispositivos


def mostrar_info(d):
    vid = d["vendor_id"]
    pid = d["product_id"]
    tipo = FLYDIGI_VIDS.get(vid, f"VID desconhecido ({hex(vid)})")
    print(f"  VID={hex(vid)}  PID={hex(pid)}")
    print(f"  Nome     : {d.get('product_string', 'N/A')}")
    print(f"  Fabricante: {d.get('manufacturer_string', 'N/A')}")
    print(f"  Usage Page: {hex(d.get('usage_page', 0))}")
    print(f"  Usage     : {hex(d.get('usage', 0))}")
    print(f"  Interface : {d.get('interface_number', -1)}")
    print(f"  Tipo      : {tipo}")


def tentar_ler(d, segundos=3):
    """Tenta abrir o dispositivo e ler pacotes brutos por N segundos."""
    vid = d["vendor_id"]
    pid = d["product_id"]
    path = d.get("path")
    print(f"\n  [LENDO] Tentando abrir VID={hex(vid)} PID={hex(pid)}...")

    try:
        dev = hid.device()
        dev.open_path(path)
        dev.set_nonblocking(1)
    except Exception as e:
        print(f"  [ERRO] Nao foi possivel abrir: {e}")
        return

    pacotes_recebidos = 0
    tem_magic = False
    inicio = time.time()

    print(f"  [OK] Aberto! Lendo por {segundos}s...")

    # Envia handshake para tentar ativar streaming
    try:
        HANDSHAKE = [
            bytes([0x5A, 0xA5, 0x01, 0x02, 0x03, 0x00, 0x00, 0x00,
                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        ]
        for pkt in HANDSHAKE:
            dev.write(b"\x00" + pkt)  # Report ID 0 antes
    except Exception:
        pass

    while time.time() - inicio < segundos:
        try:
            data = bytes(dev.read(64, timeout_ms=50))
        except Exception:
            break
        if data:
            pacotes_recebidos += 1
            if data[:2] == MAGIC or (len(data) > 1 and data[1:3] == MAGIC):
                tem_magic = True
                print(f"  [MAGIC 5AA5!] Pacote #{pacotes_recebidos}: {data[:16].hex()} ...")
            elif pacotes_recebidos <= 3:
                print(f"  [RAW] Pacote #{pacotes_recebidos}: {data[:16].hex()} ...")

    print(f"  Total recebido: {pacotes_recebidos} pacotes | Magic 5AA5: {'SIM!' if tem_magic else 'Nao'}")
    dev.close()


if __name__ == "__main__":
    print("=" * 60)
    print(" SCAN DO FLYDIGI VADER 4 PRO - Todas as interfaces HID")
    print("=" * 60)
    print("Certifique que o controle esta conectado (cabo ou dongle).\n")

    dispositivos = encontrar_vader()

    if not dispositivos:
        print("[AVISO] Nenhum dispositivo Vader/Flydigi encontrado!")
        print("Todos os HID encontrados:")
        for d in hid.enumerate():
            nome = d.get("product_string", "")
            if nome:
                print(f"  VID={hex(d['vendor_id'])} PID={hex(d['product_id'])} | {nome}")
        sys.exit(1)

    print(f"Encontrado(s): {len(dispositivos)} interface(s) do Vader\n")
    for i, d in enumerate(dispositivos):
        print(f"--- Interface #{i+1} ---")
        mostrar_info(d)

    print("\n" + "=" * 60)
    print(" TENTANDO LER PACOTES BRUTOS DE CADA INTERFACE")
    print("=" * 60)

    for i, d in enumerate(dispositivos):
        print(f"\n[Interface #{i+1}: {d.get('product_string','')} UsagePage={hex(d.get('usage_page',0))}]")
        tentar_ler(d, segundos=2)

    print("\n[CONCLUSAO]")
    print("Se encontrou pacotes com magic 5AA5: essa e a interface proprietaria!")
    print("Anote o VID/PID/UsagePage dela para o modulo flydigi_direct.py")
