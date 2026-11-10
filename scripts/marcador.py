"""Bloque 0 (10-nov): la línea del marcador de una comparación A/B del panel, igual para los tres.

Cada lado son varios juicios del panel (3 tiradas, cada una juzgada dos veces: 6 ficheros `tanda-panel-…__claude-…json` de
`scripts.juez_claude --panel`). Da los clientes con grave por juicio y su media, si la bajada cuenta (4 o más de media: el ruido
medido el 9-nov), la comparación cliente a cliente, si los dos lados se juzgaron con la misma referencia (su huella) y, con los
JSONL del panel, las llamadas de IA por turno y el estilo frente a la persona de los episodios reales.

    python -m scripts.marcador --a A1.json A1-p2.json … --b B1.json B1-p2.json … [--panel-a 061a.jsonl …] [--panel-b …]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

UMBRAL = 3  # clientes de media en panel-vara (Gadea, 10-nov; con su ruido, ~1 % de falsos positivos). Era 4 en el panel viejo
PERSONA = {"caracteres": 119, "con_pregunta": 23, "con_precio": 13, "con_enlace": 25}  # los 75 episodios reales
_PRECIO = re.compile(r"\d{1,3}(?:\.\d{3})+\s*(?:COP|pesos)|\b\d{2,4}\s*(?:USD|US\$|dólares|dollars)\b|\$\s?\d", re.IGNORECASE)


def graves_de(fichero: Path) -> dict[str, bool]:
    """Cliente → si el juez le puso grave en ese juicio."""
    datos = json.loads(Path(fichero).read_text(encoding="utf-8"))
    return {d["id"]: any(c["id"] == "sin-graves" and c["verdict"] != "cumple" for c in d["criteria"]) for d in datos["dialogues"]}


def huella_de(fichero: Path) -> str | None:
    return json.loads(Path(fichero).read_text(encoding="utf-8")).get("huella_referencia")


def lado(ficheros: list[Path]) -> dict:
    juicios = [graves_de(f) for f in ficheros]
    clientes = sorted(set().union(*juicios))
    return {"por_juicio": [sum(j.values()) for j in juicios],
            "media": statistics.mean(sum(j.values()) for j in juicios),
            # 10-nov (revisión del rumbo): vistos y ciegos por separado; los vistos se usaron para diseñar y pueden sobreajustarse
            **{f"media_{g}": statistics.mean(sum(v for c, v in j.items() if c.startswith(g)) for j in juicios)
               for g in ("visto", "ciego")},
            "cuota": {c: sum(j.get(c, False) for j in juicios) / len(juicios) for c in clientes},
            "huellas": {huella_de(f) for f in ficheros}}


def comparar(a: dict, b: dict) -> dict:
    comunes = sorted(set(a["cuota"]) & set(b["cuota"]))
    mejoran = [c for c in comunes if b["cuota"][c] <= a["cuota"][c] - 0.5]
    empeoran = [c for c in comunes if b["cuota"][c] >= a["cuota"][c] + 0.5]
    diferencia = b["media"] - a["media"]
    return {"diferencia": diferencia, "cuenta": abs(diferencia) >= UMBRAL, "mejoran": mejoran, "empeoran": empeoran,
            "igual": len(comunes) - len(mejoran) - len(empeoran),
            "misma_referencia": len(a["huellas"] | b["huellas"]) == 1 and None not in (a["huellas"] | b["huellas"])}


def estilo(jsonl: list[Path]) -> dict:
    """Llamadas de IA por turno y cómo contesta el bot, frente a la persona."""
    filas = [json.loads(ln) for f in jsonl for ln in Path(f).read_text(encoding="utf-8").splitlines() if ln.strip()]
    respuestas = [f.get("reply") or "" for f in filas if f.get("reply")]
    # Las de IA que escriben o leen; la búsqueda por significado (`embedding`) no cuenta, como en la Fase 1 y en la medida del 0,5.
    llamadas = [sum(x.get("p") != "embedding" for x in (m[0] if isinstance(m, list) and m else m or {}).get("llamadas") or [])
                for m in (f.get("metricas") for f in filas)]
    n = len(respuestas) or 1
    return {"turnos": len(filas), "llamadas_por_turno": round(statistics.mean(llamadas), 2) if llamadas else None,
            "caracteres": statistics.median(len(r) for r in respuestas) if respuestas else None,
            # 10-nov (aviso del Claude de Álvaro, #3775): sin los enlaces, que llevan «?language=es» y contaban como pregunta
            "con_pregunta": round(100 * sum("?" in re.sub(r"https?://\S+", "", r) for r in respuestas) / n),
            "con_precio": round(100 * sum(bool(_PRECIO.search(r)) for r in respuestas) / n),
            "con_enlace": round(100 * sum("http" in r for r in respuestas) / n)}


def informe(a: dict, b: dict, ea: dict | None, eb: dict | None) -> str:
    c = comparar(a, b)
    lineas = [f"Clientes con grave por juicio: A {a['por_juicio']} → B {b['por_juicio']}",
              f"Media: A {a['media']:.1f} → B {b['media']:.1f} ({c['diferencia']:+.1f}); "
              + (f"CUENTA ({UMBRAL} o más de media)" if c["cuenta"] else f"no cuenta: por debajo del ruido (menos de {UMBRAL} de media)"),
              f"Vistos: A {a['media_visto']:.1f} → B {b['media_visto']:.1f} · ciegos: A {a['media_ciego']:.1f} → B "
              f"{b['media_ciego']:.1f}",
              f"Cliente a cliente: mejoran {len(c['mejoran'])}, empeoran {len(c['empeoran'])}, igual {c['igual']}",
              "Referencia del juez: " + ("la misma en los dos lados" if c["misma_referencia"]
                                         else f"OJO, distinta o sin huella: A {sorted(map(str, a['huellas']))}, B {sorted(map(str, b['huellas']))}")]
    for nombre, e in (("A", ea), ("B", eb)):
        if e:
            lineas.append(f"Estilo {nombre}: {e['caracteres']} caracteres · {e['con_pregunta']} % con pregunta · {e['con_precio']} % con "
                          f"precio · {e['con_enlace']} % con enlace · {e['llamadas_por_turno']} llamadas de IA por turno ({e['turnos']} turnos)")
    lineas.append(f"La persona: {PERSONA['caracteres']} caracteres · {PERSONA['con_pregunta']} % con pregunta · "
                  f"{PERSONA['con_precio']} % con precio · {PERSONA['con_enlace']} % con enlace")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a", nargs="+", required=True, type=Path, help="juicios del lado A")
    ap.add_argument("--b", nargs="+", required=True, type=Path, help="juicios del lado B")
    ap.add_argument("--panel-a", nargs="*", type=Path, default=[], help="JSONL del panel del lado A (para el estilo)")
    ap.add_argument("--panel-b", nargs="*", type=Path, default=[], help="JSONL del panel del lado B")
    args = ap.parse_args(argv)
    print(informe(lado(args.a), lado(args.b), estilo(args.panel_a) if args.panel_a else None,
                  estilo(args.panel_b) if args.panel_b else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
