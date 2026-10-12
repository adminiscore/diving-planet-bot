"""ex-0: guarda etiquetas por índice de candidatos.json en etiquetas.json (se acumulan por tandas)."""
import json
import sys
from pathlib import Path

D = Path(__file__).parent


def guardar(tanda: dict) -> None:
    cs = json.loads((D / "candidatos.json").read_text(encoding="utf-8"))
    f = D / "etiquetas.json"
    et = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for i, (slot, exp) in tanda.items():
        et[cs[i]["id"]] = {"slot": slot, "expected": exp}
    f.write_text(json.dumps(et, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(tanda)} etiquetas guardadas; total {len(et)}", file=sys.stderr)
