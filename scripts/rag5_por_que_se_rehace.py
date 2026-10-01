"""rag-5, escalón 0 LOCAL: ¿por qué se tira la respuesta adelantada?

La ronda rag5-B de PRE (30-sep) aprovechó la respuesta adelantada en 12 turnos y la REHIZO en otros 12, y no se
sabía por qué. Gadea dejó un diagnóstico (`rag_rehecho_por`), pero solo dice QUÉ PARTE de la huella cambió
(mensaje / idioma / historial / resumen / origen). Casi todo va a caer en "resumen", y el resumen del estado
(`supervisor._build_extra_context`) lee unos 25 campos: las notas del mensaje (la hipótesis), pero también el
paso de la conversación, el tamaño del grupo, la certificación, el origen... Con ese diagnóstico, una ronda nueva
NO distinguiría "cambiaron las notas" de "la extracción apuntó un dato".

Esto lo responde en local y gratis, con el mismo montaje que `scripts/replay_golden_local.py` (extracción y Jev
de verdad; RAG, acuse y notas con respuestas fijas): pasa los diálogos del golden (sin el examen oculto) con
`RAG_ADELANTADO` encendido y, cada vez que se rehace, compara el resumen frase a frase y apunta QUÉ frase
apareció o desapareció entre el principio del turno y el momento de responder.

Las notas van con respuesta fija (vacía) A PROPÓSITO: así, todo "resumen" que cambie aquí NO es por las notas.
Si aun así se rehace mucho por "resumen", la hipótesis de las notas es, como mínimo, incompleta.

    python -m scripts.rag5_por_que_se_rehace
"""
import asyncio
import os
import re
import sys
from collections import Counter

os.environ.update({
    "ENV_FILE": ".env.dev", "APP_ENV": "development",
    "LLM_EXTRACTION_CUTOVER_CERTIFICATION": "true", "LLM_EXTRACTION_CUTOVER_GROUP": "true",
    "LLM_EXTRACTION_CUTOVER_LOCATION": "true", "LLM_EXTRACTION_CUTOVER_LOGISTICS": "true",
    "JEV_ROUTER_ENABLED": "true", "AGENT_ARCH": "true", "RAG_MIN_SCORE": "0.40",
    # los interruptores de rag-5 como en PRE (docker-compose.vps.yml)
    "ANSWER_AND_CONTINUE": "true", "RAG_ADELANTADO": "true", "RAG_BUSQUEDA_ORIGEN": "true",
    # Como en PRE: con las notas en SERIE se calculan al principio del turno, ANTES de lanzar el adelantado, y
    # la espera que se quiere medir no existe (primera pasada del 30-sep: 99 % aprovechado, falso).
    "NOTES_IN_PARALLEL": "true", "ACK_IN_PARALLEL": "false",
    "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "",
    "CHATWOOT_API_TOKEN": "", "CHATWOOT_BASE_URL": "http://127.0.0.1:9", "CHATWOOT_API_BASE_URL": "http://127.0.0.1:9",
})
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.replay_golden_local import _noop, _rag, dialogues  # noqa: E402
from src.agents import conversational_core as core  # noqa: E402
from src.agents import escalation, supervisor  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

_FRASES = re.compile(r"(?<=[.!?])\s+")
REGISTRO: list[dict] = []
DIALOGO = {"id": None}  # el diálogo en curso, para rastrear cada caso
NOTAS: list[dict] = []  # cada llamada al extractor de notas (con notas reales)
_original = core._adoptar_o_rehacer


def _frases(texto: str) -> set[str]:
    return {f.strip() for f in _FRASES.split(texto or "") if f.strip()}


async def _espia(state, message, history, adelantado):
    """Envuelve `_adoptar_o_rehacer` SIN cambiar lo que hace: recalcula la huella igual que ella y apunta el diff."""
    await core.await_pending_notes(state)
    entradas = core._entradas_rag(state, history)
    ahora, antes = core._huella_rag(message, entradas), adelantado["huella"]
    partes = [n for n, a, b in zip(core._PARTES_HUELLA, antes, ahora, strict=True) if a != b]
    fila = {"dialogo": DIALOGO["id"], "mensaje": message, "partes": partes, "aparece": [], "desaparece": []}
    if "resumen" in partes:
        a, b = _frases(antes[3]), _frases(ahora[3])
        fila["aparece"] = sorted(b - a)
        fila["desaparece"] = sorted(a - b)
        # El bloque de notas es UNA "frase" para `_frases` (lista con guiones, sin puntos): se guarda entero para
        # ver si cambia por un dato NUEVO o solo se reescribe/reordena.
        fila["notas_antes"], fila["notas_despues"] = _bloque_notas(antes[3]), _bloque_notas(ahora[3])
        fila["resto_igual"] = _sin_notas(antes[3]) == _sin_notas(ahora[3])
    REGISTRO.append(fila)
    return await _original(state, message, history, adelantado)


_CAB_NOTAS = re.compile(
    r"(Otros detalles que el cliente ya mencion[oó][^:]*:|Other details the customer already mentioned[^:]*:)"
)


def _bloque_notas(resumen: str) -> list[str]:
    """Las notas del cliente como lista de puntos: lo que va tras la cabecera, mientras sigan los guiones."""
    m = _CAB_NOTAS.search(resumen or "")
    if not m:
        return []
    items = []
    for linea in resumen[m.end():].split("\n"):
        linea = linea.strip()
        if linea.startswith("- "):
            items.append(linea[2:].strip())
        elif items:  # se acabó la lista
            break
    return items


def _sin_notas(resumen: str) -> str:
    """El resumen SIN el bloque de notas: si esto es igual antes y después, lo único que cambió son las notas."""
    m = _CAB_NOTAS.search(resumen or "")
    if not m:
        return resumen or ""
    fin = m.end()
    for it in _bloque_notas(resumen):
        k = resumen.find("- " + it, fin)
        if k >= 0:
            fin = k + 2 + len(it)
    return (resumen[:m.start()] + resumen[fin:]).strip()


def _clase(frase: str) -> str:
    """Agrupa la frase que cambió por el campo del estado que la escribe (heurística por texto)."""
    f = frase.lower()
    reglas = [
        ("paso de la conversación", ("paso", "step", "flujo", "esperando", "pendiente de")),
        ("grupo (cuántos)", ("persona(s)", "people in total", "son ", "grupo")),
        ("certificación", ("certificad", "principiante", "certified")),
        ("nacionalidad / moneda", ("colombian", "cop", "usd")),
        ("origen / alojamiento", ("isla", "island", "cartagena", "hotel", "hospeda", "alojamiento")),
        ("servicio elegido", ("actividad", "activity", "plan seleccionado", "selected")),
        ("inactividad / refresher", ("años", "years", "refresher", "inmersión", "dive")),
        ("edades / niños", ("edad", "age", "niñ", "kid", "hij")),
        ("notas del cliente", ("recuerd", "nota", "remember", "dijo que", "mencion")),
    ]
    for nombre, claves in reglas:
        if any(k in f for k in claves):
            return nombre
    return "otra"


async def main() -> None:
    settings.answer_and_continue = True
    settings.rag_adelantado = True
    supervisor.rag_answer = _rag
    core.compose_acknowledgement = lambda *a, **k: asyncio.sleep(0, result="")
    # Notas FIJAS (vacías): descarta su CONTENIDO como causa. `NOTAS_TARDAN` les da la latencia de una llamada
    # real (en PRE van en paralelo, `NOTES_IN_PARALLEL`): si con notas vacías pero lentas se rehace más, la causa no
    # es lo que dicen las notas sino la ESPERA, que deja a la extracción cambiar el estado entre las dos huellas.
    retardo = float(os.environ.get("NOTAS_TARDAN", "0"))
    if os.environ.get("NOTAS_REALES") == "1":
        # Tercera pasada: las notas DE VERDAD (una llamada a gpt-4o-mini por mensaje con 3+ palabras). Si ahora
        # se rehace mucho más que con notas vacías, la causa es lo que DICEN las notas.
        print(f"notas: REALES · puerta de Jev (`NOTAS_PUERTA_JEV`): {settings.notas_puerta_jev}")
        # 1-oct: se apunta CADA nota capturada (no solo las de los rehechos), para comprobar que la puerta no se come
        # las buenas. Con la puerta, los mensajes que Jev descarta ni siquiera llegan al extractor.
        _extraer = core.extract_notes

        async def _extraer_y_apuntar(message, **kw):
            notas = await _extraer(message, **kw)
            NOTAS.append({"dialogo": DIALOGO["id"], "mensaje": message, "notas": notas})
            return notas

        core.extract_notes = _extraer_y_apuntar
    else:
        core.extract_notes = lambda *a, **k: asyncio.sleep(retardo, result=[])
        print(f"notas: vacías, tardan {retardo} s")
    escalation.escalate_to_human = _noop
    supervisor.escalate_to_human = _noop
    core._adoptar_o_rehacer = _espia

    ds = dialogues()
    for did, turns in ds:  # en serie: el recurso escaso son las peticiones
        DIALOGO["id"] = did
        st = ConversationState(conversation_id=f"rag5-{did}")
        for msg in turns:
            try:
                await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {did}: {type(exc).__name__}: {exc}")

    # Todo el registro a disco: para leer los casos a mano sin repetir la pasada (20 min cada una).
    import json
    from pathlib import Path

    # `SUFIJO` (1-oct): para no pisar el registro de otra pasada (p. ej. "-con-puerta").
    nombre = f"por-que-se-rehace-{os.environ.get('NOTAS_REALES') and 'notas-reales' or 'notas-vacias'}"
    salida = Path("docs/robustness/rag-5") / f"{nombre}{os.environ.get('SUFIJO', '')}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(REGISTRO, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"registro completo -> {salida}")
    if NOTAS:
        salida_notas = salida.with_name(salida.stem + "-notas-capturadas.json")
        salida_notas.write_text(json.dumps(NOTAS, ensure_ascii=False, indent=1), encoding="utf-8")
        con = [n for n in NOTAS if n["notas"]]
        print(f"extractor llamado {len(NOTAS)} veces, con alguna nota {len(con)} -> {salida_notas}")

    rehechos = [r for r in REGISTRO if r["partes"]]
    aprov = len(REGISTRO) - len(rehechos)
    print(f"\ndiálogos {len(ds)} · turnos que llegan a usar la respuesta adelantada: {len(REGISTRO)}")
    if not REGISTRO:
        return
    print(f"  aprovechada {aprov} ({aprov / len(REGISTRO):.0%}) · rehecha {len(rehechos)} "
          f"({len(rehechos) / len(REGISTRO):.0%})")
    print("\nqué parte de la huella cambió (un turno puede tener varias):")
    for parte, n in Counter(p for r in rehechos for p in r["partes"]).most_common():
        print(f"  {parte:<10} {n}")

    clases = Counter()
    for r in rehechos:
        for f in r["aparece"] + r["desaparece"]:
            clases[_clase(f)] += 1
    if clases:
        print("\ndentro del RESUMEN, qué dato cambió (frases que aparecen o desaparecen):")
        for c, n in clases.most_common():
            print(f"  {c:<26} {n}")

    con_notas = [r for r in rehechos if "notas_antes" in r]
    solo_notas = [r for r in con_notas if r["resto_igual"]]
    print(f"\nrehechos en los que SOLO cambió el bloque de notas (el resto del resumen, idéntico): "
          f"{len(solo_notas)} de {len(rehechos)}")
    nuevo_dato = [r for r in solo_notas if set(r["notas_despues"]) - set(r["notas_antes"])]
    reescrito = [r for r in solo_notas if not (set(r["notas_despues"]) - set(r["notas_antes"]))]
    print(f"  · con una nota NUEVA (el cliente contó algo): {len(nuevo_dato)}")
    print(f"  · SIN nota nueva (mismas notas reescritas, reordenadas o quitadas): {len(reescrito)}")
    for titulo, grupo in (("NOTA NUEVA", nuevo_dato), ("SIN NOTA NUEVA", reescrito)):
        print(f"\n  --- ejemplos {titulo} ---")
        for r in grupo[:6]:
            antes, despues = r["notas_antes"], r["notas_despues"]
            print(f"  · {r['mensaje'][:78]!r}")
            for it in sorted(set(despues) - set(antes)):
                print(f"      + {it[:100]}")
            for it in sorted(set(antes) - set(despues)):
                print(f"      - {it[:100]}")
            if set(antes) == set(despues):
                print(f"      = mismas notas; mismo orden: {antes == despues}")

    print("\nejemplos:")
    for r in rehechos[:8]:
        print(f"  · {r['mensaje'][:80]!r}  [{','.join(r['partes'])}]")
        for f in r["aparece"][:2]:
            print(f"      + {f[:110]}")
        for f in r["desaparece"][:2]:
            print(f"      - {f[:110]}")


if __name__ == "__main__":
    asyncio.run(main())
