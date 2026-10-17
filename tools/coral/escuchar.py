"""Escucha de Coral para la herramienta Monitor de Claude Code: una línea por cada mensaje nuevo para ti.

La arma Claude al empezar la sesión (se lo pide el hook de inicio) y entrega cada mensaje en cuanto llega:
pide la bandeja esperando hasta 25 s (long-poll) y la marca como vista. Monitor corta a los 30 min, así que a los
29 se despide con una línea que le recuerda a Claude volver a armarla.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cliente  # noqa: E402

DURACION = 29 * 60


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not cliente.configurado():
        print("[coral] no está configurado en este ordenador: python tools/coral/configurar.py <tu nombre>",
              flush=True)
        return
    fin = time.monotonic() + DURACION
    fallos = 0
    while time.monotonic() < fin:
        try:
            for m in cliente.llamar("GET", "/api/bandeja?esperar=25&marcar=true", timeout=40):
                print("[coral] " + cliente.linea_mensaje(m), flush=True)
            if fallos >= 3:
                print("[coral] conexión recuperada", flush=True)
            fallos = 0
        except cliente.CoralError as e:
            fallos += 1
            if fallos == 3:
                print(f"[coral] sin conexión, sigo intentándolo: {e}", flush=True)
            time.sleep(min(60, 5 * fallos))
    print("[coral] la escucha caduca: vuelve a armarla con el mismo comando", flush=True)


if __name__ == "__main__":
    main()
