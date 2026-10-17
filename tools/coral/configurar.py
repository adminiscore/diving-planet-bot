"""Activa Coral en este ordenador: `python tools/coral/configurar.py <gadea|alvaro|gonzalo>`.

Lee tu token del VPS de PRE por SSH (la misma clave que usan las medidas, `~/.ssh/dp_pre_vps`) y lo guarda en
`.env.coral`, en la raíz del repo (está en .gitignore). Así nadie se pasa claves por chat. No imprime el token.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cliente  # noqa: E402

from scripts.pre_access import pre_ssh  # noqa: E402

ENV_REMOTO = "/opt/coral-hub/.env"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    persona = sys.argv[1].strip().lower()
    r = pre_ssh(f"cat {ENV_REMOTO}", timeout=30)
    if r.returncode != 0:
        print(f"No pude leer {ENV_REMOTO} en el VPS: {r.stderr.strip()[:200]}")
        return 1
    tokens = {}
    for linea in r.stdout.splitlines():
        if linea.startswith("CORAL_TOKENS="):
            for par in linea.split("=", 1)[1].split(","):
                nombre, _, tok = par.partition(":")
                tokens[nombre.strip()] = tok.strip()
    if persona not in tokens:
        print(f"'{persona}' no tiene token en Coral. Hay: {', '.join(sorted(tokens))}")
        return 1
    cliente.FICHERO.write_text(
        "# Coral (chat entre los Claude del equipo). No subir a git.\n"
        f"CORAL_URL={cliente.URL_POR_DEFECTO}\nCORAL_PERSONA={persona}\nCORAL_TOKEN={tokens[persona]}\n",
        encoding="utf-8")
    yo = cliente.llamar("GET", "/api/yo")["persona"]
    print(f"Coral listo: eres {yo}. Guardado en {cliente.FICHERO}.")
    print("Reinicia Claude Code y acepta el servidor MCP 'coral' cuando lo pregunte.")
    print(f"El chat en el navegador: {cliente.URL_POR_DEFECTO}/ (pega el CORAL_TOKEN de ese fichero).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
