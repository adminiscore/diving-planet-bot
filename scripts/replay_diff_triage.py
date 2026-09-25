"""Separa el RUIDO del diff de `scripts/replay_diff.py` antes de concluir nada.

El juez de `replay_diff` marca INVENTADO de más, y el propio script lo avisa: hay que
apartar a mano los turnos que no tocan. Esto automatiza los dos criterios OBJETIVOS de
ese aviso y deja para lectura humana solo lo que queda:

- **sin pregunta**: el turno no está en `preguntas-etiquetadas.json`, así que no es un
  turno que este cambio deba tocar (el flag solo actúa donde hay algo que contestar);
- **estado previo distinto**: off y on ya llegaban al turno con estado diferente, así que
  la diferencia de este turno no es atribuible a este turno.

Lo que sobrevive se imprime con el mensaje y el motivo del juez, para leerlo. El juez es
estricto con los mapeos de producto ("paquete de 5 buceos" -> buceo certificado es
correcto): eso NO se filtra solo, se lee.

    python -m scripts.replay_diff_triage --dir u3-4
"""
import json
import sys
from pathlib import Path

# La consola de Windows es cp1252 y los mensajes del golden traen emojis y tildes.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = Path("docs/robustness") / (sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else "u3-4")
ETIQUETAS = Path("docs/robustness/u3-4/preguntas-etiquetadas.json")


def load(name):
    rows = [json.loads(line) for line in open(D / f"replay-{name}.jsonl", encoding="utf-8")]
    return {(r["id"], r["turn"]): r for r in rows}


def main() -> None:
    off, on = load("off"), load("on")
    label = {o["msg"]: o["label"] for o in json.load(open(ETIQUETAS, encoding="utf-8"))}
    diffs = json.load(open(D / "diff.json", encoding="utf-8"))["diffs"]

    cubos: dict[str, list] = {"sin-pregunta": [], "estado-previo-distinto": [], "a-leer": [], "ok-juez": []}
    for d in diffs:
        k = (d["key"][0], d["key"][1])
        if not d["verdict"].get("inventados"):
            cubos["ok-juez"].append((k, d))
            continue
        msg = on.get(k, {}).get("msg", "")
        prev = (k[0], k[1] - 1)
        if not label.get(msg):
            cubos["sin-pregunta"].append((k, d))
        elif off.get(prev, {}).get("state") != on.get(prev, {}).get("state"):
            cubos["estado-previo-distinto"].append((k, d))
        else:
            cubos["a-leer"].append((k, d))

    print(f"turnos con dato de más: {len(diffs)} | el juez ve inventado en "
          f"{len(diffs) - len(cubos['ok-juez'])}")
    for nombre in ("sin-pregunta", "estado-previo-distinto"):
        print(f"  ruido [{nombre}]: {len(cubos[nombre])}")
    print(f"  >>> A LEER A MANO: {len(cubos['a-leer'])}\n")

    for nombre in ("a-leer", "sin-pregunta", "estado-previo-distinto"):
        print(f"===== {nombre} ({len(cubos[nombre])}) =====")
        for k, d in cubos[nombre]:
            msg = on.get(k, {}).get("msg", "").replace("\n", " ")
            print(f"- {k[0]}#{k[1]}  {msg[:110]!r}")
            print(f"    de más: {d['extra']}")
            print(f"    juez: {d['verdict'].get('inventados')} — {d['verdict'].get('por_que', '')[:220]}")
        print()


if __name__ == "__main__":
    main()
