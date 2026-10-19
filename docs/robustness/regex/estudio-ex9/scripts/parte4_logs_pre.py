"""Parte 4: logs de PRE de las rondas SOLO VISIBLES (sin ninguna fila del oculto en su JSONL) desde el 14-oct (los cuatro
dominios del extractor ya promocionados). Cuenta, por campo, cuántas veces el extractor y el regex coinciden, difieren
o el regex leía algo que el extractor descarta; cuántas veces falla el extractor (y manda el regex); y otras líneas
donde el regex decide algo (duración, nº de inmersiones, edades, hotel, "voy solo", red de menciones...).
Salida: out/parte4.json
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

def rondas_solo_visibles() -> list[str]:
    """Rondas 2026-10-1* con log cuyo JSONL solo tiene diálogos del golden VISIBLE (ninguna fila del oculto)."""
    import glob
    import os

    g = json.loads((comun.REPO / "docs/robustness/golden-set/golden-dialogues.json").read_text(encoding="utf-8"))
    visibles = {d["id"] for d in g["dialogues"] if d.get("suite") != "oculto"}
    out = []
    for f in sorted(glob.glob(str(comun.REPO / "docs/robustness/synthetic-runs/2026-10-1*.jsonl"))):
        nombre = os.path.basename(f)[:-6]
        if not (comun.REPO / f"docs/robustness/logs-pre-{nombre}.txt").exists():
            continue
        if all(json.loads(x).get("tag") in visibles for x in open(f, encoding="utf-8")):
            out.append(nombre)
    return out


rondas = [r for r in rondas_solo_visibles() if r >= "2026-10-14"]
R_VALOR = re.compile(r"\[EXTRACT\]\[EX(\d)\] (\w+)=(.+?) \(regex: (.+?)(?:, guardado: .*)?\)$")
R_LEIA = re.compile(r"\[EXTRACT\]\[EX(\d)\] el regex le[ií]a (\w+)=(.+?); el cliente no")
CLAVES = {
    "turnos": "[TURN_METRICS]",
    "turnos_jev": "[ROUTER][JEV]",
    "extractor_fallo": "el extractor falló",
    "extractor_fallo_puerta": "[EXTRACT][EX] el extractor falló y la puerta no deja",
    "u3_4_jev_descarta_regex": "[EXTRACT][U3-4] campo=",
    "u3_3_jev_descarta_regex": "[EXTRACT][U3-3] campo=",
    "s4_26_regex_otra_persona_manda_jev": "[CORE][S4-26] la regex ve a otra persona",
    "cal_c5_red_menciones_no_actua": "[CORE][CAL-C5]",
    "signals_llm_red_precision": "[CORE][SIGNALS]",
    "cutover_fill_gaps_aplicado": "[EXTRACT][CUTOVER]",
    "voy_solo_curso": "[CORE] singular course booking",
    "intent_duracion": "[INTENT] Detected duration",
    "intent_n_inmersiones": "[INTENT] Detected cert dive count",
    "intent_n_dias": "[INTENT] Detected cert day count",
    "intent_edades": "[INTENT] Detected ages",
    "intent_isla": "[INTENT] Detected island",
    "intent_hotel": "[INTENT] Detected hotel",
    "intent_idioma": "[INTENT] Detected language",
    "idioma_extractor": "[CORE][IDIOMA] el extractor dice",
    "intent_solo": "[CORE] tras",
    "router_llm_por_duda": "-> router LLM",
    "jev_fallo": "[ROUTER][JEV] fallo",
    "escalado_palabra": "[ESCALATION]",
}
por_campo = defaultdict(Counter)
otras = Counter()
ejemplos = defaultdict(list)
for r in rondas:
    for linea in open(comun.REPO / f"docs/robustness/logs-pre-{r}.txt", encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if linea.startswith("INFO:"):
            linea = linea[5:].strip()
        elif linea.startswith("WARNING:"):
            linea = linea[8:].strip()
        m = R_VALOR.search(linea)
        if m:
            _, campo, ext, rx = m.groups()
            por_campo[campo]["coinciden" if rx == ext else "solo extractor" if rx == "None" else "distinto"] += 1
            if rx not in ("None", ext) and len(ejemplos[f"{campo} distinto"]) < 8:
                ejemplos[f"{campo} distinto"].append(f"extractor={ext} regex={rx}")
            continue
        m = R_LEIA.search(linea)
        if m:
            por_campo[m.group(2)]["regex leía, extractor: no lo afirma"] += 1
            continue
        for k, v in CLAVES.items():
            if v in linea:
                otras[k] += 1
                if k not in ("turnos", "turnos_jev") and len(ejemplos[k]) < 5:
                    ejemplos[k].append(linea[:220])
print("rondas:", len(rondas), rondas)
for c, v in por_campo.items():
    print(f"  {c:24} {dict(v)}")
for k, v in otras.most_common():
    print(f"  {v:5} {k}")
(comun.OUT / "parte4.json").write_text(json.dumps({"rondas": rondas, "por_campo": {c: dict(v) for c, v in por_campo.items()},
                                                   "otras": dict(otras), "ejemplos": dict(ejemplos)},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
