"""Mete la copia de datos (data/plan-coral.json) dentro de plan-coral.html.

La pagina publicada pinta primero esa copia (nunca sale vacia) y luego la sustituye por los
datos en vivo. Tras exportar la base de datos de la pagina a `data/plan-coral.json` (se lo
pides a Claude: "exporta la base de datos de Plan Coral"), ejecuta:

    python docs/tracking/embed_backup.py

y republica `plan-coral.html` en la MISMA URL (ver README).
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PAGE = HERE / "plan-coral.html"
DATA = HERE / "data" / "plan-coral.json"
BLOCK = re.compile(r'(<script type="application/json" id="backup-data">)(.*?)(</script>)', re.S)


def embed(page_html: str, data: dict) -> str:
    # "</" dentro de un <script> lo cerraria antes de tiempo: se escapa como "<\/".
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new, count = BLOCK.subn(lambda m: m.group(1) + payload + m.group(3), page_html)
    if count != 1:
        raise SystemExit("plan-coral.html no tiene exactamente un bloque backup-data")
    return new


if __name__ == "__main__":
    data = json.loads(DATA.read_text(encoding="utf-8"))
    PAGE.write_text(embed(PAGE.read_text(encoding="utf-8"), data), encoding="utf-8")
    print(f"copia del {data['exported_at']} incrustada en {PAGE.name}")
