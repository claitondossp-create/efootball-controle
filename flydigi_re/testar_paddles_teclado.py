import keyboard
import time

print("=" * 60)
print(" TESTE DE PADDLES FLYDIGI (Detecção via Teclado / Space Station)")
print("=" * 60)
print("Aperte qualquer tecla ou paddle do Flydigi no controle...")
print("Pressione ESC para sair.\n")

def on_key_event(e):
    if e.event_type == 'down':
        print(f"[PRESSIONADO] Tecla: '{e.name}' | ScanCode: {e.scan_code}")

keyboard.hook(on_key_event)

try:
    keyboard.wait('esc')
except KeyboardInterrupt:
    pass

print("\nTeste finalizado.")
