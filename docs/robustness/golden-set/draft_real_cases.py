"""G1 (Fase G), paso 2: de episodio real (real-episodes.json) a BORRADOR de caso del golden-set.

Un LLM (gpt-5, low) lee cada episodio con la MISMA referencia que usa el juez (KB + catalogo actuales)
y propone: si entra o no, categoria, etiquetas de cobertura (G2), los turnos a usar (subsecuencia
LITERAL de los del cliente, recortada) y criterios al estilo del golden. Los precios del chat son
antiguos: la referencia historica del centro dice QUE responder, los importes los manda el catalogo.

Salida: real-cases-draft.json (borrador). No entra al golden hasta revision humana; las `dudas`
de cada caso son las preguntas para esa revision.

    ENV_FILE=.env.dev python docs/robustness/golden-set/draft_real_cases.py [--ids wa-01-e1,...] [--limit N]
"""

import argparse
import difflib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))

from scripts.judge_golden_set import load_reference  # noqa: E402
from scripts.langfuse_snapshot import _env  # noqa: E402

EPISODES = HERE / "real-episodes.json"
GOLDEN = HERE / "golden-dialogues.json"
OUT = HERE / "real-cases-draft.json"
MODEL, EFFORT = "gpt-5", "low"
MAX_TURNS = 10
VALID_AUTO = {"last_reply_has_booking_link"}
AMOUNT_RE = re.compile(
    r"(U?S?\$|USD|COP)\s?\d|\d[\d.,]*\s?(USD|COP|d[oó]lares|pesos)|\d\s?%", re.IGNORECASE
)

CATEGORIES = [
    "saludo",
    "reserva",
    "info",
    "grupo",
    "escalado",
    "seguridad",
    "refresher",
    "edades",
    "nacionalidad",
    "descuentos",
    "cambios",
    "deflection",
    "tras-link",
    "idioma",
    "adaptado",
    # nuevas por los chats reales
    "post-venta",
    "logistica",
    "pago",
    "curso",
]
INTENTS = [
    "precio",
    "disponibilidad",
    "reserva",
    "info-actividad",
    "certificacion-curso",
    "logistica-recogida",
    "punto-encuentro",
    "alojamiento-islas",
    "pago",
    "descuento",
    "equipo",
    "fotos",
    "formularios",
    "cambio-cancelacion",
    "post-venta",
    "seguridad-medico",
    "clima",
    "queja",
    "otro",
]

INSTRUCTIONS = f"""Eres el autor del golden-set de Coral, el bot de WhatsApp del centro de buceo Diving Planet
(Cartagena, Colombia). Conviertes una conversacion REAL e historica entre un cliente y el equipo humano
del centro en un caso de prueba para el BOT: los mensajes del cliente se le enviaran al bot, en orden,
y un juez comprobara tus criterios sobre las respuestas del bot.

Reglas:
1. La REFERENCIA (abajo) es la verdad ACTUAL. Las respuestas del centro en el chat son historicas: sirven
   para saber QUE necesitaba el cliente, NO como respuesta esperada. Sus precios y descuentos estan
   marcados [precio histórico: ...] / [descuento histórico: ...]: pueden estar obsoletos o seguir
   vigentes; jamas los uses en un criterio, manda la referencia. Si el cliente cita un importe o
   descuento, un buen criterio es que el bot se atenga a la referencia (confirmarlo solo si coincide).
1b. El bot trabaja por pasos: para cotizar necesita actividad, personas, desde donde sale (Cartagena o
   islas) y nacionalidad (moneda). Si al cliente le falta dar un dato que el bot necesita, PREGUNTARLO es
   una respuesta correcta: escribe el criterio como "da X, o pregunta el dato que le falta para darlo".
   Nunca exijas que el bot adivine datos que el cliente no ha dado.
2. El bot no es el equipo humano: no ve reservas existentes, no confirma disponibilidad en tiempo real
   de cosas fuera de la referencia, no comparte contactos de hoteles, no recibe pagos ni documentos.
   Cuando el cliente necesite eso, lo esperado es lo que diga la referencia (escalation_rules y
   politicas): normalmente pasar a una persona, sin inventar. No castigues al bot por no hacer lo que
   hizo el humano; exige lo que un buen bot DEBE hacer con esta referencia.
3. Turnos: una SUBSECUENCIA LITERAL de los mensajes del cliente (copiados exactos, sin reescribir), como
   mucho {MAX_TURNS}. Quita lo que no tiene sentido para el bot: respuestas a preguntas muy concretas
   del humano que el bot no haria, confirmaciones de pagos o llamadas ya hechas, despedidas sueltas,
   mensajes que solo son [imagen]/[contacto]. Corta en un punto natural (p. ej. tras pedir pagar).
4. Criterios: de 1 a 3 (mejor 2 buenos que 3 flojos), en espanol, al estilo de los EJEMPLOS.
   - Prioriza lo mas ARRIESGADO para el bot: premisas falsas o importes/descuentos que cita el
     cliente, peticiones que exigen pasar a una persona, datos que un bot tiende a inventar. Si el
     episodio trae el aviso cliente_cita_precio, UNO de los criterios es obligatoriamente que el bot
     no de por bueno ese importe/descuento sin mas y se atenga a la referencia.
   - SOLO lo que el cliente PREGUNTO o pidio de forma explicita. Si no pregunto el punto de encuentro,
     el precio o el link, no los exijas. Un cliente que solo dice "busco snorkel" espera que el bot le
     guie (pregunte o de opciones), no una lista de datos.
   - UN solo dato de la referencia por criterio (no "punto, hora y regreso" juntos: elige el que el
     cliente pregunto).
   - Si la referencia permite RESPONDER, exige la respuesta y acepta pasar a una persona como
     alternativa valida; exige el pase a una persona solo cuando la referencia (escalation_rules) lo
     pide o cuando el bot no puede resolverlo (reservas existentes, pagos hechos, cambios de una
     reserva). No exijas a la vez responder Y escalar.
   - Cada criterio debe estar respaldado por un dato EXPLICITO de la referencia: pon en "base" la cita
     literal corta (fichero + texto). Si lo que esperarias no esta en la referencia (p. ej. pedir datos
     al escalar, recomendar o no a terceros, una politica que no aparece), NO lo pongas como criterio:
     llevalo a "dudas".
   - NUNCA escribas importes ni porcentajes concretos: di "el precio del catalogo para X" o "el
     descuento que indique la referencia". Los importes ya los comprueba el criterio global por codigo.
   - Cada fallo del bot debe caer en UN solo criterio. Si depende de que la conversacion llegue a un
     punto, dilo ("si la conversacion acaba antes, no aplica").
   - NO repitas los criterios GLOBALES (ya se juzgan siempre): idioma, sin-invenciones, importes del
     catalogo, un-saludo, sin-repreguntas, sin-fugas.
   - "auto": "last_reply_has_booking_link" solo si el ULTIMO turno pide pagar/reservar y lo correcto
     es dar el link; en cualquier otro caso omite la clave "auto".
5. Descarta el episodio (incluir=false) si no aporta un caso util para el bot: solo operativa de una
   reserva ya pagada que el bot no puede tocar y no ensena nada, chat entre empresas, contenido
   ininteligible, turnos que no se entienden sin los mensajes del humano ("ya quedo", "¿lo recibiste
   ahora?", "yendo"), o duplicado evidente de un caso del golden actual o de otro episodio mas claro.
   Se exigente: es mejor un golden de 40 casos nitidos que de 75 dudosos. Un caso de post-venta SI es util
   si lo correcto es algo concreto (p. ej. pasar a una persona sin inventar el estado de la reserva).
6. dudas: preguntas CONCRETAS para el revisor humano cuando la referencia no resuelve lo que el bot
   deberia hacer (p. ej. una politica que no aparece). Vacio si no hay dudas.

7. Decisiones del negocio (Gadea, 22-sep) para escribir criterios:
   - Fotos/videos: basta con explicar la politica, pero ENFOCADA a lo que pregunta el cliente (no
     copiar y pegar la politica entera).
   - Al pasar a una persona por una reserva existente, el bot NO tiene que pedir datos: el asesor
     recibe el resumen de la conversacion.
   - Cliente enfermo o indispuesto que quiere cambiar la fecha: solo pasa a una persona (no da
     consejo medico ni recomienda bucear o no).
   - Maletas, regreso en otra fecha y cedula de extranjeria: ver luggage_policy, return_different_day
     y colombian_pricing en la referencia.

Devuelve SOLO JSON:
{{"incluir": bool, "motivo": "por que entra o no (1 frase)",
  "id": "kebab-case corto y descriptivo en espanol (sin nombres de personas)",
  "category": una de {CATEGORIES},
  "cobertura": {{"intents": [de {INTENTS}], "actividad": "buceo-certificado|minicurso|curso-open-water|snorkel|acompanante|varias|ninguna",
                "perfil": "solo|pareja|familia|grupo|grupo-mixto|desconocido", "etapa": "pre-venta|post-venta",
                "dificultad": "facil|media|dificil"}},
  "turns": ["...literal..."],
  "criteria": [{{"id": "kebab", "check": "...", "base": "fichero: cita literal corta"}}],
  "dudas": ["..."]}}
"""


def _examples() -> str:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    pick = {
        "punto-encuentro",
        "premisa-falsa-lunes",
        "clima-manana",
        "link-roto-carrito",
        "manual-duracion-curso",
        "reserva-solo-link",
        "embarazo",
    }
    ex = [
        {k: d[k] for k in ("id", "category", "turns", "criteria") if k in d}
        for d in golden["dialogues"]
        if d["id"] in pick
    ]
    return (
        "CRITERIOS GLOBALES (ya se juzgan siempre, no los repitas):\n"
        + json.dumps(golden["global_criteria"], ensure_ascii=False)
        + "\n\nEJEMPLOS de casos del golden actual:\n"
        + json.dumps(ex, ensure_ascii=False, indent=0)
        + "\n\nIDs ya existentes (no dupliques): "
        + ", ".join(d["id"] for d in golden["dialogues"])
    )


VOICE_PREFIX = "[nota de voz] "


def customer_messages(ep: dict) -> list[str]:
    """Lo que el cliente mando, tal cual le llegaria al bot: las notas de voz van como su
    transcripcion (el bot recibe texto), sin el marcador."""
    return [
        t["text"].removeprefix(VOICE_PREFIX)
        for t in ep["transcript"]
        if t["role"] == "cliente" and t["text"] != "[llamada]"
    ]


def anchor_turns(turns: list[str], ep: dict) -> tuple[list[str], list[str]]:
    """Ancla cada turno del borrador a su mensaje ORIGINAL completo. El LLM a veces trocea un
    mensaje multilinea, lo recorta o corrompe tildes; el caso debe mandar exactamente lo que el
    cliente escribio. Devuelve (turnos anclados, turnos que no se pudieron anclar)."""
    originals = customer_messages(ep)

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    anchored, orphans = [], []
    for turn in turns:
        t = norm(turn.removeprefix(VOICE_PREFIX))
        match = next((o for o in originals if t and t in norm(o)), None)
        if match is None:
            scored = [(difflib.SequenceMatcher(None, turn, o).ratio(), o) for o in originals]
            score, best = max(scored) if scored else (0, None)
            match = best if score >= 0.85 else None
        if match is None:
            orphans.append(turn)
        elif not anchored or anchored[-1] != match:
            anchored.append(match)
    return anchored, orphans


def postprocess(draft: dict, ep: dict) -> dict:
    """Comprobaciones por codigo sobre el borrador (idempotente: se puede re-aplicar con --repair)."""
    turns, orphans = anchor_turns(draft.get("turns", []), ep)
    draft["turns"] = turns
    for c in draft.get("criteria", []):
        if c.get("auto") not in VALID_AUTO:
            c.pop("auto", None)  # un auto vacio o inventado romperia al juez
    draft["_checks"] = {
        "turnos_sin_anclar": orphans,
        "n_turnos": len(turns),
        "importes_en_criterio": [
            c["id"] for c in draft.get("criteria", []) if AMOUNT_RE.search(c.get("check", ""))
        ],
        "categoria_desconocida": draft.get("category") not in CATEGORIES,
    }
    return draft


def render_episode(ep: dict) -> str:
    lines = [f"Episodio {ep['id']} ({ep['month']}), avisos: {', '.join(ep['flags']) or 'ninguno'}"]
    lines += [f"{t['role'].upper()}: {t['text']}" for t in ep["transcript"]]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids", help="solo estos episodios (coma)")
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--repair", action="store_true", help="solo re-aplica las comprobaciones por codigo"
    )
    args = ap.parse_args()

    episodes = json.loads(EPISODES.read_text(encoding="utf-8"))["episodes_list"]
    if args.repair:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        by_id = {e["id"]: e for e in episodes}
        data["drafts"] = {k: postprocess(v, by_id[k]) for k, v in data["drafts"].items()}
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        bad = {
            k: v["_checks"]["turnos_sin_anclar"]
            for k, v in data["drafts"].items()
            if v["_checks"]["turnos_sin_anclar"]
        }
        print(f"{len(data['drafts'])} borradores revisados; turnos sin anclar: {bad or 'ninguno'}")
        return

    from openai import OpenAI

    client = OpenAI(api_key=_env("OPENAI_API_KEY"))
    if args.ids:
        wanted = set(args.ids.split(","))
        episodes = [e for e in episodes if e["id"] in wanted]
    episodes = episodes[: args.limit] if args.limit else episodes

    drafts = json.loads(OUT.read_text(encoding="utf-8"))["drafts"] if OUT.exists() else {}
    # referencia + instrucciones primero y fijas: la cache de prompts de OpenAI las reutiliza
    system = f"{INSTRUCTIONS}\n\n{_examples()}\n\nREFERENCIA (verdad actual):\n{load_reference()}"
    usage = {"input": 0, "cached": 0, "output": 0}
    for i, ep in enumerate(episodes, 1):
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            reasoning_effort=EFFORT,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": render_episode(ep)},
            ],
        )
        u = resp.usage
        usage["input"] += u.prompt_tokens
        usage["cached"] += getattr(u.prompt_tokens_details, "cached_tokens", 0) or 0
        usage["output"] += u.completion_tokens
        draft = json.loads(resp.choices[0].message.content or "{}")
        draft["episode"] = ep["id"]
        draft["flags"] = ep["flags"]
        drafts[ep["id"]] = postprocess(draft, ep)
        OUT.write_text(
            json.dumps(
                {"model": f"{MODEL} ({EFFORT})", "drafts": drafts}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
        )
        mark = "+" if draft.get("incluir") else "-"
        print(
            f"{i}/{len(episodes)} {mark} {ep['id']} -> {draft.get('id')} [{draft.get('category')}] "
            f"{len(draft.get('turns', []))}t {len(draft.get('criteria', []))}c dudas={len(draft.get('dudas', []))} "
            f"{'SIN-ANCLAR ' if draft['_checks']['turnos_sin_anclar'] else ''}{time.time() - t0:.0f}s"
        )
    cost = (
        (usage["input"] - usage["cached"]) * 1.25 + usage["cached"] * 0.125 + usage["output"] * 10
    ) / 1e6
    print(f"tokens {usage} ~{cost:.2f} $")


if __name__ == "__main__":
    main()
