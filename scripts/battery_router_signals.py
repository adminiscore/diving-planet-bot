"""Bateria de las 9 senales del router con el LLM real (2026-09-15).

El tool de `escalation.detect_routing_signals` es UNO para todas las senales: cambiar
una parte (p. ej. el vocabulario de `comparing_options`) puede mover las demas. Los
tests del router van con mock, asi que esta bateria es la unica medida real.

Un caso acierta si salen exactamente las senales esperadas y ninguna otra. Las frases
vienen de hallazgos en vivo documentados en docs/HISTORY.md (bloques 2.2-2.5 y la red
de precision) y de los negativos que las descripciones del tool piden no marcar.

Variantes: las de `battery_activity_choice` para el router (`base` y `vocab`).

Uso (necesita una API key real):

    ENV_FILE=.env.dev python -m scripts.battery_router_signals [repeticiones] [variantes]
"""

import asyncio
import json
import sys
from collections import Counter

from scripts import battery_activity_choice as bac
from src.agents import escalation

# (id, lang, mensaje, senales esperadas). {} = ninguna senal.
CASES = [
    ("h01-asesor", "es", "quiero hablar con un asesor", {"wants_human": True}),
    ("h02-persona-real", "es", "me puede atender una persona de verdad?", {"wants_human": True}),
    ("h03-en-someone", "en", "can I speak with someone from your team", {"wants_human": True}),
    ("m01-de-cero", "es", "mejor empecemos de cero", {"wants_menu_or_restart": True}),
    ("s01-embarazadita", "es", "estoy embarazadita, puedo bucear?", {"sensitive_topic": "medical_questions"}),
    ("s02-epileptica", "es", "soy epiléptica", {"sensitive_topic": "medical_questions"}),
    ("s03-cardiaca", "es", "tengo una condición cardiaca", {"sensitive_topic": "medical_questions"}),
    ("s04-llover-manana", "es", "¿va a llover mañana en cartagena?", {"sensitive_topic": "weather_conditions"}),
    # Problema de pago y queja a la vez: los dos valores escalan igual.
    ("s05-cobro-doble", "es", "me cobraron dos veces y nadie me responde",
     {"sensitive_topic": ["complaints_or_emergencies", "real_time_issues"]}),
    ("a01-pierna", "es", "perdí una pierna en un accidente, puedo bucear?", {"adaptive_diving_topic": True}),
    ("a02-sordomuda", "es", "soy sordomuda", {"adaptive_diving_topic": True}),
    ("a03-lesion-medular", "es", "tengo una lesión medular", {"adaptive_diving_topic": True}),
    ("d01-domingo", "es", "¿queda espacio el domingo?", {"availability_question": True}),
    ("d02-en-saturday", "en", "any spots left for saturday?", {"availability_question": True}),
    ("l01-pagina-blanco", "es", "me sale página en blanco al reservar", {"broken_link_complaint": True}),
    ("l02-en-dead-link", "en", "your booking link is dead", {"broken_link_complaint": True}),
    ("c01-numero", "es", "¿me pasas un número para llamar?", {"asks_for_contact_number": True}),
    ("c02-correo", "es", "tienen algún correo?", {"asks_for_contact_number": True}),
    ("b01-imprevisto", "es", "me surgió un imprevisto y no puedo asistir", {"booking_change_topic": "cancellation"}),
    ("b02-otro-dia", "es", "quiero pasar mi buceo para otro día", {"booking_change_topic": "reschedule"}),
    ("b03-agregar-persona", "es", "ya tengo una reserva hecha, quiero agregar una persona más", {"booking_change_topic": "modify_headcount"}),
    # Negativos: lo que las descripciones piden NO marcar.
    ("n01-politica-cancelacion", "es", "¿cuál es la política de cancelación?", {}),
    ("n02-si-llueve", "es", "¿qué pasa si llueve ese día?", {}),
    ("n03-pago-tarjeta", "es", "puedo pagar con tarjeta?", {}),
    ("n04-link-seguro", "es", "¿el link de pago es seguro?", {}),
    ("n05-precio-manana", "es", "quiero bucear mañana, cuánto cuesta?", {}),
    ("n06-reserva-grupo", "es", "si, tengo el AOWD, además tengo 3 amigos que quieren hacer alguna actividad", {}),
    ("n07-amigo-snorkel", "es", "tengo un amigo que quiere bucear y yo hago snorkel", {}),
]


def _signals(got: dict) -> dict:
    """Senales marcadas, sin falsos ni vacios. `comparing_options` cuenta solo si compara."""
    out = {k: v for k, v in got.items() if v not in (False, None, "", [], {})}
    obj = out.pop("comparing_options", None)
    if isinstance(obj, dict) and obj.get("comparing"):
        out["comparing_options"] = frozenset(obj.get("options") or [])
    return out


def _ok(got: dict, expected: dict) -> bool:
    if set(got) != set(expected):
        return False
    return all(bac._ok(got[k], v) for k, v in expected.items())


def _cases():
    router = [(cid, lang, msg, {} if exp is None else {"comparing_options": exp}) for cid, lang, msg, exp in bac.ROUTER]
    return CASES + router


def _plain(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, list):  # varias respuestas validas
        return [_plain(v) for v in value]
    return value


def _show(signals: dict) -> str:
    return json.dumps({k: _plain(v) for k, v in sorted(signals.items())}, ensure_ascii=False)


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    wanted = sys.argv[2].split(",") if len(sys.argv) > 2 else ["base", "vocab"]
    only = tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else ()  # prefijos de id
    variants = [(name, apply) for name, apply in bac.VARIANTES if name in wanted]
    cases = [c for c in _cases() if not only or c[0].startswith(only)]
    tabla = {}
    for variant, apply in variants:
        apply()
        for cid, lang, msg, expected in cases:
            outs = [_signals(await escalation.detect_routing_signals(msg, lang=lang)) for _ in range(reps)]
            tabla[(cid, variant)] = (sum(_ok(o, expected) for o in outs), Counter(_show(o) for o in outs))
    bac._restore()

    for cid, _lang, msg, expected in cases:
        print(f"  {cid:32} esperado={_show(expected)}  «{msg[:60]}»")
        for variant, _apply in variants:
            oks, vistos = tabla[(cid, variant)]
            print(f"      {variant:6} {oks}/{reps} {dict(vistos)}")

    print("\nRESUMEN (casos con todas las repeticiones correctas)")
    resumen = {v: sum(1 for c in cases if tabla[(c[0], v)][0] == reps) for v, _ in variants}
    for variant, n in resumen.items():
        print(f"  {variant:6} {n}/{len(cases)}")
    cambios = [(c[0], {v: tabla[(c[0], v)][0] for v, _ in variants}) for c in cases
               if len({tabla[(c[0], v)][0] for v, _ in variants}) > 1]
    print("  CASOS QUE CAMBIAN ENTRE VARIANTES:")
    for cid, per_variant in cambios:
        print(f"    {cid:32} " + "  ".join(f"{v}={n}/{reps}" for v, n in per_variant.items()))
    print("JSON " + json.dumps({"resumen": resumen, "cambios": cambios}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
