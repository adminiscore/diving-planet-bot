"""g-7, paso 0.1: inventario de los HECHOS que afirman los chats antiguos frente a la KB oficial.

Por cada chat de `data/knowledge_base/conversations.json` (lado del centro), un LLM extrae los hechos
de negocio que afirma el equipo y los clasifica contra la KB oficial (todo `data/knowledge_base/`
salvo conversations.json):
  - en_kb: la KB oficial ya lo dice (quitar el chat no pierde nada);
  - desfasado: la KB oficial dice otra cosa (el chat esta caducado: se descarta);
  - ausente: la KB oficial no lo cubre (candidato a anadir a la KB, lo decide Gadea);
  - no_negocio: saludos, logistica de una reserva concreta, cosas del dia (no es conocimiento).

No toca el bot. Salida: docs/robustness/g7-inventory.json (+ resumen por pantalla).

    ENV_FILE=.env.dev python docs/robustness/g7_inventory.py
"""

import collections
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.langfuse_snapshot import _env  # noqa: E402

KB = ROOT / "data" / "knowledge_base"
OUT = Path(__file__).parent / "g7-inventory.json"
MODEL = "gpt-4.1-mini"

INSTRUCTIONS = """Eres auditor de la base de conocimiento de Diving Planet (centro de buceo en Cartagena,
Colombia). Te paso lo que el EQUIPO respondio a un cliente en un chat antiguo de WhatsApp (2025-26) y la
BASE DE CONOCIMIENTO OFICIAL actual. Extrae cada HECHO DE NEGOCIO que afirma el equipo (precios,
horarios, punto de encuentro, que incluye cada plan, politicas, requisitos, alojamiento, recogidas,
descuentos, pagos, idiomas, equipo, fotos, etc.) y clasificalo contra la KB oficial:
- "en_kb": la KB oficial dice lo mismo (cita el texto de la KB en "evidencia_kb");
- "desfasado": la KB oficial dice otra cosa (cita lo que dice la KB);
- "ausente": la KB oficial no dice nada de eso;
- "no_negocio": saludos, confirmaciones de una reserva concreta, logistica de un dia puntual,
  preguntas al cliente.
Un hecho por elemento, en espanol, corto y concreto. Devuelve SOLO JSON:
{"hechos": [{"hecho": "...", "tema": "precio|punto_encuentro|horario|incluye|politica|requisito|alojamiento|recogida|descuento|pago|idioma|equipo|fotos|otro", "estado": "en_kb|desfasado|ausente|no_negocio", "evidencia_kb": "cita corta o vacio"}]}"""


def official_kb() -> str:
    parts = []
    for path in sorted(KB.glob("*.json")):
        if path.name.startswith("conversations"):
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        parts.append(f"### {path.name}\n{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}")
    return "\n\n".join(parts)


def chats() -> dict[str, list[str]]:
    examples = json.loads((KB / "conversations.json").read_text(encoding="utf-8-sig"))["conversation_examples"]
    by_chat: dict[str, list[str]] = collections.defaultdict(list)
    for ex in examples:
        chat = re.sub(r"_part\d+$", "", ex.get("id", ""))
        by_chat[chat] += [str(m) for m in (ex.get("diving_planet") or {}).get("messages") or []]
    # los ids del import llevan el numero de telefono del cliente: al informe va solo un indice
    return {f"chat-{i:02d}": msgs for i, (_, msgs) in enumerate(sorted(by_chat.items()), 1)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from openai import OpenAI

    client = OpenAI(api_key=_env("OPENAI_API_KEY"))
    system = f"{INSTRUCTIONS}\n\nBASE DE CONOCIMIENTO OFICIAL:\n{official_kb()}"
    done = json.loads(OUT.read_text(encoding="utf-8"))["chats"] if OUT.exists() else {}
    usage = collections.Counter()
    todo = {k: v for k, v in chats().items() if k not in done}
    for i, (chat, msgs) in enumerate(todo.items(), 1):
        text = "\n".join(f"EQUIPO: {m}" for m in msgs)[:20000]
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
        )
        usage["input"] += resp.usage.prompt_tokens
        usage["cached"] += getattr(resp.usage.prompt_tokens_details, "cached_tokens", 0) or 0
        usage["output"] += resp.usage.completion_tokens
        done[chat] = json.loads(resp.choices[0].message.content or "{}").get("hechos", [])
        OUT.write_text(json.dumps({"model": MODEL, "chats": done}, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        estados = collections.Counter(h.get("estado") for h in done[chat])
        print(f"{i}/{len(todo)} {chat}: {dict(estados)} {time.time() - t0:.0f}s")
    total = collections.Counter(h.get("estado") for hs in done.values() for h in hs)
    cost = ((usage["input"] - usage["cached"]) * 0.4 + usage["cached"] * 0.1 + usage["output"] * 1.6) / 1e6
    print(f"TOTAL {dict(total)} · ~{cost:.2f} $")


if __name__ == "__main__":
    main()
