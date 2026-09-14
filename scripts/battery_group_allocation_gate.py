"""Bateria a nivel de CONVERSACION para el grupo: reparto Y total (2026-09-12,
ampliada 2026-09-14).

Existe porque el eval-set NO puede responder esta pregunta: su arnes
(`run_extraction_eval.py`) pide SIEMPRE todos los huecos y crea un estado limpio
por caso, asi que nunca pasa por `conversational_core._relevant_gaps` ni tiene
un total de un turno anterior. Y PRE no tiene trafico real (solo los 3
desarrolladores), asi que tampoco se puede esperar a que lo conteste la
produccion: hay que provocarlo.

Mide las CUATRO combinaciones de los dos vetos que tocan al grupo:

  veto de total   -> `llm_group_size_veto_cutover`: corrige un total que el regex
                     resolvio con confianza y mal ("en total 7: 4 certificados..."
                     da 4 -- la cifra de un tramo tomada por el total).
  veto de reparto -> `llm_group_allocation_veto_cutover`: corrige un reparto que
                     el regex resolvio pero que NO suma el total.

(La version del 2026-09-12 media la "puerta" de `_relevant_gaps` en lugar del
veto de total; la puerta se retiro ese mismo dia con estos datos, ver
docs/robustness/progress-log.md.)

Se ataca por `_understand`, que no toca BD ni RAG, y se juzga el ESTADO que queda
al final del turno, no el intent: el fallo del 2026-09-14 (un reparto de 4
guardado para un grupo de 7) solo se ve en el estado, porque el total se escribe
una sola vez y el intent del turno decia 4.

Uso (necesita una API key real, igual que el eval-set):

    ENV_FILE=.env.dev python -m scripts.battery_group_allocation_gate
    ssh ... "docker exec -i dp-pre-bot python3 -m scripts.battery_group_allocation_gate"

Argumento opcional: numero de repeticiones por variante (por defecto 2). Los
fallos vistos hasta ahora han sido deterministas (0/N o N/N), pero repetir es lo
que distingue una regresion real del ruido -- leccion de 2026-09-12.

Familias de escenario:
  beneficio -> el cliente SI dio un reparto contable; perderlo es un fallo real
  total     -> el total se lee mal (frase no listada, o cifra de un tramo); hay
               controles donde el regex acierta y nadie debe tocarlo
  riesgo    -> NO hay reparto contable; inventarlo seria un misfill
  frontera  -> observacional, para mirarlo a mano

Cada escenario lleva el total esperado (`gs`); si no lo lleva, se espera que el
total ya sabido por la conversacion no cambie.
"""

import asyncio
import json
import sys
from collections import Counter

from src.agents import conversational_core as cc
from src.agents import supervisor as sup
from src.flows.state import ConversationState

CERT, MINI, SNK, OW = "certified_diving", "minicourse", "snorkel", "padi_open_water"

_PREGUNTA_REPARTO_ES = [
    {"role": "user", "content": "somos 7"},
    {"role": "assistant", "content": "Perfecto, 7 personas. Que quiere hacer cada uno?"},
]
_PREGUNTA_REPARTO_EN = [
    {"role": "user", "content": "we are 7"},
    {"role": "assistant", "content": "Great, 7 people. What would each one like to do?"},
]

SCENARIOS = [
    # ── BENEFICIO ────────────────────────────────────────────────────────
    {
        "id": "b01-sustantivo-mismo-turno",
        "familia": "beneficio",
        "desc": "Total y reparto en el MISMO turno, con la actividad nombrada como sustantivo.",
        "message": "somos 8: 6 certificados, 2 minicurso",
        "state": {},
        "gs": 8,
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
        # AMBIGUO: "2 open water" tambien se dice de dos personas CON la certificacion.
        # Decision del owner (2026-09-15): el bot pregunta si ya estan certificados o
        # quieren certificarse; no se asume ni curso ni buceo certificado. Hasta que
        # exista esa pregunta, lo correcto es no guardar reparto (el bot pregunta).
        "desc": "Nivel de curso nombrado sin decir si lo tienen o lo quieren (ambiguo: se pregunta).",
        "message": "2 open water y 3 snorkel",
        "state": {"detected_group_size": 5},
        "expect": ("NONE",),
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
        "gs": 7,
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

    # ── TOTAL (2026-09-14) ───────────────────────────────────────────────
    # Mismo fallo de lista cerrada que el reparto, visto desde el total: el
    # regex coge la cifra del primer tramo ("4 certificados") como total.
    {
        "id": "t01-seremos-dos-tramos",
        "familia": "total",
        "desc": "'seremos' no esta en la lista de frases de total.",
        "message": "seremos 7, 4 certificados y 3 snorkel",
        "state": {},
        "gs": 7,
        "expect": ("ALLOC", {CERT: 4, SNK: 3}),
    },
    {
        "id": "t02-total-al-final",
        "familia": "total",
        "desc": "El total va DETRAS del tramo; los otros 3 no dicen actividad.",
        "message": "4 certificados y en total seremos 7",
        "state": {},
        "gs": 7,
        "expect": ("NONE",),
    },
    {
        "id": "t03-entre-todos",
        "familia": "total",
        "desc": "'entre todos' como frase de total.",
        "message": "entre todos 7, 4 certificados y 3 snorkel",
        "state": {},
        "gs": 7,
        "expect": ("ALLOC", {CERT: 4, SNK: 3}),
    },
    {
        "id": "t04-grupo-de-un-tramo",
        "familia": "total",
        "desc": "Total + un solo tramo: no hay reparto completo.",
        "message": "somos un grupo de 7, 4 certificados",
        "state": {},
        "gs": 7,
        "expect": ("NONE",),
    },
    {
        "id": "t05-en-in-total",
        "familia": "total",
        "desc": "Ingles: 'in total' + tres tramos.",
        "message": "7 in total: 4 certified, 2 minicourse and 1 snorkel",
        "lang": "en",
        "state": {},
        "gs": 7,
        "expect": ("ALLOC", {CERT: 4, MINI: 2, SNK: 1}),
    },
    {
        "id": "t06-pareja-e-hijos",
        "familia": "total",
        "desc": "El bug original del veto de total: 'pareja' gana y no suma a los hijos.",
        "message": "vengo con mi pareja y nuestros dos hijos",
        "state": {},
        "gs": 4,
        "expect": ("ANY",),
    },
    {
        "id": "m01-tramo-tras-total-sabido",
        "familia": "total",
        "desc": "Multi-turno: 7 ya sabidos, el turno trae el reparto completo.",
        "message": "4 certificados y 3 snorkel",
        "state": {"detected_group_size": 7},
        "history": _PREGUNTA_REPARTO_ES,
        "expect": ("ALLOC", {CERT: 4, SNK: 3}),
    },
    {
        "id": "m02-un-tramo-tras-total-sabido",
        "familia": "total",
        "desc": "El caso del 2026-09-14: 7 sabidos, 'N certificados' da total 4 en el "
                "turno y un reparto de 4 'cuadraba' con el. No puede guardarse.",
        "message": "4 certificados",
        "state": {"detected_group_size": 7},
        "history": _PREGUNTA_REPARTO_ES,
        "expect": ("NONE",),
    },
    {
        "id": "m03-en-tramos-tras-total-sabido",
        "familia": "total",
        "desc": "Ingles, multi-turno, reparto completo.",
        "message": "4 certified and 3 snorkel",
        "lang": "en",
        "state": {"detected_group_size": 7},
        "history": _PREGUNTA_REPARTO_EN,
        "expect": ("ALLOC", {CERT: 4, SNK: 3}),
    },
    {
        "id": "m04-correccion-explicita",
        "familia": "total",
        "desc": "Una correccion explicita SI cambia un total ya sabido.",
        "message": "perdon, en realidad somos 5",
        "state": {"detected_group_size": 7},
        "gs": 5,
        "expect": ("NONE",),
    },
    {
        "id": "c01-control-somos",
        "familia": "total",
        "desc": "Control: el regex acierta.",
        "message": "somos 4",
        "state": {},
        "gs": 4,
        "expect": ("NONE",),
    },
    {
        "id": "c02-control-pareja-sola",
        "familia": "total",
        "desc": "Control: caso real validado por el owner, 'con mi pareja' = 2.",
        "message": "con mi pareja, tenemos un presupuesto ajustado",
        "state": {},
        "gs": 2,
        "expect": ("NONE",),
    },
    {
        "id": "c03-control-reparto-con-verbo",
        "familia": "total",
        "desc": "Control: total y reparto que el regex ya entiende.",
        "message": "somos 7: 4 bucean y 3 snorkel",
        "state": {},
        "gs": 7,
        "expect": ("ALLOC", {CERT: 4, SNK: 3}),
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
        "desc": "Se anade gente sin cifra: no se puede repartir. (Que el total suba en "
                "uno aqui es el flujo de acompanante, no este mecanismo.)",
        "message": "tambien viene un amigo",
        "state": {"detected_group_size": 4},
        "gs": None,
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
    # 2026-09-14: el caso para el que existia la guarda de vocabulario de actividad
    # en el reparto (acompanante descrito solo por un atributo). Medido con LLM
    # real: 0 repartos inventados con y sin esa guarda (3/3); lo cubren la
    # comprobacion de cifras del texto y la invariante de la suma.
    {
        "id": "r11-atributo-sin-actividad",
        "familia": "riesgo",
        "desc": "Acompanante descrito solo por un atributo: no hay actividad que repartir.",
        "message": "mi amigo no esta certificado",
        "state": {"detected_activity": "certified_diving", "is_certified": True, "detected_group_size": 2},
        "expect": ("NONE",),
    },
    {
        "id": "r12-atributo-con-total",
        "familia": "riesgo",
        "desc": "Atributo del acompanante con el total en el mismo mensaje.",
        "message": "somos 2, mi amigo no está certificado",
        "state": {"detected_activity": "certified_diving", "is_certified": True},
        "expect": ("NONE",),
    },
    {
        "id": "r13-atributo-plural",
        "familia": "riesgo",
        "desc": "Atributo de un tramo con cifra pero sin actividad.",
        "message": "vamos 4 pero dos no tienen licencia",
        "state": {"detected_activity": "certified_diving", "is_certified": True},
        # 2026-09-15 (owner: recomendar, no asumir): 2 certificados y 2 sin decidir,
        # a los que el bot recomienda opciones. Antes se esperaba no repartir.
        "expect": ("ALLOC", {CERT: 2}),
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
        "desc": "El regex resuelve un reparto INCOMPLETO: territorio del veto de reparto.",
        "message": "somos 5: 3 certificados, 1 minicurso y 1 snorkel",
        "state": {},
        "expect": ("OBS",),
    },
    {
        "id": "f03-sin-total-conocido",
        "familia": "frontera",
        "desc": "Sin total en estado ni en el turno: no hay invariante que aplicar.",
        "message": "6 certificados y 2 minicurso",
        "state": {},
        "expect": ("OBS",),
    },
]


# ── Los dos vetos, conmutables ──────────────────────────────────────────────

VARIANTES = [
    # (nombre, veto de total, veto de reparto)
    ("sin_vetos", False, False),
    ("solo_reparto", False, True),
    ("solo_total", True, False),
    ("ambos", True, True),
]


def _build_state(spec):
    s = ConversationState(conversation_id="ga-gate-" + spec["id"])
    s.language = spec.get("lang", "es")
    for k, v in (spec.get("state") or {}).items():
        setattr(s, k, v)
    s.history = list(spec.get("history") or [])
    return s


async def _run(spec, veto_total, veto_reparto):
    object.__setattr__(sup.settings, "llm_group_size_veto_cutover", veto_total)
    object.__setattr__(sup.settings, "llm_group_allocation_veto_cutover", veto_reparto)
    state = _build_state(spec)
    try:
        await cc._understand(state, spec["message"])
    except Exception as exc:  # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    return {"alloc": state.detected_group_allocation, "gs": state.detected_group_size,
            "undecided": state.pending_undecided_qty or 0}


def _total_esperado(spec):
    if "gs" in spec:
        return spec["gs"]
    return (spec.get("state") or {}).get("detected_group_size")


def _clasificar(spec, got):
    """OK / TOTAL_MAL / PARCIAL / DISTINTO / VACIO / ALUCINA / ALTERA.

    Se juzga el estado final. `PARCIAL` (un reparto guardado que no suma el total
    guardado) y `TOTAL_MAL` son las categorias que importan: las dos tarifican
    mal la reserva sin que nadie pregunte. Un `VACIO` es seguro: el bot pregunta.
    """
    if "err" in got:
        return "ERROR"
    alloc, gs = got.get("alloc"), got.get("gs")
    esperado = _total_esperado(spec)
    if esperado is not None and gs != esperado:
        return "TOTAL_MAL"
    # Las personas sin actividad elegida (se les recomiendan opciones, 2026-09-15)
    # cuentan para el total aunque aun no esten en el reparto.
    if alloc and isinstance(gs, int) and gs > 0 and sum(alloc.values()) + got.get("undecided", 0) != gs:
        return "PARCIAL"
    kind = spec["expect"][0]
    if kind == "ALLOC":
        if alloc == spec["expect"][1]:
            return "OK"
        return "VACIO" if not alloc else "DISTINTO"
    if kind == "NONE":
        return "OK" if not alloc else "ALUCINA"
    if kind == "KEEP":
        return "OK" if alloc == spec["expect"][1] else "ALTERA"
    if kind == "ANY":
        return "OK"
    return "OBS"


_FAMILIAS = ("beneficio", "total", "riesgo", "frontera")


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    nombres = [v[0] for v in VARIANTES]
    tabla = {}
    for spec in SCENARIOS:
        for nombre, veto_total, veto_reparto in VARIANTES:
            veredictos, vistos = [], []
            for _ in range(reps):
                got = await _run(spec, veto_total, veto_reparto)
                veredictos.append(_clasificar(spec, got))
                vistos.append(got.get("err") or "gs={} {}".format(
                    got.get("gs"), json.dumps(got.get("alloc"), ensure_ascii=False, sort_keys=True)))
            # El PEOR veredicto manda: una sola repeticion mala ya es un fallo.
            peor = next((v for v in veredictos if v != "OK"), "OK")
            tabla[(spec["id"], nombre)] = (peor, Counter(vistos))

    for fam in _FAMILIAS:
        specs = [s for s in SCENARIOS if s["familia"] == fam]
        if not specs:
            continue
        print()
        print("=" * 90)
        print(f"FAMILIA: {fam.upper()}")
        print("=" * 90)
        print(f"{'escenario':<36}" + "".join(f"{n:<14}" for n in nombres))
        for s in specs:
            print(f"{s['id']:<36}"
                  + "".join(f"{tabla[(s['id'], n)][0]:<14}" for n in nombres))
        print()
        for s in specs:
            print(f"  [{s['id']}] {s['message']!r}")
            for n in nombres:
                _v, vistos = tabla[(s["id"], n)]
                print(f"      {n:<13} "
                      + ", ".join(f"{c}x {a}" for a, c in vistos.most_common()))

    print()
    print("=" * 90)
    print("RESUMEN POR VARIANTE")
    print("=" * 90)
    medibles = [s for s in SCENARIOS if s["familia"] != "frontera"]
    resumen = {}
    for n in nombres:
        veredictos = Counter(tabla[(s["id"], n)][0] for s in medibles)
        ok_por_familia = {
            fam: sum(1 for s in medibles if s["familia"] == fam and tabla[(s["id"], n)][0] == "OK")
            for fam in _FAMILIAS if fam != "frontera"
        }
        resumen[n] = {"ok": ok_por_familia, "veredictos": dict(veredictos)}
        tot = {fam: sum(1 for s in medibles if s["familia"] == fam) for fam in ok_por_familia}
        print(f"  {n:<13} "
              + " | ".join(f"{fam} {ok_por_familia[fam]}/{tot[fam]}" for fam in ok_por_familia)
              + f" | TOTAL_MAL {veredictos.get('TOTAL_MAL', 0)}"
              + f" | PARCIAL {veredictos.get('PARCIAL', 0)}"
              + f" | ALUCINA {veredictos.get('ALUCINA', 0)}"
              + f" | VACIO {veredictos.get('VACIO', 0)}")
    print("JSON " + json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
