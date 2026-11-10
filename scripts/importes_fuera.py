"""Simplificar (10-nov): contadores independientes de la puerta de V2, para medir igual V1, V2 y el bot (B).

- **Importes fuera del catálogo:** cada cifra en USD o COP de una respuesta frente a los números de `pricing`,
  `discounts`, `services` y `policies`. Un descuento aplicado o un total («567.000 COP», «356 USD en total») no está y cuenta.
- **Charlas con pase:** las que pasan con una persona en algún turno. En V1 y V2, `estado.pasar.si`; en B,
  `estado.pending_escalation_reason`.

    python -m scripts.importes_fuera docs/robustness/caln/simple/v1-a.jsonl docs/robustness/caln/simple/v1-b.jsonl ...
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KB = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"
_CIFRA = re.compile(r"(?:(?:USD|US\$|\$|COP)\s?(\d[\d.,]*))|(?:(\d[\d.,]*)\s?(?:USD|COP|dólares|pesos))", re.I)


def _entero(texto: str) -> int | None:
    v = re.sub(r"[.,](?=\d{3}\b)", "", texto)
    try:
        return int(float(v.replace(",", ".")))
    except ValueError:
        return None


def numeros_del_catalogo() -> set[int]:
    num: set[int] = set()

    def recoge(x) -> None:
        if isinstance(x, dict):
            for v in x.values():
                recoge(v)
        elif isinstance(x, list):
            for v in x:
                recoge(v)
        elif isinstance(x, (int, float)) and x >= 20:
            num.update({int(x), int(round(x))})  # «125.57» de la respuesta se lee 125 (como `_entero`); su redondeo, 126
        elif isinstance(x, str):
            for m in re.findall(r"\d[\d.,]*", x):
                if (n := _entero(m)) is not None:
                    num.add(n)

    for f in ("pricing.json", "discounts.json", "services.json", "policies.json"):
        recoge(json.loads((KB / f).read_text(encoding="utf-8-sig")))
    return num


def contar(ficheros: list[Path]) -> dict:
    catalogo = numeros_del_catalogo()
    citados = fuera = 0
    con_pase: set[tuple[str, str]] = set()
    charlas: set[tuple[str, str]] = set()
    for f in ficheros:
        for linea in f.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            r = json.loads(linea)
            charla = (str(f), r["dialogo"])
            charlas.add(charla)
            estado = r.get("estado") or {}
            if (estado.get("pasar") or {}).get("si") or estado.get("pending_escalation_reason"):
                con_pase.add(charla)
            for m in _CIFRA.finditer(r.get("reply") or ""):
                if (n := _entero(m.group(1) or m.group(2))) is not None:
                    citados += 1
                    fuera += n not in catalogo
    return {"importes_citados": citados, "importes_fuera": fuera, "charlas": len(charlas), "charlas_con_pase": len(con_pase)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    c = contar([Path(a) for a in sys.argv[1:]])
    print(f"importes fuera del catálogo {c['importes_fuera']} de {c['importes_citados']} citados · "
          f"charlas con pase {c['charlas_con_pase']} de {c['charlas']}")
