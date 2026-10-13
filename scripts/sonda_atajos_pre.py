"""ex-3 (fase EX): qué contesta el bot a las preguntas de las respuestas fijas, con los flags de ex-3 apagados y
encendidos, DENTRO del contenedor de PRE (misma forma que `scripts/sonda_rag_pre.py`).

Cada pregunta de `docs/robustness/atajos/preguntas-ex3.json` va en una conversación nueva por `route_message` de
verdad (Chatwoot y el escalado apagados; no se envía nada), dos veces: con los flags como hoy y con los tres de ex-3
encendidos (`atajo_resumen_por_rag`, `atajo_nacionalidad_por_rag`, `atajo_alergia_por_rag`). Saca una línea JSON por
pregunta y modo con la respuesta, para leerlas a mano frente a lo que pide cada pregunta (`debe`).

    scp scripts/sonda_atajos_pre.py docs/robustness/atajos/preguntas-ex3.json root@PRE:/tmp/
    docker cp /tmp/sonda_atajos_pre.py dp-pre-bot:/tmp/ && docker cp /tmp/preguntas-ex3.json dp-pre-bot:/tmp/
    docker exec -i -w /app -e PYTHONPATH=/app dp-pre-bot python /tmp/sonda_atajos_pre.py /tmp/preguntas-ex3.json
Con código local sin desplegar: como en `sonda_rag_pre.py` (copiar `src/` a /tmp/p5 y `-w /tmp/p5`). Gasta OpenAI
(una respuesta del RAG con su revisor por pregunta encendida, ~0,025 $ cada una): avisar antes.
"""
import asyncio
import json
import sys

from src.config import settings

settings.chatwoot_base_url = settings.chatwoot_api_base_url = "http://127.0.0.1:9"
settings.chatwoot_api_token = ""
settings.langfuse_public_key = settings.langfuse_secret_key = ""

from src.agents import escalation, supervisor  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

FLAGS_EX3 = ("atajo_resumen_por_rag", "atajo_nacionalidad_por_rag", "atajo_alergia_por_rag")


async def _noop(*args, **kwargs):
    return True


escalation.escalate_to_human = _noop
supervisor.escalate_to_human = _noop


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    preguntas = json.loads(open(sys.argv[1], encoding="utf-8").read())["preguntas"]
    for modo in ("hoy", "ex3"):
        for flag in FLAGS_EX3:
            setattr(settings, flag, modo == "ex3")
        for p in preguntas:
            st = ConversationState(conversation_id=f"ex3-{modo}-{p['id']}", language=p.get("idioma"))
            try:
                respuesta = await supervisor.route_message(st, p["texto"])
            except Exception as exc:  # noqa: BLE001 — se apunta y se sigue con la siguiente
                respuesta = f"ERROR {exc!r}"
            print(json.dumps({"id": p["id"], "modo": modo, "atajo": p["atajo"], "texto": p["texto"],
                              "debe": p["debe"], "respuesta": str(respuesta)[:1200]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
