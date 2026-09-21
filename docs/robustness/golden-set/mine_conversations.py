"""G1 - Mina los chats reales de WhatsApp para convertirlos en candidatos del golden-set.

Fuente: `data/knowledge_base/conversations.json` (107 ejemplos = 50 chats reales troceados
en `_partN`). Salida: `docs/robustness/golden-set/mined-candidates.json`, que un humano cura
y vuelca en `build_golden.py` (la fuente unica del golden).

    PYTHONPATH=. python docs/robustness/golden-set/mine_conversations.py [--max-chats 30]

Que hace (todo determinista, SIN llamadas al LLM: los criterios se proponen despues):
1. Agrupa por CHAT de origen (quita el sufijo `_partN`): el split examen/entrenamiento es
   por chat, no por trozo, o se filtraria mal.
2. Trocea en turnos, tira lo trivial (solo saludos) y separa lo que escribio el CENTRO y
   quedo colado en el lado del cliente.
3. Anonimiza con `redact_pii` + enlaces/correos.
4. Etiqueta cobertura (idioma, temas, perfil, dificultad) -> insumo de G2.
5. Escribe `data/knowledge_base/golden_holdout_chats.json` con los chats elegidos, que el RAG
   excluye del few-shot (anti-contaminacion; ver `_load_conversations_cached`).

OJO AL COSTE DEL SPLIT (medido 2026-09-21): reservar 30 de los 50 chats como examen deja el
few-shot del RAG en 40 de 107 ejemplos (-63%). Es lo correcto contra la contaminacion, pero
PUEDE bajar la calidad del RAG -> hay que medirlo con `eval_rag_answers` / `eval_retrieval`
contra la linea base m0-7 ANTES de darlo por bueno, y bajar `--max-chats` si duele.

Los candidatos salen LARGOS (30-40 turnos) porque se fusionan todos los `_partN` de un chat;
los dialogos del golden actual son de 1-8 turnos. La curacion humana debe trocearlos en
segmentos con un objetivo claro, no meterlos enteros.

Lo dudoso NO se tira en silencio: se marca en `needs_review` con el motivo, para la revision
humana que pide el plan (Fase G, G1).
"""

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from src.privacy import redact_pii

SOURCE = Path("data/knowledge_base/conversations.json")
OUT = Path("docs/robustness/golden-set/mined-candidates.json")
HOLDOUT = Path("data/knowledge_base/golden_holdout_chats.json")

# El import crudo de WhatsApp trae el hablante EXPLICITO: `[1/5/26, 11:32] ~Camilo: texto`.
# Medido sobre los datos: 74 de 814 lineas traen ese formato y 49 de ellas son del CENTRO
# (contaminacion real), y 73 de las 74 son solo adjuntos sin texto. Usar el hablante es mucho
# mas fiable que adivinar por frases; el 91% restante ya es texto limpio de cliente.
EXPORT_RE = re.compile(r"^\[[^\]]+\]\s*(?P<who>[^:]{1,40}):\s*(?P<txt>.*)$")
CENTER_SPEAKER_RE = re.compile(r"diving\s*planet", re.I)
# Adjuntos / multimedia omitida: no aportan texto que probar.
PLACEHOLDER_RE = re.compile(
    r"<adjunto:|imagen omitida|audio omitido|sticker omitido|video omitido|"
    r"multimedia omitid|image omitted|audio omitted|<attached:",
    re.I,
)
# Avisos del propio WhatsApp, no los escribe nadie.
SYSTEM_RE = re.compile(
    r"cre[oó] este grupo|te a[nñ]adi[oó]|a[nñ]adi[oó] a |sali[oó] del grupo|"
    r"cambi[oó] el asunto|cambi[oó] la descripci[oó]n|mensajes .*cifrados|"
    r"created (this )?group|added you|added ~|left$|changed the subject|"
    r"messages .*end-to-end encrypted",
    re.I,
)
# Si aparece esto, el chat es de GRUPO: hablan cliente y centro sin prefijo -> revision humana.
GROUP_RE = re.compile(r"cre[oó] este grupo|created (this )?group|te a[nñ]adi[oó]|added you", re.I)
# Frases que solo dice el CENTRO y que aparecen coladas en customer.messages (los ejemplos
# curados a mano no llevan el prefijo del export, asi que aqui si hace falta la frase).
CENTER_MARKERS = (
    "sorry i missed your call", "do you speak english", "se comparte", "te comparto",
    "adjunto el link", "aqui tienes el link", "here is the link", "buenas tardes, soy",
    "gracias por escribirnos", "thank you for writing", "thank you for contacting",
    "gracias por contactarnos", "how may we help", "en que podemos ayudar",
    "nos gustaria ayudarle", "nos gustaría ayudarle", "con gusto le ayudamos",
)
# Saludos/cortesias que por si solos no son un caso de prueba.
TRIVIAL = ("hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "gracias",
           "ok", "vale", "hi", "hello", "thanks", "thank you", "perfecto", "listo")
URL_RE = re.compile(r"https?://\S+|www\.\S+|\b\S+\.(?:com|co|org|net)\b", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
MONEY_RE = re.compile(r"\$|\busd\b|\bcop\b", re.I)


def chat_id(example_id: str) -> str:
    """Chat de origen: `whatsapp_import_1_403_7957813_part3` -> sin el `_partN`."""
    return re.sub(r"_part\d+$", "", example_id)


def anonymize(text: str) -> str:
    text = URL_RE.sub("[enlace]", EMAIL_RE.sub("[correo]", text))
    return redact_pii(text).strip()


def is_trivial(turn: str) -> bool:
    low = turn.lower().strip(" .!?")
    return len(low) < 12 or low in TRIVIAL


def looks_like_center(turn: str) -> bool:
    low = turn.lower()
    return any(marker in low for marker in CENTER_MARKERS)


def clean_turns(messages: list) -> tuple[list[str], list[str]]:
    """Devuelve (turnos_del_cliente, motivos_de_revision)."""
    turns: list[str] = []
    notes: list[str] = []
    for raw in messages:
        if not isinstance(raw, str):
            continue
        # Un mensaje puede traer varias lineas pegadas (import de WhatsApp).
        for line in (ln.strip() for ln in raw.splitlines()):
            if not line:
                continue
            # 1) Formato export: el hablante viene dado, no hay que adivinarlo.
            if export := EXPORT_RE.match(line):
                who, line = export.group("who").strip(), export.group("txt").strip()
                if CENTER_SPEAKER_RE.search(who):
                    notes.append("linea del CENTRO descartada (" + who + "): " + line[:50])
                    continue
                if not line:
                    continue
            # 2) Adjuntos / multimedia y avisos del sistema: no hay texto que probar.
            if PLACEHOLDER_RE.search(line):
                continue
            if SYSTEM_RE.search(line):
                # En un chat de GRUPO hablan cliente y centro sin prefijo: no se puede separar
                # de forma fiable, asi que se marca para que lo mire una persona.
                if GROUP_RE.search(line):
                    notes.append("CHAT DE GRUPO: revisar turno a turno quien habla (cliente vs centro)")
                continue
            # 3) Ejemplos curados: aqui si hay que reconocer al centro por la frase.
            if looks_like_center(line):
                notes.append("linea del centro descartada: " + line[:60])
                continue
            clean = anonymize(line)
            if not clean or is_trivial(clean):
                continue
            # Se AVISA (no se tira): un cliente puede citar un precio legitimamente.
            if MONEY_RE.search(clean):
                notes.append("menciona dinero, revisar de quien es: " + clean[:60])
            turns.append(clean)
    return turns, notes


def profile_of(turns: list[str], topics: list[str]) -> str:
    joined = " ".join(turns).lower()
    if any(w in joined for w in ("nino", "nina", "hijo", "hija", "kid", "child", "familia", "family")):
        return "familia"
    if "certification" in topics and any(w in joined for w in ("principiante", "beginner", "nunca")):
        return "grupo_mixto"
    if any(w in joined for w in ("somos", "grupo", "we are", "group", "amigos", "friends")):
        return "grupo"
    return "solo"


def build(max_chats: int) -> dict:
    examples = json.loads(SOURCE.read_text(encoding="utf-8"))["conversation_examples"]
    by_chat: dict[str, list[dict]] = {}
    for ex in examples:
        by_chat.setdefault(chat_id(ex["id"]), []).append(ex)

    candidates = []
    for cid, parts in by_chat.items():
        turns: list[str] = []
        notes: list[str] = []
        center: list[str] = []
        topics: list[str] = []
        for part in sorted(parts, key=lambda p: p["id"]):
            part_turns, part_notes = clean_turns((part.get("customer") or {}).get("messages") or [])
            turns += part_turns
            notes += part_notes
            center += [
                anonymize(m)
                for m in ((part.get("diving_planet") or {}).get("messages") or [])
                if isinstance(m, str)
            ]
            topics += part.get("extracted_topics") or []
        if not turns:
            continue
        topics = sorted(set(topics))
        lang = Counter(p.get("lang") for p in parts).most_common(1)[0][0]
        candidates.append({
            "id": "real-" + cid,
            "chat_id": cid,
            "lang": lang,
            "turns": turns,
            # Respuesta real del equipo: base para proponer criterios (la KB manda si discrepan).
            "center_reference": center,
            "coverage": {
                "topics": topics,
                "lang": lang,
                "profile": profile_of(turns, topics),
                "difficulty": "alta" if len(turns) >= 6 else "media" if len(turns) >= 3 else "baja",
            },
            "needs_review": sorted(set(notes)),
        })

    # Seleccion: primero los chats con mas recorrido y mas temas (mas sustancia por caso),
    # respetando la proporcion real de idiomas (65 ES / 42 EN ~ 60/40).
    candidates.sort(key=lambda c: (len(c["turns"]), len(c["coverage"]["topics"])), reverse=True)
    quota_es = round(max_chats * 0.6)
    picked: list[dict] = []
    n_es = n_en = 0
    for cand in candidates:
        if len(picked) >= max_chats:
            break
        if cand["lang"] == "es" and n_es < quota_es:
            picked.append(cand)
            n_es += 1
        elif cand["lang"] != "es" and n_en < max_chats - quota_es:
            picked.append(cand)
            n_en += 1
    chosen = {c["chat_id"] for c in picked}
    for cand in candidates:  # rellena si una cuota se quedo corta
        if len(picked) >= max_chats:
            break
        if cand["chat_id"] not in chosen:
            picked.append(cand)
            chosen.add(cand["chat_id"])

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(SOURCE).replace("\\", "/"),
        "about": ("G1: candidatos del golden-set minados de chats reales. Curar a mano y volcar en "
                  "build_golden.py. Los chat_id elegidos quedan fuera del few-shot del RAG "
                  "(golden_holdout_chats.json) para no inflar la nota."),
        "chats_total": len(by_chat),
        "chats_con_contenido": len(candidates),
        "seleccionados": len(picked),
        "candidates": picked,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-chats", type=int, default=30)
    args = ap.parse_args()

    result = build(args.max_chats)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    HOLDOUT.write_text(json.dumps({
        "about": ("Chats reales reservados como EXAMEN (golden-set). El RAG los excluye del few-shot "
                  "para que el examen no puntue sobre ejemplos que el propio modelo ya ve. "
                  "Lo genera docs/robustness/golden-set/mine_conversations.py (Fase G, G1)."),
        "holdout_chat_ids": sorted(c["chat_id"] for c in result["candidates"]),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    con_avisos = sum(1 for c in result["candidates"] if c["needs_review"])
    print(f"{result['chats_total']} chats -> {result['chats_con_contenido']} con contenido -> "
          f"{result['seleccionados']} seleccionados ({con_avisos} con avisos de revision)")
    print("idiomas:", Counter(c["lang"] for c in result["candidates"]))
    print("escrito", OUT, "y", HOLDOUT)
