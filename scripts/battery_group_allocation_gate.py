"""Bateria a nivel de CONVERSACION para `group_allocation` (2026-09-12).

Existe porque el eval-set NO puede responder esta pregunta: su arnes
(`run_extraction_eval.py`) pide SIEMPRE todos los huecos, asi que nunca pasa por
`conversational_core._relevant_gaps`, que es justo donde se decide si
`group_allocation` se le llega a preguntar al LLM. Y PRE no tiene trafico real
(solo los 3 desarrolladores), asi que tampoco se puede esperar a que lo conteste
la produccion: hay que provocarlo.

Mide las CUATRO combinaciones de las dos palancas que afectan al reparto:

  puerta  -> `_relevant_gaps` quita `group_allocation` de los huecos cuando ya se
             sabe la cantidad y el mensaje no anade gente. Se puso por COSTE, y
             ese argumento decayo al fusionar las peticiones del turno (un campo
             mas viaja en la misma peticion: cuesta tokens, no peticiones).
  veto    -> `llm_group_allocation_veto_cutover`: corrige un reparto que el regex
             resolvio pero que NO suma el total.

Se ataca por `_understand`, que es donde viven las dos y que no toca BD ni RAG.

Uso (necesita una API key real, igual que el eval-set):

    ENV_FILE=.env.dev python -m scripts.battery_group_allocation_gate
    ssh ... "docker exec -i dp-pre-bot python3 -m scripts.battery_group_allocation_gate"

Argumento opcional: numero de repeticiones por variante (por defecto 2). Los
fallos vistos hasta ahora han sido deterministas (0/N o N/N), pero repetir es lo
que distingue una regresion real del ruido -- leccion de 2026-09-12.

Familias de escenario:
  beneficio -> el cliente SI dio un reparto contable; perderlo es un fallo real
  riesgo    -> NO hay reparto contable; inventarlo seria un misfill
  frontera  -> observacional, para mirarlo a mano
"""

import asyncio
import json
import sys
from collections import Counter

from src.agents import conversational_core as cc
from src.agents import supervisor as sup
from src.agents.llm_extractor import missing_fields
from src.flows.state import ConversationState

CERT, MINI, SNK, OW = "certified_diving", "minicourse", "snorkel", "padi_open_water"

SCENARIOS = [
    # ── BENEFICIO ────────────────────────────────────────────────────────
    {
        "id": "b01-sustantivo-mismo-turno",
        "familia": "beneficio",
        "desc": "Total y reparto en el MISMO turno, con la actividad nombrada como sustantivo.",
        "message": "somos 8: 6 certificados, 2 minicurso",
        "state": {},
        "expect": ("ALLOC", {CERT: 6, MINI: 2}),
    },
    {
        "id": "b02-sustantivo-turno-previo",
        "familia": "beneficio",
        "desc": "El total ya se sabia de antes; este turno trae solo el reparto.",
        "message": "6 certificados y 2 minicurso",
        "state": {"detected_group_size": 8},
        "expect": ("ALLOC", {CERT: 6, MINI: 2}),
    },
    {
        "id": "b03-con-titulo",
        "familia": "beneficio",
        "desc": "Jerga distinta para 'certificado': 'con titulo'.",
        "message": "4 con titulo y 2 snorkel",
        "state": {"detected_group_size": 6},
        "expect": ("ALLOC", {CERT: 4, SNK: 2}),
    },
    {
        "id": "b04-brevetados",
        "familia": "beneficio",
        "desc": "Otra jerga regional: 'brevetados'.",
        "message": "3 brevetados y 2 snorkel",
        "state": {"detected_group_size": 5},
        "expect": ("ALLOC", {CERT: 3, SNK: 2}),
    },
    {
        "id": "b05-open-water-nombrado",
        "familia": "beneficio",
        "desc": "Curso PADI concreto nombrado dentro del reparto.",
        "message": "2 open water y 3 snorkel",
        "state": {"detected_group_size": 5},
        "expect": ("ALLOC", {OW: 2, SNK: 3}),
    },
    {
        "id": "b06-en-certified",
        "familia": "beneficio",
        "desc": "Ingles: 'certified' como sustantivo (la palabra que falta en la lista).",
        "message": "3 certified and 3 snorkel",
        "lang": "en",
        "state": {"detected_group_size": 6},
        "expect": ("ALLOC", {CERT: 3, SNK: 3}),
    },
    {
        "id": "b07-en-total-frase-no-listada",
        "familia": "beneficio",
        "desc": "Frase de total fuera de la lista ('en total') + reparto de 3 tramos.",
        "message": "en total 7: 4 certificados, 2 minicurso y 1 snorkel",
        "state": {},
        "expect": ("ALLOC", {CERT: 4, MINI: 2, SNK: 1}),
    },
    {
        "id": "b08-ninos",
        "familia": "beneficio",
        "desc": "Reparto adultos/ninos con el total ya conocido.",
        "message": "2 adultos bucean y 2 ninos hacen snorkel",
        "state": {"detected_group_size": 4, "kids_mention_detected": True},
        "expect": ("ALLOC", {CERT: 2, SNK: 2}),
    },
    {
        "id": "b09-respuesta-a-pregunta-del-bot",
        "familia": "beneficio",
        "desc": "El bot pregunto explicitamente por el reparto y el cliente contesta.",
        "message": "3 buceo y 3 snorkel",
        "state": {"detected_group_size": 6},
        "history": [
            {"role": "user", "content": "somos 6"},
            {"role": "assistant", "content": "Perfecto, 6 personas. Que quiere hacer cada uno?"},
        ],
        "expect": ("ALLOC", {CERT: 3, SNK: 3}),
    },
    {
        "id": "b10-mixto-tres-actividades-jerga",
        "familia": "beneficio",
        "desc": "Tres tramos, uno con jerga no listada.",
        "message": "4 con brevet, 2 minicurso y 1 snorkel",
        "state": {"detected_group_size": 7},
        "expect": ("ALLOC", {CERT: 4, MINI: 2, SNK: 1}),
    },

    # ── RIESGO ───────────────────────────────────────────────────────────
    {
        "id": "r01-followup-con-reparto-ya-sabido",
        "familia": "riesgo",
        "desc": "El caso del eval-set: reparto YA resuelto en estado, turno de logistica. "
                "No debe rederivarse del historial.",
        "message": "desde cartagena",
        "state": {"detected_group_size": 6,
                  "detected_group_allocation": {CERT: 2, MINI: 2, SNK: 2}},
        "history": [
            {"role": "user", "content": "somos 6: 2 bucean, 2 minicurso y 2 snorkel"},
            {"role": "assistant", "content": "Perfecto. Desde donde salen?"},
        ],
        "expect": ("KEEP", {CERT: 2, MINI: 2, SNK: 2}),
    },
    {
        "id": "r02-followup-sin-reparto-sabido",
        "familia": "riesgo",
        "desc": "Mismo turno de logistica pero SIN reparto en estado: no hay nada que inventar.",
        "message": "desde cartagena",
        "state": {"detected_group_size": 6},
        "history": [
            {"role": "user", "content": "somos 6, queremos bucear"},
            {"role": "assistant", "content": "Perfecto. Desde donde salen?"},
        ],
        "expect": ("NONE",),
    },
    {
        "id": "r03-plural-vago",
        "familia": "riesgo",
        "desc": "Un tramo sin numero contable ('mis amigos'): debe abstenerse.",
        "message": "yo buceo y mis amigos hacen snorkel",
        "state": {"detected_group_size": 5},
        "expect": ("NONE",),
    },
    {
        "id": "r04-acompanante-sin-numero",
        "familia": "riesgo",
        "desc": "Se anade gente sin cifra: no se puede repartir.",
        "message": "tambien viene un amigo",
        "state": {"detected_group_size": 4},
        "expect": ("NONE",),
    },
    {
        "id": "r05-pregunta-de-precio",
        "familia": "riesgo",
        "desc": "Turno que no habla del reparto en absoluto.",
        "message": "cuanto cuesta el minicurso?",
        "state": {"detected_group_size": 6},
        "expect": ("NONE",),
    },
    {
        "id": "r06-saludo",
        "familia": "riesgo",
        "desc": "Saludo puro con cantidad ya conocida.",
        "message": "hola buenas",
        "state": {"detected_group_size": 6},
        "expect": ("NONE",),
    },
    {
        "id": "r07-total-repetido",
        "familia": "riesgo",
        "desc": "Repite el total sin dar reparto.",
        "message": "somos 8",
        "state": {"detected_group_size": 8},
        "expect": ("NONE",),
    },
    {
        "id": "r08-actividades-sin-numeros",
        "familia": "riesgo",
        "desc": "Menciona actividades pero sin ninguna cifra por tramo.",
        "message": "unos quieren bucear y otros hacer snorkel",
        "state": {"detected_group_size": 6},
        "expect": ("NONE",),
    },
    {
        "id": "r09-respuesta-a-slot-pendiente",
        "familia": "riesgo",
        "desc": "El bot pregunto por la ubicacion; la respuesta no debe generar reparto.",
        "message": "cartagena",
        "state": {"detected_group_size": 5, "core_pending_slot": "location"},
        "history": [
            {"role": "user", "content": "somos 5, 3 bucean y 2 snorkel"},
            {"role": "assistant", "content": "Desde donde salen, Cartagena o isla?"},
        ],
        "expect": ("NONE",),
    },
    {
        "id": "r10-nacionalidad",
        "familia": "riesgo",
        "desc": "Turno de nacionalidad con grupo conocido: nada de reparto.",
        "message": "ninguno es colombiano",
        "state": {"detected_group_size": 6},
        "expect": ("NONE",),
    },

    # ── FRONTERA (observacional) ─────────────────────────────────────────
    {
        "id": "f01-cambio-legitimo-del-reparto",
        "familia": "frontera",
        "desc": "El reparto ya estaba y el cliente lo CAMBIA. Cambiarlo seria correcto; "
                "hoy el estado lo bloquea. Observacional.",
        "message": "al final mi suegra tambien bucea, no hace snorkel",
        "state": {"detected_group_size": 3,
                  "detected_group_allocation": {CERT: 2, SNK: 1}},
        "history": [
            {"role": "user", "content": "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel"},
            {"role": "assistant", "content": "Anotado."},
        ],
        "expect": ("OBS",),
    },
    {
        "id": "f02-reparto-parcial-visible",
        "familia": "frontera",
        "desc": "El regex resuelve un reparto INCOMPLETO: territorio del veto de "
                "group_allocation (flags off aqui), no de la puerta.",
        "message": "somos 5: 3 certificados, 1 minicurso y 1 snorkel",
        "state": {},
        "expect": ("OBS",),
    },
    {
        "id": "f03-sin-total-conocido",
        "familia": "frontera",
        "desc": "Sin total en estado la puerta NO se aplica: control de que la puerta es "
                "lo unico que cambia entre variantes.",
        "message": "6 certificados y 2 minicurso",
        "state": {},
        "expect": ("OBS",),
    },
]


# ── Las dos palancas, conmutables ───────────────────────────────────────────

_ORIG_RELEVANT_GAPS = cc._relevant_gaps


def _gaps_sin_puerta(state, intent, message):
    """Modela EXACTAMENTE quitar la puerta de coste: si `group_allocation` sigue
    sin resolver y la CONVERSACION tampoco lo sabe, no se le echa de los huecos.
    El resto de filtros se respetan tal cual -- en particular el de
    `_state_known_fields`, que es el que impide rederivar un reparto ya sabido."""
    gaps = list(_ORIG_RELEVANT_GAPS(state, intent, message))
    if "group_allocation" not in gaps and "group_allocation" in missing_fields(intent):
        if "group_allocation" not in cc._state_known_fields(state):
            gaps.append("group_allocation")
    return gaps


VARIANTES = [
    ("hoy", False, False),
    ("sin_puerta", True, False),
    ("solo_veto", False, True),
    ("puerta+veto", True, True),
]


def _build_state(spec):
    s = ConversationState(conversation_id="ga-gate-" + spec["id"])
    s.language = spec.get("lang", "es")
    for k, v in (spec.get("state") or {}).items():
        setattr(s, k, v)
    s.history = spec.get("history") or []
    return s


async def _run(spec, sin_puerta, con_veto):
    cc._relevant_gaps = _gaps_sin_puerta if sin_puerta else _ORIG_RELEVANT_GAPS
    object.__setattr__(sup.settings, "llm_group_allocation_veto_cutover", con_veto)
    try:
        intent, _carry = await cc._understand(_build_state(spec), spec["message"])
    except Exception as exc:  # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    return {"alloc": getattr(intent, "group_allocation", None),
            "gs": getattr(intent, "group_size", None)}


def _clasificar(spec, got, state_gs):
    """OK / PARCIAL / DISTINTO / VACIO / ALUCINA.

    `PARCIAL` es la categoria que importa vigilar: un reparto PRESENTE que no
    suma el total es peor que no tener reparto -- es el fallo que el veto de
    `group_allocation` existe para cazar. El total puede venir de este turno o
    de la conversacion, asi que se miran los dos.
    """
    if "err" in got:
        return "ERROR"
    alloc = got.get("alloc")
    total = got.get("gs") or state_gs
    kind = spec["expect"][0]
    if kind == "ALLOC":
        if alloc == spec["expect"][1]:
            return "OK"
        if not alloc:
            return "VACIO"
        if isinstance(total, int) and total > 0 and sum(alloc.values()) != total:
            return "PARCIAL"
        return "DISTINTO"
    if kind == "NONE":
        return "OK" if not alloc else "ALUCINA"
    if kind == "KEEP":
        return "OK" if (alloc == spec["expect"][1] or not alloc) else "ALTERA"
    return "OBS"


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    nombres = [v[0] for v in VARIANTES]
    tabla = {}
    for spec in SCENARIOS:
        state_gs = (spec.get("state") or {}).get("detected_group_size")
        for nombre, sin_puerta, con_veto in VARIANTES:
            veredictos, allocs = [], []
            for _ in range(reps):
                got = await _run(spec, sin_puerta, con_veto)
                veredictos.append(_clasificar(spec, got, state_gs))
                allocs.append(got.get("err") or json.dumps(
                    got.get("alloc"), ensure_ascii=False, sort_keys=True))
            tabla[(spec["id"], nombre)] = (Counter(veredictos).most_common(1)[0][0],
                                           Counter(allocs))

    for fam in ("beneficio", "riesgo", "frontera"):
        specs = [s for s in SCENARIOS if s["familia"] == fam]
        if not specs:
            continue
        print()
        print("=" * 78)
        print(f"FAMILIA: {fam.upper()}")
        print("=" * 78)
        print(f"{'escenario':<34}" + "".join(f"{n:<14}" for n in nombres))
        for s in specs:
            print(f"{s['id']:<34}"
                  + "".join(f"{tabla[(s['id'], n)][0]:<14}" for n in nombres))
        print()
        for s in specs:
            print(f"  [{s['id']}] {s['message']!r}")
            for n in nombres:
                _v, allocs = tabla[(s["id"], n)]
                print(f"      {n:<12} "
                      + ", ".join(f"{c}x {a}" for a, c in allocs.most_common()))

    print()
    print("=" * 78)
    print("RESUMEN POR VARIANTE")
    print("=" * 78)
    total_ben = sum(1 for s in SCENARIOS if s["familia"] == "beneficio")
    total_rie = sum(1 for s in SCENARIOS if s["familia"] == "riesgo")
    resumen = {}
    for n in nombres:
        def cuenta(fam, veredicto):
            return sum(1 for s in SCENARIOS
                       if s["familia"] == fam and tabla[(s["id"], n)][0] == veredicto)
        resumen[n] = {"ok": cuenta("beneficio", "OK"),
                      "parcial": cuenta("beneficio", "PARCIAL"),
                      "vacio": cuenta("beneficio", "VACIO"),
                      "alucina": cuenta("riesgo", "ALUCINA")}
        r = resumen[n]
        print(f"  {n:<13} correctos {r['ok']}/{total_ben} | "
              f"PARCIALES (peligrosos) {r['parcial']} | vacios {r['vacio']} | "
              f"alucinaciones {r['alucina']}/{total_rie}")
    print("JSON " + json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
