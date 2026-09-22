"""Cuenta, por codigo, los patrones de fallo del bot en una ronda del golden-set.

El juez dice QUE criterio falla; esto agrupa POR QUE falla, mirando la forma de las respuestas.
Cada patron es una causa candidata (se confirma leyendo los casos) y lista los dialogos donde
aparece, que son los casos de regresion de la tarea que la arregle.

    python docs/robustness/golden-set/failure_patterns.py docs/robustness/synthetic-runs/<ronda>.jsonl
"""

import collections
import json
import re
import sys
from pathlib import Path

# (id, descripcion, predicado sobre (turno, turno_anterior_del_mismo_dialogo))
AVAILABILITY_CANNED = re.compile(r"salidas son diarias y siempre hay disponibilidad|departures are daily and there is always availability", re.I)
CHANGE_CONFIRM = re.compile(r"Solo para confirmar, ¿lo cambio\?|Just to confirm, should I change it\?", re.I)
RAG_FALLBACK = re.compile(r"no lo tengo a la mano|don't have that specific detail handy", re.I)
RECALL = re.compile(r"^(Me habías dicho|Me dijiste|You told me)", re.I | re.M)
PRIVACY = re.compile(r"Por tu privacidad y seguridad|For your privacy and security", re.I)
SLOT_Q = re.compile(
    r"¿Desde dónde saldrías\?|Where would you be departing from\?|¿Ha[n]? pasado \*más de 2 años\*|"
    r"Has it been \*more than 2 years\*|¿Con cuál te animas|¿Y para cuántas personas armamos el plan\?|"
    r"¿eres colombiano o residente|¿sois colombianos o residentes|are you Colombian or a resident|"
    r"Cuéntame, ¿qué te gustaría vivir con nosotros\?|Para recomendarte el plan perfecto|"
    r"So I can recommend the perfect plan",
    re.I,
)
QUESTION = re.compile(r"\?|^(qu[eé]|c[oó]mo|cu[aá]nt|d[oó]nde|cu[aá]l|hay|tienen|puedo|pueden|what|how|where|is|are|can|do|will)\b", re.I)


def slot_question(reply: str) -> str | None:
    m = SLOT_Q.search(reply or "")
    return m.group(0) if m else None


PATTERNS = {
    "disponibilidad-enlatada": "Responde con el mensaje fijo de disponibilidad ('las salidas son diarias...') aunque el cliente preguntaba otra cosa o daba fechas.",
    "cambio-sin-motivo": "Pide confirmar un cambio del carrito ('¿lo cambio? X -> Y') que el cliente no pidio (extraccion equivocada).",
    "rag-no-lo-tengo": "El RAG contesta 'no lo tengo a la mano' (fallback).",
    "recuerdo-en-vez-de-respuesta": "Contesta 'Me habias dicho: ...' / 'You told me' a una pregunta.",
    "aviso-privacidad": "Salta el aviso de privacidad (datos de pago o documentos).",
    "ignora-pregunta-repite-paso": "El cliente pregunta algo y el bot solo repite la misma pregunta del flujo que ya habia hecho.",
}


def analyse(records: list[dict]) -> dict:
    by_tag: dict[str, list[dict]] = collections.defaultdict(list)
    for r in records:
        by_tag[r["tag"]].append(r)
    hits: dict[str, dict[str, int]] = {p: collections.Counter() for p in PATTERNS}
    turns: collections.Counter = collections.Counter()
    for tag, rs in by_tag.items():
        rs.sort(key=lambda r: r["turn"])
        prev_q = None
        for r in rs:
            reply = r.get("reply") or ""
            if AVAILABILITY_CANNED.search(reply):
                hits["disponibilidad-enlatada"][tag] += 1
            if CHANGE_CONFIRM.search(reply):
                hits["cambio-sin-motivo"][tag] += 1
            if RAG_FALLBACK.search(reply):
                hits["rag-no-lo-tengo"][tag] += 1
            if RECALL.search(reply):
                hits["recuerdo-en-vez-de-respuesta"][tag] += 1
            if PRIVACY.search(reply):
                hits["aviso-privacidad"][tag] += 1
            q = slot_question(reply)
            if q and prev_q == q and QUESTION.search(r["msg"].strip()):
                hits["ignora-pregunta-repite-paso"][tag] += 1
            prev_q = q
        turns[tag] = len(rs)
    return {
        "dialogos": len(by_tag),
        "turnos": sum(turns.values()),
        "patrones": {
            p: {
                "descripcion": PATTERNS[p],
                "dialogos": len(h),
                "turnos": sum(h.values()),
                "casos": dict(h.most_common()),
            }
            for p, h in hits.items()
        },
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run = Path(sys.argv[1])
    records = [json.loads(line) for line in run.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = analyse(records)
    print(f"{report['dialogos']} dialogos, {report['turnos']} turnos")
    for p, v in report["patrones"].items():
        print(f"  {p:32} {v['dialogos']:3} dialogos {v['turnos']:3} turnos")
    out = run.with_name(run.stem + "__patrones.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
