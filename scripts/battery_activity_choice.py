"""Bateria de los prompts que ELIGEN entre actividades (2026-09-14).

Existe porque ni el eval-set (`run_extraction_eval.py`, solo `fill_gaps` + veto)
ni la bateria de grupo (`battery_group_allocation_gate.py`, solo `_understand`)
pasan por las tres redes que deciden QUE actividad quiere alguien:

  signals -> `llm_extractor.detect_special_signals`: actividad de un acompanante
             que se une a mitad de flujo (`companion_activity`).
  slot    -> `llm_extractor.resolve_slot_answer("companion_activity_choice")`:
             respuesta a "¿minicurso o snorkel para tu acompanante?".
  router  -> `escalation.detect_routing_signals`: si el cliente esta DUDANDO entre
             actividades (`comparing_options`) y cuales.

Mide dos variantes por caso (docs/robustness/activity-domain-plan.md, F2a):

  base      -> los prompts tal cual.
  for_whom  -> los mismos prompts + el contexto de negocio de cada opcion, sacado
               del registro de actividades (`for_whom` de activities.json).
  vocab     -> (F2b) opciones del router = actividades reservables del registro.
  vocab+ctx -> vocab + el contexto de negocio de esas opciones.

La decision de activar `for_whom` en produccion se toma con esta tabla, caso a
caso: una mejora que se compensa con un empeoramiento no vale (leccion del
2026-09-12 con el eval-set agregado).

Uso (necesita una API key real; los scripts no trazan en LangSmith):

    ENV_FILE=.env.dev python -m scripts.battery_activity_choice [repeticiones]
"""

import asyncio
import copy
import json
import sys
from collections import Counter

from src.agents import escalation, llm_extractor
from src.domain import activities as dom
from src.prompts import booking

MINI, SNK, CERT, COURSE = "minicourse", "snorkel", "certified_diving", "padi_course"

# (id, lang, mensaje, esperado). `None` = debe abstenerse.
SIGNALS = [
    ("s01-amigo-snorkel", "es", "hay un amigo que quiere hacer snorkel", SNK),
    ("s02-primo-certificado", "es", "viene mi primo a bucear, él es certificado también", CERT),
    ("s03-acompanante-no-certificado-bucear", "es", "mi acompañante quiere hacer buceo pero no es certificado", MINI),
    ("s04-solo-atributo", "es", "mi amigo no está certificado", None),
    ("s05-jerga-parces", "es", "también vienen mis parces a hacer snorkel", SNK),
    ("s06-cambio-propio", "es", "mejor snorkel", None),
    ("s07-novia-probar", "es", "mi novia quiere probar a bucear, nunca lo ha hecho", MINI),
    ("s08-certificado-inactivo", "es", "mi hermano se certificó hace 8 años y no ha vuelto a bucear, quiere venir a bucear", CERT),
    ("s09-en-first-time", "en", "my friend wants to try diving for the first time", MINI),
    ("s10-en-open-water", "en", "my wife is an open water diver and wants to dive with me", CERT),
]

SLOT = [
    ("c01-bautizo", "es", "que pruebe el bautizo", MINI),
    ("c02-arriba-peces", "es", "prefiere quedarse arriba viendo los peces", SNK),
    ("c03-lo-que-sea", "es", "lo que sea mejor", None),
    ("c04-bajar-tanque", "es", "que se anime a bajar con tanque", MINI),
    ("c05-careteo", "es", "careteo nomás", SNK),
    ("c06-en-surface", "en", "she'd rather just swim at the surface", SNK),
]

# esperado: None = no esta comparando; set = esta comparando esas opciones.
ROUTER = [
    ("r01-minicurso-o-snorkel", "es", "no sé si hacer el minicurso o el snorkel", {MINI, SNK}),
    ("r02-pareja-duda", "es", "mi pareja duda entre buceo y minicurso", {CERT, MINI}),
    ("r03-elige-una", "es", "quiero el minicurso", None),
    ("r04-curso-o-minicurso", "es", "qué me recomiendas, el curso open water o el minicurso? nunca he buceado",
     # Con el vocabulario de hoy solo cabe `padi_course`; con el abierto (F2b) lo
     # correcto es el curso que nombra. Las dos respuestas son validas.
     [{COURSE, MINI}, {"padi_open_water", MINI}]),
    ("r05-reserva-ambas", "es", "quiero buceo y snorkel para los dos", None),
    ("r06-en-first-timer", "en", "is snorkeling or the mini course better for a first timer?", {SNK, MINI}),
    # F2b: dudas entre opciones que el vocabulario de hoy (4 valores) no puede expresar.
    ("r07-open-water-o-advanced", "es", "no sé si hacer el open water o el advanced", {"padi_open_water", "padi_advanced"}),
    ("r08-nitrox-o-flotabilidad", "es", "dudo entre la especialidad de nitrox y la de flotabilidad", {"specialty_nitrox", "specialty_buoyancy"}),
    ("r09-en-rescue-or-divemaster", "en", "should I do the rescue course or go for divemaster?", {"padi_rescue", "padi_divemaster"}),
]


# ── Variantes ────────────────────────────────────────────────────────────────

_ORIG = {
    "signals_prompt": llm_extractor.signals_system_prompt,
    "slot_prompt": llm_extractor.slot_resolver_prompt,
    "routing_tool": escalation.ROUTING_TOOL,
}


def _context_block(lang: str, ids: list[str]) -> str:
    lead = ("Para quién es cada actividad:" if lang == "es" else "Who each activity is for:")
    return f"\n\n{lead}\n{dom.business_context(lang, ids)}"


def _with_for_whom():
    companion_ids = booking._field_enum("companion_activity", booking.SIGNALS_TOOL)
    llm_extractor.signals_system_prompt = (
        lambda lang: _ORIG["signals_prompt"](lang) + _context_block(lang, companion_ids)
    )

    def slot_prompt(slot, lang):
        text = _ORIG["slot_prompt"](slot, lang)
        options = booking.SLOT_RESOLVER_SPEC[slot].get("enum")
        return text + _context_block("en", options) if options else text

    llm_extractor.slot_resolver_prompt = slot_prompt

    tool = copy.deepcopy(_ORIG["routing_tool"])
    options = tool["function"]["parameters"]["properties"]["comparing_options"]["properties"]["options"]
    options["description"] += _context_block("en", options["items"]["enum"])
    escalation.ROUTING_TOOL = tool


def _restore():
    llm_extractor.signals_system_prompt = _ORIG["signals_prompt"]
    llm_extractor.slot_resolver_prompt = _ORIG["slot_prompt"]
    escalation.ROUTING_TOOL = _ORIG["routing_tool"]


def _with_open_vocabulary(with_context: bool):
    """F2b: las opciones del router pasan a ser todas las actividades reservables
    del registro (antes 4 valores escritos a mano)."""
    def apply():
        _restore()
        tool = copy.deepcopy(_ORIG["routing_tool"])
        options = tool["function"]["parameters"]["properties"]["comparing_options"]["properties"]["options"]
        options["items"]["enum"] = dom.bookable_activity_ids()
        if with_context:
            options["description"] += _context_block("en", options["items"]["enum"])
        escalation.ROUTING_TOOL = tool
    return apply


VARIANTES = [
    ("base", _restore),
    ("for_whom", _with_for_whom),
    ("vocab", _with_open_vocabulary(False)),
    ("vocab+ctx", _with_open_vocabulary(True)),
]


# ── Ejecucion y veredicto ────────────────────────────────────────────────────

async def _signals(lang, msg):
    got = await llm_extractor.detect_special_signals(msg, lang=lang)
    return got.get("companion_activity")


async def _slot(lang, msg):
    got = await llm_extractor.resolve_slot_answer("companion_activity_choice", msg, lang=lang)
    return got.get("value")


async def _router(lang, msg):
    got = await escalation.detect_routing_signals(msg, lang=lang)
    obj = got.get("comparing_options") or {}
    if not obj.get("comparing"):
        return None
    return frozenset(obj.get("options") or [])


def _ok(got, expected):
    if isinstance(expected, list):  # varias respuestas validas
        return any(_ok(got, option) for option in expected)
    if isinstance(expected, set):
        return got is not None and set(got) == expected
    return got == expected


NETS = [("signals", SIGNALS, _signals), ("slot", SLOT, _slot), ("router", ROUTER, _router)]


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    tabla = {}
    for variant, apply in VARIANTES:
        apply()
        for net, cases, call in NETS:
            for case_id, lang, msg, expected in cases:
                outs = [await call(lang, msg) for _ in range(reps)]
                oks = sum(_ok(o, expected) for o in outs)
                vistos = Counter(json.dumps(sorted(o) if isinstance(o, frozenset) else o) for o in outs)
                tabla[(net, case_id, variant)] = (oks, reps, vistos)
    _restore()

    for net, cases, _call in NETS:
        print()
        print("=" * 92)
        print(f"RED: {net}")
        print("=" * 92)
        for case_id, _lang, msg, expected in cases:
            cells = []
            for variant, _apply in VARIANTES:
                oks, n, vistos = tabla[(net, case_id, variant)]
                cells.append(f"{variant} {oks}/{n} {dict(vistos)}")
            esperado = ([sorted(e) for e in expected] if isinstance(expected, list)
                        else sorted(expected) if isinstance(expected, set) else expected)
            print(f"  {case_id:40} esperado={esperado}")
            for cell in cells:
                print(f"      {cell}")

    print()
    print("=" * 92)
    print("RESUMEN (casos con todas las repeticiones correctas)")
    print("=" * 92)
    resumen = {}
    for variant, _apply in VARIANTES:
        por_red = {}
        for net, cases, _call in NETS:
            por_red[net] = sum(1 for c in cases if tabla[(net, c[0], variant)][0] == reps)
        resumen[variant] = por_red
        print(f"  {variant:10} " + " | ".join(f"{net} {por_red[net]}/{len(cases)}" for net, cases, _ in NETS))
    names = [v for v, _apply in VARIANTES]
    cambios = [
        (net, c[0], {v: tabla[(net, c[0], v)][0] for v in names})
        for net, cases, _call in NETS for c in cases
        if len({tabla[(net, c[0], v)][0] for v in names}) > 1
    ]
    print("  CASOS QUE CAMBIAN ENTRE VARIANTES (aciertos por variante):")
    for net, case_id, per_variant in cambios:
        print(f"    {net:8} {case_id:40} " + "  ".join(f"{v}={n}/{reps}" for v, n in per_variant.items()))
    print("JSON " + json.dumps({"resumen": resumen, "cambios": cambios}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
