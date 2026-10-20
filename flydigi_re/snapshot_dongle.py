"""
COMPARADOR DE INTERFACES HID - CABO vs DONGLE
Execute com cabo conectado, depois desconecte e conecte o dongle 2.4G.
O script detecta automaticamente as interfaces NOVAS que aparecerem.
"""
import hid, time, json, os

def tirar_snapshot():
    devs = {}
    for d in hid.enumerate():
        key = f"{d['vendor_id']}:{d['product_id']}:{d.get('usage_page',0)}:{d.get('interface_number',-1)}"
        devs[key] = {
            "vendor_id": d["vendor_id"],
            "product_id": d["product_id"],
            "vid_hex": hex(d["vendor_id"]),
            "pid_hex": hex(d["product_id"]),
            "name": d.get("product_string", ""),
            "manufacturer": d.get("manufacturer_string", ""),
            "usage_page": d.get("usage_page", 0),
            "usage": d.get("usage", 0),
            "interface": d.get("interface_number", -1),
            "path": str(d.get("path", b"")),
        }
    return devs

# --- PASSO 1: Snapshot com cabo ---
print("=" * 60)
print(" COMPARADOR CABO vs DONGLE - Flydigi Vader 4 Pro")
print("=" * 60)
print("\nPASSO 1: Controle conectado via CABO USB")
print("Tirando snapshot dos dispositivos atuais...")
snap_cabo = tirar_snapshot()

save_path = os.path.join(os.path.dirname(__file__), "snapshot_cabo.json")
with open(save_path, "w", encoding="utf-8") as f:
    json.dump(snap_cabo, f, indent=2, ensure_ascii=False)

print(f"[OK] {len(snap_cabo)} dispositivos registrados.")
print("\nDispositivos atuais:")
for key, info in snap_cabo.items():
    if info["name"]:
        print(f"  {info['vid_hex']}:{info['pid_hex']} | {info['name']} | UsagePage={hex(info['usage_page'])} | IF={info['interface']}")

# --- PASSO 2: Aguardar troca para dongle ---
print("\n" + "=" * 60)
print("\nAGORA:")
print("  1. DESCONECTE o cabo USB do controle")
print("  2. Plugue o DONGLE 2.4G no PC")
print("  3. Ligue o controle")
print("\nO script vai detectar automaticamente as novas interfaces...")
print("=" * 60 + "\n")

snap_anterior = snap_cabo.copy()
snap_dongle = None
aguardando = True

while aguardando:
    time.sleep(0.5)
    snap_atual = tirar_snapshot()
    
    novos = {k: v for k, v in snap_atual.items() if k not in snap_anterior}
    removidos = {k: v for k, v in snap_anterior.items() if k not in snap_atual}
    
    if novos or removidos:
        print(f"[MUDANCA DETECTADA em {time.strftime('%H:%M:%S')}]")
        
        if removidos:
            print("  REMOVIDOS (desconectados):")
            for k, v in removidos.items():
                print(f"    {v['vid_hex']}:{v['pid_hex']} | {v['name']}")
        
        if novos:
            print("  NOVOS (conectados):")
            for k, v in novos.items():
                print(f"    VID={v['vid_hex']} PID={v['pid_hex']} | {v['name']} | UsagePage={hex(v['usage_page'])} | IF={v['interface']}")
                if v["vendor_id"] == 0x37D7:
                    print(f"    *** INTERFACE PROPRIETARIA FLYDIGI ENCONTRADA! ***")
                    print(f"    *** PID={v['pid_hex']} - Este e o canal dos botoes extras! ***")
        
        snap_anterior = snap_atual
        
        # Verifica se o dongle ja foi totalmente detectado (espera estabilizar)
        time.sleep(1.5)
        snap_estavel = tirar_snapshot()
        if snap_estavel == snap_anterior:
            snap_dongle = snap_estavel
            print("\n[ESTAVEL] Dongle detectado e estabilizado!\n")
            aguardando = False

# --- PASSO 3: Analise comparativa ---
if snap_dongle:
    save_path2 = os.path.join(os.path.dirname(__file__), "snapshot_dongle.json")
    with open(save_path2, "w", encoding="utf-8") as f:
        json.dump(snap_dongle, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print(" RESULTADO FINAL - Interfaces do DONGLE 2.4G")
    print("=" * 60)
    
    novos_final = {k: v for k, v in snap_dongle.items() if k not in snap_cabo}
    
    print(f"\nInterfaces NOVAS (so aparecem com o dongle): {len(novos_final)}")
    for k, v in novos_final.items():
        print(f"\n  VID={v['vid_hex']} PID={v['pid_hex']}")
        print(f"  Nome      : {v['name']}")
        print(f"  Fabricante: {v['manufacturer']}")
        print(f"  Usage Page: {hex(v['usage_page'])}")
        print(f"  Interface : {v['interface']}")
        print(f"  Path      : {v['path']}")
        
        if v["vendor_id"] == 0x37D7:
            print(f"\n  *** CANAL PROPRIETARIO FLYDIGI CONFIRMADO! ***")
            print(f"  *** Use este VID/PID no firmware_bridge.py para ler M1-M4 ***")
        elif v.get("usage_page") == 0xFFA0:
            print(f"\n  *** Usage Page 0xFFA0 = Interface de config Flydigi! ***")
    
    print(f"\nSnapshots salvos em flydigi_re/")
