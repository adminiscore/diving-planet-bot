"""Punto 3, opción C: compara el escalón 0 (C) con OFF, V1 y V2 del 6-oct, turno a turno.

Para cada diálogo y versión dice, en cada turno, si el bot COTIZÓ (dio un importe) y si PREGUNTÓ EL ORIGEN. Los
criterios vienen del relevo del 7-oct:
- 6 diálogos donde el bot DEBE preguntar el origen y NO cotizar (el cliente pide precio sin decir desde dónde sale);
- 2 diálogos donde NO debe repreguntar el origen (eran las 2 regresiones de V1: el cliente ya lo había dado a
  entender).

    python -m scripts.origen_c_comparar

Lee `docs/robustness/origen-2026-10-06.json` (OFF/V1/V2) y `docs/robustness/origen-c/<diálogo>.jsonl` (C).
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEBE_PREGUNTAR = [
    "open-water-precio-para-colombianos-corrige-mito",
    "minicurso-precio-colombianos-origen-pendiente",
    "paquete-5-buceos-cop-refresh-y-hoteles",
    "colombianos-precio-minicurso-dos-inmersiones",
    "precio-fundive-datos-faltan",
    "reserva-paquete-5-buceos-solicita",
]
NO_DEBE_REPREGUNTAR = [
    "referral-mas-refresher-hotel-y-domingo-pascua",
    "curso-open-water-transporte-y-regreso-otro-dia",
]
# Un importe: 1.429.000 COP, 178 USD, $630,000, USD 124...
_IMPORTE = re.compile(r"\d[\d.,]{2,}\s*(?:cop|usd|d[oó]lares|pesos)|(?:usd|cop|\$)\s*\d[\d.,]{1,}", re.I)
# Preguntar el origen: la frase fija de C o las formas libres de OFF/V1/V2.
_ORIGEN = re.compile(
    r"desde d[oó]nde sal|saldr[ií]as\s+\*?desde cartagena|ya est[aá]s\s+\*?en las\s+\*?islas|"
    r"where you'?re starting from|leave\s+\*?from cartagena|already\s+\*?on the rosario|"
    r"(?:sales|sale|salen) desde cartagena o|from cartagena or",
    re.I,
)


def _filas_c(dialogo: str) -> list[dict]:
    p = Path("docs/robustness/origen-c") / f"{dialogo}.jsonl"
    if not p.exists():
        return []
    filas = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    # una fila por turno (el script guarda una por juicio; nos quedamos con la última de cada turno)
    # `reproducir_juez_pre` escribe `turn` (texto) y `reply`; el fichero del 6-oct, `turno` y `respuesta`.
    por_turno = {}
    for f in filas:
        por_turno[int(f.get("turno") or f.get("turn"))] = {**f, "respuesta": f.get("respuesta") or f.get("reply")}
    return [por_turno[k] for k in sorted(por_turno)]


_FRASES = re.compile(r"[^.!?\n]*[.!?]?")


def _pregunta_origen(r: str) -> bool:
    """El origen dentro de una PREGUNTA. El saludo de bienvenida dice "departing from Cartagena or right from the
    islands" / "saliendo desde Cartagena o desde las propias islas" en una frase AFIRMATIVA: contarlo como pregunta
    falseaba el turno 1 de casi todos los diálogos (lección del 7-oct). La C se reconoce además por su texto exacto."""
    from src.agents.conversational_core import (
        ORIGEN_ANTES_DEL_PRECIO_EN,
        ORIGEN_ANTES_DEL_PRECIO_ES,
    )

    if ORIGEN_ANTES_DEL_PRECIO_ES in r or ORIGEN_ANTES_DEL_PRECIO_EN in r:
        return True
    return any(f.strip().endswith("?") and _ORIGEN.search(f) for f in _FRASES.findall(r))


def _marca(respuesta: str) -> str:
    r = respuesta or ""
    cotiza, origen = bool(_IMPORTE.search(r)), _pregunta_origen(r)
    return {(True, True): "cotiza+pregunta", (True, False): "COTIZA", (False, True): "pregunta origen",
            (False, False): "—"}[(cotiza, origen)]


def main() -> None:
    previo = json.load(open("docs/robustness/origen-2026-10-06.json", encoding="utf-8"))["dialogos"]
    for grupo, titulo in ((DEBE_PREGUNTAR, "DEBE preguntar el origen y NO cotizar"),
                          (NO_DEBE_REPREGUNTAR, "NO debe repreguntar el origen")):
        print(f"\n{'=' * 104}\n{titulo}\n{'=' * 104}")
        for d in grupo:
            versiones = {v: previo.get(d, {}).get(v, []) for v in ("OFF", "V1", "V2")}
            versiones["C"] = _filas_c(d)
            n = max((len(v) for v in versiones.values()), default=0)
            print(f"\n· {d}")
            print(f"    {'turno':<6}" + "".join(f"{v:<18}" for v in versiones))
            for t in range(n):
                fila = f"    {t + 1:<6}"
                for v, filas in versiones.items():
                    fila += f"{(_marca(filas[t].get('respuesta')) if t < len(filas) else '·'):<18}"
                print(fila)


if __name__ == "__main__":
    main()
