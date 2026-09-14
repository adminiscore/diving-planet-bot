"""Bateria de la GUARDA (b) de booleanos del nucleo (F5, 2026-09-14).

Mide `conversational_core._boolean_patch_is_anchored` con turnos reales de
`_understand` (LLM real, sin BD ni RAG) en tres familias:

  legit (apertura)  -> sin pregunta pendiente, el booleano dicho con palabras que
                       ninguna lista conocia ("soy paisa", "tengo el AOWD").
  halluc            -> el turno CONTESTA otra pregunta pendiente (o es charla) y
                       el LLM no debe colar un booleano ("Desde Cartagena" con la
                       ubicacion pendiente rellenaba is_colombian=True 3/3).
  legit (doble)     -> respuesta doble legitima con pregunta pendiente. Coste
                       conocido: la guarda la descarta y el bot pregunta despues.

Linea base medida (3 repeticiones):
  guarda de vocabulario (retirada)  legitimos 0/24   alucinaciones evitadas 18/18
  sin guarda                        legitimos 24/24  alucinaciones evitadas 15/18
  anclaje estructural (actual)      legitimos 18/24  alucinaciones evitadas 18/18

Uso (necesita una API key real; los scripts no trazan en LangSmith):

    ENV_FILE=.env.dev python -m scripts.battery_boolean_anchoring [repeticiones]
"""

import asyncio
import logging
import sys

from src.agents import conversational_core as cc
from src.flows.state import ConversationState


def _state(pending, history, **fields):
    s = ConversationState(conversation_id="bool-anchoring")
    s.language, s.history, s.core_pending_slot = "es", list(history), pending
    for name, value in fields.items():
        setattr(s, name, value)
    return s


H_LOCATION = [
    {"role": "user", "content": "hola quiero bucear, somos 2"},
    {"role": "assistant", "content": "¡Genial! ¿Ya tienen certificación de buceo?"},
    {"role": "user", "content": "si los dos"},
    {"role": "assistant", "content": "Perfecto. ¿Desde dónde salen, Cartagena o ya están en las islas? Y ¿son colombianos?"},
]
H_DIVING = [
    {"role": "user", "content": "quiero hacer buceo, somos 2"},
    {"role": "assistant", "content": "¡Buenísimo! ¿Desde dónde salen? ¿Alguno tiene certificación de buceo?"},
]
H_CERT = [
    {"role": "user", "content": "hola, queremos bucear 2 personas"},
    {"role": "assistant", "content": "¡Genial! ¿Tienen certificación de buceo? ¿Son colombianos?"},
]
CERTIFIED = dict(detected_activity="certified_diving", is_certified=True, detected_group_size=2)
DIVING = dict(detected_activity="certified_diving", detected_group_size=2)

# (id, familia, estado, mensaje, {campo: esperado}); esperado None = no debe rellenarse.
SCENARIOS = [
    ("apertura-paisa", "legit", lambda: _state(None, []), "soy paisa", {"is_colombian": True}),
    ("apertura-paisas", "legit", lambda: _state(None, []), "somos paisas, queremos bucear 2 días", {"is_colombian": True}),
    ("apertura-typos", "legit", lambda: _state(None, []), "ola quiero vucear, ya soy sertificado, somos 2", {"is_certified": True}),
    ("apertura-aowd", "legit", lambda: _state(None, []), "hola soy rocio, quiero hacer buceo, tengo el AOWD", {"is_certified": True}),
    ("apertura-nunca", "legit", lambda: _state(None, []), "hola quiero probar el buceo, nunca lo he hecho, voy solo", {"is_certified": False}),
    ("desde-cartagena", "halluc", lambda: _state(cc.SLOT_LOCATION, H_LOCATION, **CERTIFIED), "Desde Cartagena", {"is_colombian": None}),
    ("bocagrande", "halluc", lambda: _state(cc.SLOT_LOCATION, H_DIVING, **DIVING), "salimos desde bocagrande", {"is_certified": None, "is_colombian": None}),
    ("cert-pendiente-da-ubicacion", "halluc", lambda: _state(cc.SLOT_CERTIFICATION, H_CERT, **DIVING), "desde cartagena", {"is_colombian": None}),
    ("ninguno-colombiano", "halluc", lambda: _state(cc.SLOT_SAFETY, H_LOCATION, location="cartagena", detected_location="cartagena", **CERTIFIED), "ninguno colombiano", {"last_dive_over_2_years": None}),
    ("charla-vale-perfecto", "halluc", lambda: _state(cc.SLOT_LOCATION, H_DIVING, **DIVING), "vale perfecto", {"is_certified": None, "is_colombian": None}),
    ("charla-jaja-ok", "halluc", lambda: _state(cc.SLOT_LOCATION, H_LOCATION, **CERTIFIED), "jajaja ok gracias", {"is_colombian": None}),
    ("doble-cartagena-paisas", "legit", lambda: _state(cc.SLOT_LOCATION, H_LOCATION, **CERTIFIED), "desde cartagena, somos paisas", {"is_colombian": True}),
    ("doble-bocagrande-aowd", "legit", lambda: _state(cc.SLOT_LOCATION, H_DIVING, **DIVING), "salimos de bocagrande, ya tenemos el AOWD", {"is_certified": True}),
    ("cambio-de-tema-paisas", "legit", lambda: _state(cc.SLOT_LOCATION, H_DIVING, **DIVING), "ah y somos paisas", {"is_colombian": True}),
]


def _value(state, field):
    if field == "is_certified":
        return state.is_certified if state.is_certified is not None else state.detected_is_certified
    return getattr(state, field, None)


async def main():
    logging.disable(logging.CRITICAL)
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    totals = {"legit": [0, 0], "halluc": [0, 0]}
    for case_id, family, make, message, expected in SCENARIOS:
        ok, seen = 0, []
        for _ in range(reps):
            state = make()
            await cc._understand(state, message)
            got = {field: _value(state, field) for field in expected}
            seen.append(got)
            ok += all(got[field] == want for field, want in expected.items())
        totals[family][0] += ok
        totals[family][1] += reps
        print(f"[{case_id:28}] {family:6} {ok}/{reps}  esperado={expected}  visto={seen[0]}", flush=True)
    print(f"RESUMEN legitimos {totals['legit'][0]}/{totals['legit'][1]} | "
          f"alucinaciones evitadas {totals['halluc'][0]}/{totals['halluc'][1]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
