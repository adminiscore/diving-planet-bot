"""ex-9b paso 6: junta las comparaciones del replay (`paso4_diff.py` sobre las pasadas de `paso4_replay.py` y
`paso6_replay.py`) en `datos/paso6-replay.json`. Las pasadas y sus diff viven en <ESTUDIO_OUT> (fuera del repo).

Pasadas que espera (cwd = raíz del repo; las "viejo" con el código de 9ae3e19, exportado aparte):
    paso4_replay.py --modo oraculo|caido --salida viejo|nuevo          (flags apagados: código viejo frente a nuevo)
    paso6_replay.py --modo oraculo --salida p6-base [--flags <uno> --salida p6-<nombre>]
    paso6_replay.py --modo caido --salida p6-base / --flags <los cinco> --salida p6-todos
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

COMPARACIONES = {
    "flags apagados: código de 9ae3e19 frente al nuevo (oráculo)": ("paso4-oraculo-viejo", "paso4-oraculo-nuevo"),
    "flags apagados: código de 9ae3e19 frente al nuevo (extractor caído)": ("paso4-caido-viejo", "paso4-caido-nuevo"),
    "duracion_por_extractor (oráculo)": ("paso4-oraculo-p6-base", "paso4-oraculo-p6-duracion"),
    "edades_por_extractor (oráculo)": ("paso4-oraculo-p6-base", "paso4-oraculo-p6-edades"),
    "plan_elegido_por_extractor (oráculo)": ("paso4-oraculo-p6-base", "paso4-oraculo-p6-plan"),
    "reparto_al_sumarse_alguien (oráculo)": ("paso4-oraculo-p6-base", "paso4-oraculo-p6-reparto"),
    "notas_rag_desde_estado (oráculo)": ("paso4-oraculo-p6-base", "paso4-oraculo-p6-notas"),
    "los cinco flags con el extractor caído": ("paso4-caido-p6-base", "paso4-caido-p6-todos"),
}
salida = {"turnos": None, "dialogos": None, "comparaciones": {}}
for nombre, (a, b) in COMPARACIONES.items():
    diff = json.loads((comun.OUT / f"diff-{a}-vs-{b}.json").read_text(encoding="utf-8"))
    salida["comparaciones"][nombre] = diff
    base = json.loads((comun.OUT / f"{a}.json").read_text(encoding="utf-8"))
    salida["turnos"] = base["turnos"]
    salida["dialogos"] = len({f["id"] for f in base["filas"]})
    print(f"{nombre}: estado {len(diff['dialogos_estado'])} diálogos, respuesta {len(diff['dialogos_reply'])}, "
          f"RAG {len(diff['dialogos_rag'])}")
destino = comun.REPO / "docs/robustness/regex/estudio-ex9/datos/paso6-replay.json"
destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
print("->", destino)
