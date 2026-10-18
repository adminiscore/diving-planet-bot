"""MOD-4 (18-oct): el RESUMEN de la conversación y el DETECTOR DE IDIOMA (hoy gpt-4o-mini) con otros modelos.

Resumen: las conversaciones VISIBLES más largas de la ronda CAL-F y los 10 casos del banco de inyecciones (r6-2), con
`conversation_summarizer._generate_summary` tal cual (incluida la regla de seguridad de la memoria). Se guarda cada
resumen para leerlo: lo que importa es que sea fiel y que NO apunte como hecho lo que el cliente ordena o dice que otro
autorizó. Idioma: mensajes cortos o ambiguos con `language_detector.detect_language_llm` (es/en); acuerdo con
gpt-4o-mini y latencia.

    python -m scripts.mod_resumen_idioma docs/robustness/mod/mod4-resumen-idioma.json
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agents import conversation_summarizer as cs  # noqa: E402
from src.agents import language_detector as ld  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.catalog import _detect_language_from_text  # noqa: E402

RONDA = "docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl"
GOLDEN = "docs/robustness/golden-set/golden-dialogues.json"
INYECCION = "docs/robustness/seguridad/banco-inyeccion.json"
CANDIDATOS = ["gpt-4o-mini", "deepseek/deepseek-v4.1-flash", "gpt-5.4-mini", "gpt-6-luna"]
MENSAJES_IDIOMA = [
    "ok", "vale", "perfecto 👌", "thanks!", "gracias", "👍", "sí", "yes please", "bueno", "great", "dale",
    "Hola! My partner and I want to dive", "Bonjour", "Obrigado", "cuanto", "how much", "info", "precio?", "price?",
    "buenas", "hey", "jaja ok", "lol ok", "mañana?", "tomorrow?", "snorkel", "minicurso", "fun dives",
    "Isla Grande", "Cartagena 2 pax", "2 personas", "2 people", "certificado", "certified", "ok gracias",
    "ok thanks", "si porfa", "yes pls", "no", "nop",
]


def conversaciones() -> list[tuple[str, str, list[dict]]]:
    ocultos = {d["id"] for d in json.load(open(GOLDEN, encoding="utf-8"))["dialogues"] if d.get("suite") == "oculto"}
    por_conv: dict = {}
    for ln in open(RONDA, encoding="utf-8"):
        r = json.loads(ln)
        if r["tag"] not in ocultos:
            por_conv.setdefault((r["tag"], r["conv"]), []).append(r)
    largas = sorted(por_conv.items(), key=lambda kv: -len(kv[1]))[:8]
    out = []
    for (tag, _), rs in largas:
        rs.sort(key=lambda r: r["turn"])
        turnos = []
        for r in rs:
            turnos += [{"role": "user", "content": r["msg"]}, {"role": "assistant", "content": r["reply"] or ""}]
        out.append((tag, _detect_language_from_text(rs[0]["reply"] or "") or "es", turnos))
    for f in json.load(open(INYECCION, encoding="utf-8"))["fallos"]:
        turnos = list(f["historial"]) + [{"role": "user", "content": f["mensaje_cliente"]}]
        out.append((f["id"], _detect_language_from_text(f["mensaje_cliente"]) or "es", turnos))
    return out


async def main():
    convs = conversaciones()
    res = {"resumen": {}, "idioma": {}}
    for modelo in CANDIDATOS:
        settings.resumen_model = settings.idioma_model = modelo
        ts, salidas = [], []
        for tag, lang, turnos in convs:
            t0 = time.perf_counter()
            try:
                out = await cs._generate_summary(None, cs._format_turns(turnos, lang), lang)
            except Exception as exc:  # noqa: BLE001
                out = f"ERROR {exc}"
            ts.append(time.perf_counter() - t0)
            salidas.append({"tag": tag, "resumen": out})
        res["resumen"][modelo] = {"p50": round(statistics.median(ts), 2), "salidas": salidas}
        ti, idiomas = [], []
        for m in MENSAJES_IDIOMA:
            t0 = time.perf_counter()
            idiomas.append(await ld.detect_language_llm(m))
            ti.append(time.perf_counter() - t0)
        res["idioma"][modelo] = {"p50": round(statistics.median(ti), 2), "salidas": idiomas}
        print(f"{modelo:30} resumen p50 {res['resumen'][modelo]['p50']}s · idioma p50 "
              f"{res['idioma'][modelo]['p50']}s", flush=True)
    ref = res["idioma"]["gpt-4o-mini"]["salidas"]
    for modelo in CANDIDATOS[1:]:
        dif = [(m, a, b) for m, a, b in zip(MENSAJES_IDIOMA, ref, res["idioma"][modelo]["salidas"]) if a != b]
        print(f"idioma {modelo}: {len(dif)} distintos de gpt-4o-mini: {dif[:8]}")
    Path(sys.argv[1]).write_text(json.dumps({"mensajes_idioma": MENSAJES_IDIOMA, **res}, ensure_ascii=False, indent=1),
                                 encoding="utf-8")


asyncio.run(main())
