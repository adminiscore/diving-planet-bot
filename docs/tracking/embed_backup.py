"""Mete la copia de datos (data/plan-coral.json) y la cobertura del golden-set dentro de plan-coral.html.

La pagina publicada pinta primero esa copia (nunca sale vacia) y luego la sustituye por los
datos en vivo. Tras exportar la base de datos de la pagina a `data/plan-coral.json` (se lo
pides a Claude: "exporta la base de datos de Plan Coral"), ejecuta:

    python docs/tracking/embed_backup.py

y republica `plan-coral.html` en la MISMA URL (ver README).

La cobertura (docs/robustness/golden-set/coverage.json, de coverage.py) no vive en la base de
datos: sale del repo, asi que se incrusta aqui cada vez que cambia el golden-set.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PAGE = HERE / "plan-coral.html"
DATA = HERE / "data" / "plan-coral.json"
COVERAGE = HERE.parent / "robustness" / "golden-set" / "coverage.json"


def _block(block_id: str) -> re.Pattern:
    return re.compile(rf'(<script type="application/json" id="{block_id}">)(.*?)(</script>)', re.S)


def embed(page_html: str, data: dict, block_id: str = "backup-data") -> str:
    # "</" dentro de un <script> lo cerraria antes de tiempo: se escapa como "<\/".
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new, count = _block(block_id).subn(lambda m: m.group(1) + payload + m.group(3), page_html)
    if count != 1:
        raise SystemExit(f"plan-coral.html no tiene exactamente un bloque {block_id}")
    return new


if __name__ == "__main__":
    data = json.loads(DATA.read_text(encoding="utf-8"))
    html = embed(PAGE.read_text(encoding="utf-8"), data)
    if COVERAGE.exists():
        html = embed(html, json.loads(COVERAGE.read_text(encoding="utf-8")), "coverage-data")
    PAGE.write_text(html, encoding="utf-8")
    print(f"copia del {data['exported_at']} incrustada en {PAGE.name}" + (" (+ cobertura)" if COVERAGE.exists() else ""))
