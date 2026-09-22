"""G1 (Fase G): convierte los exports ORIGINALES de WhatsApp en episodios reales para el golden-set.

Independiente de `mine_conversations.py` (que parte del import ya recortado de conversations.json):
aqui la fuente son los `_chat.txt` completos que exporta WhatsApp, con hablante y hora exactos,
mas los adjuntos (las notas de voz se transcriben). Asi se pueden comparar los dos minados.

Privacidad: la carpeta de exports NO entra nunca en el repo. Todo lo que lleva datos personales
(transcripciones, nombres detectados, mapa chat -> numero) se guarda en `<src>/_coral/`, junto a los
originales. Al repo solo llega `real-episodes.json`, anonimizado.

    ENV_FILE=.env.dev python docs/robustness/golden-set/mine_whatsapp_exports.py transcribe --src <carpeta>
    ENV_FILE=.env.dev python docs/robustness/golden-set/mine_whatsapp_exports.py build --src <carpeta>

Un episodio = una consulta independiente dentro de un chat: se corta cuando pasan >= GAP_HOURS sin
mensajes y quien retoma es el cliente. Cada mensaje del cliente es un turno (el bot no agrupa
mensajes: en PRE cada mensaje de WhatsApp es un turno, asi que las rafagas se conservan).
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.langfuse_snapshot import _env  # noqa: E402

OUT = Path(__file__).parent / "real-episodes.json"
CENTER = "DIVING PLANET CARTAGENA"
GAP_HOURS = 72
TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
LLM_MODEL = "gpt-4.1-mini"

LINE_RE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{2}), (\d{1,2}):(\d{2}):(\d{2})\s?([ap])\.\s?m\.\] ([^:]+?): ?(.*)$"
)
ATTACH_RE = re.compile(r"<adjunto: ([^>]+)>")
SYSTEM_RE = re.compile(
    r"cifrados de extremo a extremo|end-to-end encrypted|creó este grupo|te añadió|añadió a "
)
DELETED_RE = re.compile(
    r"^(Eliminaste este mensaje|Se eliminó este mensaje|This message was deleted|You deleted this message)\.?$"
)
CALL_RE = re.compile(r"^(Llamada|Videollamada|Missed (voice|video) call|Voice call|Video call)\b")
WELCOME_RE = re.compile(r"Welcome to Diving Planet|Bienvenid@ a Diving Planet", re.IGNORECASE)

EMAIL_RE = re.compile(r"[\w.%+-]+@[\w.-]+\.[a-z]{2,}", re.IGNORECASE)
AT_DOMAIN_RE = re.compile(r"@[\w-]+\.[a-z]{2,}", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
LONG_ID_RE = re.compile(r"\b\d{8,}\b")

# Precios y descuentos de chats de 2025-26: pueden estar obsoletos (o seguir vigentes, como el 10 %
# online). En la respuesta del centro se marcan como "historicos" para que nadie (ni el LLM que
# redacte criterios) los tome como referencia: manda el catalogo actual. En los turnos del cliente
# se dejan tal cual (es lo que escribiria) y se marca el episodio: el bot debe atenerse al catalogo
# y no dar por bueno el importe que cita el cliente sin comprobarlo.
_NUM_WORD = (
    r"(?:un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cien|ciento|doscientos|trescientos|"
    r"cuatrocientos|quinientos|seiscientos|setecientos|ochocientos|novecientos|veinte|treinta|"
    r"cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|mil|millón|millones)"
)
MONEY_RE = re.compile(
    r"(?:US\$|USD|COP|\$)\s?\d[\d.,]*(?:\s?(?:USD|COP)\b)?"
    r"|\b\d[\d.,]*\s?(?:de\s|US\s?)?(?:USD|COP|d[oó]lares|dollars|pesos|mil)\b"
    r"|\b\d{1,3}(?:[.,]\d{3})+\b"
    # dicho con palabras (notas de voz transcritas): "dos millones cien mil pesos"
    rf"|\b{_NUM_WORD}(?:\s+(?:{_NUM_WORD}|y|de))*\s+(?:pesos|d[oó]lares)\b",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b\d{1,2}\s?%")


def mark_old_prices(text: str) -> str:
    text = MONEY_RE.sub(lambda m: f"[precio histórico: {m.group(0).strip()}]", text)
    return PERCENT_RE.sub(lambda m: f"[descuento histórico: {m.group(0)}]", text)


# --------------------------------------------------------------------------- parseo


def _clean(text: str) -> str:
    for ch in ("\u200e", "\u2068", "\u2069", "\r"):
        text = text.replace(ch, "")
    return text.replace("\u202f", " ").strip()


def parse_chat(path: Path) -> list[dict]:
    """Mensajes del `_chat.txt`: {at, speaker, text, attachment}. Las lineas sin cabecera continuan
    el mensaje anterior (mensajes multilinea)."""
    msgs: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = _clean(raw)
        m = LINE_RE.match(line)
        if not m:
            if msgs and line:
                msgs[-1]["text"] += "\n" + line
            continue
        mo, dd, yy, hh, mi, ss, ap, speaker, text = m.groups()
        hour = int(hh) % 12 + (12 if ap == "p" else 0)
        at = datetime(2000 + int(yy), int(mo), int(dd), hour, int(mi), int(ss))
        msgs.append({"at": at, "speaker": speaker.strip().lstrip("~").strip(), "text": text})
    for msg in msgs:
        msg["text"] = msg["text"].replace("<Se editó este mensaje.>", "").strip()
        att = ATTACH_RE.search(msg["text"])
        msg["attachment"] = att.group(1) if att else None
        if att:
            msg["text"] = ATTACH_RE.sub("", msg["text"]).strip()
    return msgs


def attachment_kind(name: str | None, text: str) -> str | None:
    if name:
        up = name.upper()
        if "AUDIO" in up or up.endswith(".OPUS"):
            return "audio"
        if "STICKER" in up:
            return "sticker"
        if "PHOTO" in up or up.endswith((".JPG", ".JPEG", ".PNG")):
            return "imagen"
        if "VIDEO" in up or up.endswith(".MP4"):
            return "video"
        if up.endswith(".VCF"):
            return "contacto"
        return "documento"
    if re.fullmatch(
        r"(imagen|image|video|audio|sticker|GIF) (omitid[oa]|omitted)", text, re.IGNORECASE
    ):
        word = text.split()[0].lower()
        return "imagen" if word == "image" else word
    return None


# --------------------------------------------------------------------------- transcripcion


def _private_dir(src: Path) -> Path:
    d = src / "_coral"
    d.mkdir(exist_ok=True)
    return d


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
    )


def _client():
    from openai import OpenAI

    key = _env("OPENAI_API_KEY")
    if not key:
        raise SystemExit("Falta OPENAI_API_KEY (usa ENV_FILE=.env.dev).")
    return OpenAI(api_key=key)


def transcribe(src: Path) -> None:
    """Transcribe cada .opus una sola vez (cache en _coral/transcripts.json, fuera del repo)."""
    cache_path = _private_dir(src) / "transcripts.json"
    cache = _load(cache_path)
    audios = sorted(p for p in src.glob("*/*.opus") if f"{p.parent.name}/{p.name}" not in cache)
    print(f"{len(cache)} ya transcritos, {len(audios)} pendientes")
    client = _client()
    for i, p in enumerate(audios, 1):
        key = f"{p.parent.name}/{p.name}"
        try:
            r = client.audio.transcriptions.create(
                model=TRANSCRIBE_MODEL, file=(p.stem + ".ogg", p.read_bytes(), "audio/ogg")
            )
            cache[key] = r.text.strip()
        except Exception as exc:  # un audio roto no para el lote
            cache[key] = None
            print(f"  ERROR {key}: {exc}")
        _save(cache_path, cache)
        print(f"  {i}/{len(audios)} {p.name}: {(cache[key] or '')[:70]!r}")


# --------------------------------------------------------------------------- anonimizacion


def _names_by_llm(client, chat_text: str) -> list[str]:
    """Nombres de PERSONAS que aparecen en el chat (clientes, acompanantes, staff). Los hoteles,
    islas y empresas no son datos personales y se conservan."""
    r = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Extrae datos personales de este chat de WhatsApp para anonimizarlo. Devuelve JSON "
                    '{"names": [...], "other": [...]}. names: cada nombre o apellido de PERSONA tal como '
                    "aparece escrito (clientes, acompanantes, instructores, familiares), incluidos apodos. "
                    "other: numeros de documento, pasaporte, cuentas, codigos de reserva, direcciones "
                    "postales exactas, matriculas. NO incluyas hoteles, islas, lugares, empresas, "
                    "certificaciones (PADI, Open Water) ni 'Diving Planet'."
                ),
            },
            {"role": "user", "content": chat_text[:60000]},
        ],
    )
    data = json.loads(r.choices[0].message.content or "{}")
    return [
        s
        for s in (data.get("names") or []) + (data.get("other") or [])
        if isinstance(s, str) and len(s) > 1
    ]


NOT_PERSONAL = {
    "mi tio",
    "michael kors",
    "info@divingplanet.org",
    "oficina@divingplanet.org",
    "dan insurance policy #",
}
PARTICLES = {"de", "del", "la", "las", "los", "y", "da", "dos", "van"}
# Palabras que salen al trocear nombres de contactos/hablantes pero son del negocio, lugares o
# palabras comunes: nunca se tapan sueltas (el nombre completo sí).
NOT_A_NAME = {
    "diving",
    "planet",
    "cartagena",
    "reservas",
    "cocoliso",
    "hotel",
    "rosario",
    "baru",
    "barú",
    "dan",
    "insurance",
    "policy",
    "hope",
    "blanco",
    "blanca",
    "toro",
    "guerra",
    "marco",
    "pato",
    "isa",
    "mar",
}


def personal_terms(raw: list[str]) -> set[str]:
    """Limpia lo que devuelve el LLM + hablantes: fuera precios, fechas, medidas y los datos del propio
    centro; dentro cada nombre completo y sus partes (el apellido suelto tambien identifica)."""
    terms: set[str] = set()
    for item in raw:
        item = (item or "").strip().strip("~").strip()
        if (
            len(item) <= 2
            or item.lower() in NOT_PERSONAL
            or not re.search(r"[A-Za-zÀ-ÿ]", item)
            or re.fullmatch(r"[\d\s.,’'-]+(lb|kg|cm)?", item, re.IGNORECASE)
            or re.search(
                r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d",
                item,
                re.IGNORECASE,
            )
        ):
            continue
        if " " not in item and item.lower() in NOT_A_NAME:
            continue
        terms.add(item)
        if " " in item and "@" not in item:
            terms.update(
                p
                for p in item.split()
                if len(p) > 2
                and p.lower() not in PARTICLES | NOT_A_NAME
                and re.search(r"[A-Za-zÀ-ÿ]", p)
            )
    return terms


def make_anonymizer(names):
    """Nombres completos: sin distinguir mayusculas. Una sola palabra: solo con mayuscula inicial
    ("Hope" nombre vs "I hope"), salvo que el propio termino venga en minusculas (el LLM lo vio asi)."""
    ordered = sorted({n.strip() for n in names if n and len(n.strip()) > 1}, key=len, reverse=True)
    patterns = [
        re.compile(
            rf"(?<!\w){re.escape(n)}(?!\w)",
            0 if (" " not in n and n[:1].isupper()) else re.IGNORECASE,
        )
        for n in ordered
    ]

    def anon(text: str) -> str:
        out = EMAIL_RE.sub("[EMAIL]", text)
        out = AT_DOMAIN_RE.sub("[EMAIL]", out)
        out = URL_RE.sub(
            lambda m: m.group(0) if "divingplanet" in m.group(0).lower() else "[ENLACE]", out
        )
        out = PHONE_RE.sub(
            lambda m: "[TELEFONO]" if len(re.sub(r"\D", "", m.group(0))) >= 9 else m.group(0), out
        )
        out = LONG_ID_RE.sub("[NUMERO]", out)
        for pat in patterns:
            out = pat.sub("[NOMBRE]", out)
        return out

    return anon


# --------------------------------------------------------------------------- episodios


def _render(msg: dict, transcripts: dict, chat_dir: str) -> str | None:
    """Texto que 've' el bot por un mensaje: el propio texto o un marcador del adjunto."""
    kind = attachment_kind(msg["attachment"], msg["text"])
    if kind == "sticker" or DELETED_RE.search(msg["text"]):
        return None
    if CALL_RE.match(msg["text"]):
        return "[llamada]"
    if kind == "audio":
        t = transcripts.get(f"{chat_dir}/{msg['attachment']}")
        return f"[nota de voz] {t}" if t else "[nota de voz sin transcribir]"
    if kind:
        return f"[{kind}]" + (
            f" {msg['text']}"
            if msg["text"] and not re.search("omitid|omitted", msg["text"])
            else ""
        )
    return msg["text"] or None


def split_episodes(msgs: list[dict]) -> list[list[dict]]:
    episodes: list[list[dict]] = []
    for msg in msgs:
        new = not episodes or (
            msg["speaker"] != CENTER
            and (msg["at"] - episodes[-1][-1]["at"]).total_seconds() >= GAP_HOURS * 3600
        )
        if new:
            episodes.append([])
        episodes[-1].append(msg)
    return episodes


def build(src: Path) -> None:
    priv = _private_dir(src)
    transcripts = _load(priv / "transcripts.json")
    names_cache = _load(priv / "names.json")
    chat_map: dict[str, str] = {}
    client = None
    chats = []
    for d in sorted(p for p in src.iterdir() if (p / "_chat.txt").exists()):
        msgs = [m for m in parse_chat(d / "_chat.txt") if not SYSTEM_RE.search(m["text"])]
        if msgs:
            chats.append((d, msgs))
    chats.sort(key=lambda c: c[1][0]["at"])  # id por orden de fecha: no deriva del numero

    # Pasada 1: texto que ve el bot + datos personales de cada chat. Se juntan TODOS: un nombre
    # detectado en un chat (p. ej. un instructor) tambien aparece en otros.
    raw_terms: list[str] = []
    for d, msgs in chats:
        for m in msgs:
            m["rendered"] = _render(m, transcripts, d.name)
        if d.name not in names_cache:
            client = client or _client()
            text = "\n".join(f"{m['speaker']}: {m['rendered']}" for m in msgs if m["rendered"])
            names_cache[d.name] = _names_by_llm(client, text)
            _save(priv / "names.json", names_cache)
        raw_terms += names_cache[d.name]
        raw_terms += [m["speaker"] for m in msgs if m["speaker"] != CENTER]
        raw_terms += [
            re.sub(r"^\d+-|\.vcf$", "", m["attachment"])
            for m in msgs
            if (m["attachment"] or "").endswith(".vcf")
        ]
        raw_terms.append(d.name.removeprefix("WhatsApp Chat - "))
    anon = make_anonymizer(personal_terms(raw_terms))

    episodes_out = []
    for n, (d, msgs) in enumerate(chats, 1):
        chat_id = f"wa-{n:02d}"
        chat_map[chat_id] = d.name
        speakers = {m["speaker"] for m in msgs if m["speaker"] != CENTER}
        for k, ep in enumerate(split_episodes(msgs), 1):
            customer = [
                m
                for m in ep
                if m["speaker"] != CENTER and m["rendered"] and m["rendered"] != "[llamada]"
            ]
            if not customer:
                continue
            transcript = []
            for m in ep:
                if not m["rendered"]:
                    continue
                role = "centro" if m["speaker"] == CENTER else "cliente"
                text = (
                    "[bienvenida automática]"
                    if role == "centro" and WELCOME_RE.search(m["rendered"])
                    else anon(m["rendered"])
                )
                if role == "centro":
                    text = mark_old_prices(text)
                transcript.append(
                    {"role": role, "text": text, "at": m["at"].strftime("%Y-%m-%d %H:%M")}
                )
            flags = []
            if len(speakers) > 1:
                flags.append("chat_de_grupo")
            if any("[nota de voz" in m["rendered"] for m in customer):
                flags.append("audio_transcrito")
            if any(
                re.match(r"\[(imagen|documento|video|contacto)\]", m["rendered"]) for m in customer
            ):
                flags.append("adjuntos")
            if any(m["rendered"] == "[llamada]" for m in ep):
                flags.append("llamada")  # parte de la conversacion paso por telefono
            if any(
                MONEY_RE.search(m["rendered"]) or PERCENT_RE.search(m["rendered"]) for m in customer
            ):
                flags.append("cliente_cita_precio")
            if any(
                "[precio histórico" in t["text"] or "[descuento histórico" in t["text"]
                for t in transcript
            ):
                flags.append("referencia_con_precios_historicos")
            if len(customer) > 15:
                flags.append("largo")
            if not any(
                t["role"] == "centro" and t["text"] != "[bienvenida automática]" for t in transcript
            ):
                flags.append("sin_respuesta_del_centro")
            episodes_out.append(
                {
                    "id": f"{chat_id}-e{k}",
                    "chat_id": chat_id,
                    "episode": k,
                    "month": ep[0]["at"].strftime("%Y-%m"),
                    "turns": [
                        t["text"]
                        for t in transcript
                        if t["role"] == "cliente" and t["text"] != "[llamada]"
                    ],
                    "transcript": transcript,
                    "flags": flags,
                }
            )

    _save(priv / "chat_map.json", chat_map)
    usable = [e for e in episodes_out if "sin_respuesta_del_centro" not in e["flags"]]
    OUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source": "exports originales de WhatsApp (fuera del repo); ver cabecera de mine_whatsapp_exports.py",
                "about": (
                    "G1: episodios reales anonimizados, candidatos al golden-set. Nombres -> [NOMBRE], "
                    "telefonos -> [TELEFONO], correos -> [EMAIL], enlaces ajenos -> [ENLACE]. "
                    "`transcript` trae la respuesta REAL del centro como referencia HISTORICA: precios, "
                    "descuentos y condiciones pueden estar obsoletos (marcados [precio histórico: ...] / "
                    "[descuento histórico: ...]). Los criterios se escriben contra la KB y el catalogo actuales."
                ),
                "chats": len(chats),
                "episodes": len(episodes_out),
                "episodes_with_center_reply": len(usable),
                "episodes_list": episodes_out,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(chats)} chats -> {len(episodes_out)} episodios ({len(usable)} con respuesta del centro) -> {OUT}"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=["transcribe", "build"])
    ap.add_argument(
        "--src",
        required=True,
        type=Path,
        help="carpeta con una subcarpeta por chat (_chat.txt + adjuntos)",
    )
    args = ap.parse_args()
    (transcribe if args.step == "transcribe" else build)(args.src)


if __name__ == "__main__":
    main()
