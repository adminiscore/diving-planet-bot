"""Paso 5 (RAG): sonda de los turnos que fallaron por el RAG, DENTRO del contenedor de PRE.

Reproduce cada dialogo hasta el turno que fallo con `route_message` de verdad (Chatwoot y el
escalado apagados; no se envia nada) y guarda por turno: la llamada al RAG (consulta, contexto de
estado, respuesta final), las busquedas (fuente, puntuacion, confianza) y cada respuesta que vio el
juez de grounding con su veredicto. Solo lectura sobre la base de conocimiento.

Entrada por stdin: dos lineas JSON — {dialogo: [mensajes hasta el turno]} y {"dialogo#turno": datos
del fallo} (`docs/robustness/paso5-rag/casos-ronda-A.txt`). Uso:
    scp scripts/sonda_rag_pre.py docs/robustness/paso5-rag/casos-ronda-A.txt root@PRE:/tmp/
    docker cp /tmp/sonda_rag_pre.py dp-pre-bot:/tmp/
    docker exec -i -w /app -e PYTHONPATH=/app dp-pre-bot python /tmp/sonda_rag_pre.py < /tmp/casos-ronda-A.txt
Para probar codigo local sin desplegar: copiar `src/` a /tmp/p5 del contenedor (con /tmp/p5/data ->
/app/data) y usar `-w /tmp/p5 -e PYTHONPATH=/tmp/p5` mas las variables de los flags (RAG_V2=true).
"""
import asyncio, contextvars, json, logging, sys
from src.config import settings
settings.chatwoot_base_url = settings.chatwoot_api_base_url = "http://127.0.0.1:9"
settings.chatwoot_api_token = ""
settings.langfuse_public_key = settings.langfuse_secret_key = ""
from src.agents import conversational_core as core, escalation, supervisor, rag_agent
from src.flows.state import ConversationState
DATA = json.loads(sys.stdin.readline()); TARGETS = json.loads(sys.stdin.readline())
async def _noop(*a, **k): return True
escalation.escalate_to_human = _noop; supervisor.escalate_to_human = _noop
_CUR = contextvars.ContextVar('cur', default=None)
def cur():
    return _CUR.get() if _CUR.get() is not None else {}
orig_search = rag_agent.search_knowledge_base
async def search(q, **k):
    docs = await orig_search(q, **k)
    cur().setdefault("searches", []).append({"q": q[:200], "top": [
        {"src": (d.get("metadata") or {}).get("source"), "sc": round(float(rag_agent._score_for_threshold(d)), 3),
         "conf": rag_agent._is_confident(d), "txt": (d.get("content") or d.get("text") or "")[:160]} for d in docs[:5]]})
    return docs
rag_agent.search_knowledge_base = search
orig_ver = rag_agent._verify_grounding
async def ver(answer, context, lang):
    g, r = await orig_ver(answer, context, lang)
    cur().setdefault("judged", []).append({"answer": answer[:700], "grounded": g, "ctx_len": len(context)})
    return g, r
rag_agent._verify_grounding = ver
orig_rag = supervisor.rag_answer
async def rag(query, **k):
    cur().setdefault("calls", []).append({"query": query[:300], "extra": (k.get("extra_context") or "")[:900]})
    ans = await orig_rag(query, **k)
    cur()["calls"][-1]["final"] = ans[:700]
    return ans
supervisor.rag_answer = rag
class H(logging.Handler):
    def emit(self, rec):
        m = rec.getMessage()
        if m.startswith("[RAG]") and _CUR.get() is not None: _CUR.get().setdefault("log", []).append(m[:300])
logging.getLogger("uvicorn.error").addHandler(H())
async def one(did, turns, sem):
    out = []
    async with sem:
        st = ConversationState(conversation_id=f"probe-{did}")
        for i, msg in enumerate(turns, 1):
            key = f"{did}#{i}"
            c = {}
            _CUR.set(c)
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:
                reply = f"ERROR {exc}"
            if key in TARGETS:
                out.append({"id": key, **TARGETS[key], "msg": msg, "reply": str(reply)[:900], **c})
    return out
async def main():
    sem = asyncio.Semaphore(6)
    parts = await asyncio.gather(*(one(d, t, sem) for d, t in DATA.items()))
    res = [r for p in parts for r in p]
    for r in res: print(json.dumps(r, ensure_ascii=False))
asyncio.run(main())
