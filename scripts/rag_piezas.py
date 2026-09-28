"""rag-1 (Plan Coral, fase RAG): medir el RAG POR PIEZAS en PRE, no solo de punta a punta.

Hasta ahora solo veíamos el resultado final con el juez del golden (ruido ±2 diálogos) y no sabíamos si un
fallo era de la búsqueda (no trae el dato), de la redacción (lo tiene y no lo dice o lo cambia) o del juez
(la respuesta era buena y la corta). Este script lo separa con un set de preguntas VISIBLES
(`docs/robustness/rag-piezas/preguntas.json`; nunca el examen oculto), cada una con los datos que la respuesta
necesita y lo que no debe decir.

Corre `rag_answer` dentro del contenedor `dp-pre-bot` por SSH (base, catálogo, flags y modelos de PRE; no
cambia nada para nadie) con el estado del cliente pasado por `_build_extra_context`, igual que en una
conversación. Espía cada pieza sin tocar el código del bot: la reescritura, cada búsqueda (top-8), el contexto
exacto que ve el modelo, cada respuesta, el juez y las guardas. Después un verificador (gpt-4.1, temperatura 0)
marca por dato si la respuesta lo dice, no lo dice o lo contradice.

Por dato, la causa cuando falta:
  busqueda    el dato no llegó al contexto que vio el modelo (ni fragmentos, ni catálogo, ni estado)
  redaccion   estaba en el contexto y la respuesta no lo dice
  juez_corta  estaba en el contexto y la respuesta acabó en "no lo tengo" (juez o guardas rechazaron)
  contradice  la respuesta dice algo incompatible con el dato

    # todo el set, 1 vez (~47 respuestas, ~1,5 $, ~5 min)
    python -m scripts.rag_piezas --name base
    # solo la búsqueda (sin redactar ni juzgar: céntimos, ~1 min)
    python -m scripts.rag_piezas --name base-busqueda --solo-busqueda
    # algunos casos, 2 veces
    python -m scripts.rag_piezas --name prueba --casos hoteles-base,residente-cop --reps 2
    # comparar dos mediciones (antes/después de un cambio)
    python -m scripts.rag_piezas --comparar docs/robustness/rag-piezas/A.json docs/robustness/rag-piezas/B.json

La cuenta de OpenAI es la MISMA que usa PRE: si se queda sin crédito, PRE deja de contestar.
Salida: `docs/robustness/rag-piezas/<fecha>-<name>.json` (casos con su contexto) y un resumen por pantalla.
"""
import argparse
import json
import re
import statistics
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "docs/robustness/rag-piezas"
PREGUNTAS = DIR / "preguntas.json"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"

_REMOTO = r'''
import asyncio, json, logging, time, types
from openai import AsyncOpenAI
from src.config import settings
from src.observability import _TURN_FACTS
from src.agents import rag_agent, supervisor
from src.agents.rag_agent import FALLBACK_ES, FALLBACK_EN
from src.flows.state import ConversationState
CASOS, SOLO_BUSQUEDA, REPS = json.loads(CASOS_JSON), SOLO_BUSQUEDA_FLAG, N_REPS
VERIFICADOR = VERIFICADOR_PROMPT

T = {}  # lo que espiamos en el caso en curso

class _Log(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if "[RAG][GROUNDING] attempt" in msg:
            T.setdefault("rechazos", []).append(msg.split("rejected (", 1)[-1].split(") query=", 1)[0][:300])
        elif "[RAG][CANONICAL_SHORTCUT]" in msg:
            T["atajo"] = msg.split("shortcut=", 1)[-1].split(" ", 1)[0]
rag_agent.logger.setLevel(logging.INFO)
rag_agent.logger.addHandler(_Log())

_condense = rag_agent.condense_query
async def _spy_condense(query, history=None, lang="es"):
    out = await _condense(query, history=history, lang=lang)
    T["reescrita"] = out
    return out
rag_agent.condense_query = _spy_condense

_search = rag_agent.search_knowledge_base
async def _spy_search(query, lang="es", top_k=None):
    docs = await _search(query, lang=lang, top_k=top_k)
    T.setdefault("busquedas", []).append({"query": query, "docs": [
        {"key": (d.get("metadata") or {}).get("key"), "source": (d.get("metadata") or {}).get("source"),
         "vector": round(float(d.get("score_vector", 0) or 0), 3), "confiado": rag_agent._is_confident(d),
         "content": d.get("content") or ""} for d in docs]})
    return docs
rag_agent.search_knowledge_base = _spy_search

_expand = rag_agent._expand_with_parent_context
async def _spy_expand(docs, lang):
    out = await _expand(docs, lang)
    T["fragmentos"] = [{"key": (d.get("metadata") or {}).get("key"), "source": (d.get("metadata") or {}).get("source"),
                        "content": d.get("content") or ""} for d in out]
    return out
rag_agent._expand_with_parent_context = _spy_expand

_grounded = rag_agent.is_grounded
async def _spy_grounded(answer, context, lang="es"):
    if SOLO_BUSQUEDA:
        return True, ""
    ok, why = await _grounded(answer, context, lang=lang)
    T.setdefault("juicios", []).append({"ok": ok, "why": why[:400]})
    return ok, why
rag_agent.is_grounded = _spy_grounded

_FAKE = "Respuesta de prueba sin datos del negocio, solo para medir la busqueda."
class _SpyClient:
    def __init__(self, real):
        self._real = real
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))
    async def _create(self, **kw):
        msgs = kw.get("messages") or []
        T.setdefault("llamadas", []).append({
            "sistema": msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else "",
            "usuario": msgs[-1]["content"] if msgs else "", "n_mensajes": len(msgs)})
        if SOLO_BUSQUEDA:
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=_FAKE))],
                usage=types.SimpleNamespace(total_tokens=0, prompt_tokens=0, prompt_tokens_details=None))
        t0 = time.perf_counter()
        r = await self._real.chat.completions.create(**kw)
        T["llamadas"][-1].update({"respuesta": r.choices[0].message.content or "", "s": round(time.perf_counter() - t0, 2),
                                  "prompt_tokens": getattr(r.usage, "prompt_tokens", 0)})
        return r
_trace = rag_agent.trace_openai
rag_agent.trace_openai = lambda c: _SpyClient(_trace(c))

async def verificar(c, respuesta):
    datos = "\n".join(f"- [{h['id']}] {h['hecho']}" for h in c["necesita"])
    prohibidas = "\n".join(f"- [{i}] {p}" for i, p in enumerate(c.get("no_debe") or []))
    user = (f"PREGUNTA DEL CLIENTE:\n{c['pregunta']}\n\nRESPUESTA DEL ASISTENTE:\n{respuesta}\n\n"
            f"DATOS:\n{datos}\n\nAFIRMACIONES PROHIBIDAS:\n{prohibidas or '(ninguna)'}")
    cli = AsyncOpenAI(api_key=settings.openai_api_key)
    r = await cli.chat.completions.create(model="gpt-4.1", temperature=0, response_format={"type": "json_object"},
                                          messages=[{"role": "system", "content": VERIFICADOR}, {"role": "user", "content": user}])
    try:
        return json.loads(r.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return {}

async def una(c, rep):
    T.clear()
    st = ConversationState(conversation_id="rag-piezas", language=c["lang"])
    st.history = list(c.get("historial") or [])
    for k, v in (c.get("estado") or {}).items():
        setattr(st, k, v)
    extra = supervisor._build_extra_context(st)
    tok = _TURN_FACTS.set({})
    t0 = time.perf_counter()
    try:
        ans = await rag_agent.rag_answer(c["pregunta"], lang=c["lang"], history=st.history, extra_context=extra)
    except Exception as exc:  # noqa: BLE001
        ans = f"ERROR {type(exc).__name__}: {exc}"
    s = round(time.perf_counter() - t0, 2)
    n_llm = len((_TURN_FACTS.get() or {}).get("_llm", []))
    _TURN_FACTS.reset(tok)
    fila = {"id": c["id"], "rep": rep, "s": s, "n_llm": n_llm, "respuesta": ans,
            "fallback": (ans or "").strip() in (FALLBACK_ES, FALLBACK_EN), **T}
    if not SOLO_BUSQUEDA and not fila["fallback"] and not ans.startswith("ERROR "):
        fila["verificacion"] = await verificar(c, ans)
    return fila

async def main():
    for rep in range(REPS):
        for c in CASOS:
            print(json.dumps(await una(c, rep), ensure_ascii=False), flush=True)

asyncio.run(main())
'''

VERIFICADOR_PROMPT = (
    "Eres un verificador estricto. Recibes la pregunta de un cliente, la respuesta de un asistente, una lista de "
    "DATOS verdaderos y una lista de AFIRMACIONES PROHIBIDAS. Para cada DATO decide: 'dice' si la respuesta lo "
    "transmite (con otras palabras, en otro idioma o con otro formato de número vale), 'contradice' si afirma algo "
    "incompatible con él, 'no_dice' si no lo menciona. Si un dato tiene varias partes, 'dice' exige la parte "
    "esencial que responde al cliente. Para cada AFIRMACIÓN PROHIBIDA, true si la respuesta la afirma o la da a "
    "entender. Devuelve SOLO JSON: {\"datos\": {\"<id>\": \"dice|no_dice|contradice\"}, "
    "\"prohibidas\": {\"<indice>\": true|false}}."
)


def norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", t)  # 1.429.000 / 1,429,000 -> 1429000
    return re.sub(r"\s+", " ", t)


def presente(hecho: dict, texto_norm: str) -> bool:
    return any(all(norm(p) in texto_norm for p in ancla.split(" + ")) for ancla in hecho["anclas"])


def compactar(run: dict) -> dict:
    """Guarda cada prompt de sistema distinto una sola vez (en cada respuesta pesa ~26.000 caracteres)."""
    sistemas = run.setdefault("sistemas", [])
    for f in run["filas"]:
        for ll in f.get("llamadas") or []:
            s = ll.get("sistema", "")
            if isinstance(s, str) and not s.startswith("@"):
                if s not in sistemas:
                    sistemas.append(s)
                ll["sistema"] = f"@{sistemas.index(s)}"
    return run


def expandir(run: dict) -> dict:
    sistemas = run.get("sistemas") or []
    for f in run["filas"]:
        for ll in f.get("llamadas") or []:
            s = ll.get("sistema", "")
            if isinstance(s, str) and s.startswith("@") and s[1:].isdigit():
                ll["sistema"] = sistemas[int(s[1:])]
    return run


def leer(path: Path) -> dict:
    return expandir(json.loads(path.read_text(encoding="utf-8")))


def guardar(path: Path, run: dict) -> None:
    path.write_text(json.dumps(compactar(run), ensure_ascii=False, indent=1), encoding="utf-8")


def _oculto() -> set[str]:
    dialogos = json.loads(GOLDEN.read_text(encoding="utf-8"))["dialogues"]
    return {d["id"] for d in dialogos if d.get("suite") == "oculto"}


def cargar_casos(filtro: str | None) -> list[dict]:
    casos = json.loads(PREGUNTAS.read_text(encoding="utf-8"))["casos"]
    oculto = _oculto()
    malos = [c["id"] for c in casos if c.get("origen", "").split(":", 1)[-1].split("#")[0] in oculto]
    if malos:
        raise SystemExit(f"casos sacados del examen oculto (no se permiten): {malos}")
    if filtro:
        ids = {x.strip() for x in filtro.split(",") if x.strip()}
        casos = [c for c in casos if c["id"] in ids]
    return casos


def puntuar(caso: dict, fila: dict) -> dict:
    """Por dato: dónde está (top-8 bruto, contexto visto) y qué hizo la respuesta."""
    busquedas = fila.get("busquedas") or []
    top8 = busquedas[-1]["docs"] if busquedas else []
    llamadas = fila.get("llamadas") or []
    visto = (llamadas[0]["sistema"] + "\n" + llamadas[0]["usuario"]) if llamadas else ""
    visto_n = norm(visto)
    frag_n = norm("\n".join(d["content"] for d in (fila.get("fragmentos") or [])))
    verif = (fila.get("verificacion") or {}).get("datos") or {}
    datos = []
    for h in caso["necesita"]:
        rango = next((i + 1 for i, d in enumerate(top8) if presente(h, norm(d["content"]))), None)
        en_contexto = None if h.get("calculo") else presente(h, visto_n)
        v = "no_dice" if fila.get("fallback") else verif.get(h["id"], "no_dice")
        if v == "dice":
            causa = "ok"
        elif v == "contradice":
            causa = "contradice"
        elif h.get("calculo"):
            causa = "juez_corta" if fila.get("fallback") else "redaccion"
        elif not en_contexto:
            causa = "busqueda"
        elif fila.get("fallback"):
            causa = "juez_corta"
        else:
            causa = "redaccion"
        datos.append({"id": h["id"], "calculo": bool(h.get("calculo")), "opcional": bool(h.get("opcional")),
                      "rango_top8": rango,
                      "en_fragmentos": None if h.get("calculo") else presente(h, frag_n),
                      "en_contexto": en_contexto, "respuesta": v, "causa": causa})
    prohibidas = (fila.get("verificacion") or {}).get("prohibidas") or {}
    return {"datos": datos, "prohibidas_afirmadas": sum(1 for v in prohibidas.values() if v is True),
            "contexto_chars": len(visto), "confiado": fila.get("fragmentos") is not None,
            "regeneraciones": max(0, sum(1 for x in llamadas if "respuesta" in x) - 1)}


def resumen(filas: list[dict], solo_busqueda: bool) -> dict:
    todos = [d for f in filas for d in f["puntos"]["datos"]]
    datos = [d for d in todos if not d.get("opcional")]
    extras = [d for d in todos if d.get("opcional")]
    busc = [d for d in datos if not d["calculo"]]
    n = len(busc) or 1
    r = {
        "casos": len(filas), "datos": len(datos),
        "recall_top1": sum(1 for d in busc if d["rango_top8"] == 1) / n,
        "recall_top3": sum(1 for d in busc if d["rango_top8"] and d["rango_top8"] <= 3) / n,
        "recall_top8": sum(1 for d in busc if d["rango_top8"]) / n,
        "en_fragmentos": sum(1 for d in busc if d["en_fragmentos"]) / n,
        "en_contexto": sum(1 for d in busc if d["en_contexto"]) / n,
        "sin_confianza": sum(1 for f in filas if not f["puntos"]["confiado"]) / (len(filas) or 1),
        "atajos": sum(1 for f in filas if f.get("atajo")),
        "contexto_chars_media": statistics.mean(f["puntos"]["contexto_chars"] for f in filas) if filas else 0,
    }
    if not solo_busqueda:
        causas = {}
        for d in datos:
            causas[d["causa"]] = causas.get(d["causa"], 0) + 1
        s = sorted(f["s"] for f in filas)
        r.update({
            "cobertura": causas.get("ok", 0) / (len(datos) or 1), "causas": causas,
            "extras_cubiertos": f"{sum(1 for d in extras if d['causa'] == 'ok')}/{len(extras)}",
            "prohibidas_afirmadas": sum(f["puntos"]["prohibidas_afirmadas"] for f in filas),
            "no_lo_tengo": sum(1 for f in filas if f.get("fallback")),
            "rechazos": sum(len(f.get("rechazos") or []) for f in filas),
            "regeneraciones": sum(f["puntos"]["regeneraciones"] for f in filas),
            "segundos_p50": statistics.median(s) if s else 0, "segundos_p90": s[int(len(s) * 0.9)] if s else 0,
            "llamadas_llm_media": statistics.mean(f["n_llm"] for f in filas) if filas else 0,
        })
    return r


def imprimir(r: dict, etiqueta: str = "") -> None:
    pc = lambda x: f"{100 * x:.0f} %"  # noqa: E731
    print(f"== {etiqueta} {r['casos']} respuestas, {r['datos']} datos")
    print(f"  BÚSQUEDA  recall@1 {pc(r['recall_top1'])} · @3 {pc(r['recall_top3'])} · @8 {pc(r['recall_top8'])} · "
          f"en fragmentos usados {pc(r['en_fragmentos'])} · en contexto visto (con catálogo y estado) {pc(r['en_contexto'])}")
    print(f"            sin confianza (solo estado+catálogo) {pc(r['sin_confianza'])} · atajos {r['atajos']} · "
          f"contexto medio {r['contexto_chars_media'] / 1000:.1f}k caracteres")
    if "cobertura" in r:
        c = r["causas"]
        print(f"  RESPUESTA cobertura {pc(r['cobertura'])} · faltan por: búsqueda {c.get('busqueda', 0)} · redacción "
              f"{c.get('redaccion', 0)} · juez/guardas {c.get('juez_corta', 0)} · contradice {c.get('contradice', 0)} · "
              f"prohibidas {r['prohibidas_afirmadas']} · extras opcionales {r.get('extras_cubiertos', '—')}")
        print(f"  JUEZ      \"no lo tengo\" {r['no_lo_tengo']} · rechazos {r['rechazos']} · regeneraciones {r['regeneraciones']}")
        print(f"  TIEMPO    p50 {r['segundos_p50']:.1f} s · p90 {r['segundos_p90']:.1f} s · llamadas LLM {r['llamadas_llm_media']:.1f}")


def comparar(a_path: Path, b_path: Path) -> None:
    a, b = (leer(p) for p in (a_path, b_path))
    imprimir(a["resumen"], f"A {a_path.stem}:")
    imprimir(b["resumen"], f"B {b_path.stem}:")
    ok = lambda run: {(f["id"], d["id"]): d["causa"] == "ok" for f in run["filas"] for d in f["puntos"]["datos"]}  # noqa: E731
    oa, ob = ok(a), ok(b)
    gana = sorted(k for k in oa if k in ob and ob[k] and not oa[k])
    pierde = sorted(k for k in oa if k in ob and oa[k] and not ob[k])
    print(f"datos que B cubre y A no ({len(gana)}): {', '.join(f'{c}/{d}' for c, d in gana) or '—'}")
    print(f"datos que A cubre y B no ({len(pierde)}): {', '.join(f'{c}/{d}' for c, d in pierde) or '—'}")
    print("(con 1 repetición por lado, un dato que cambia puede ser ruido de muestreo: mirar las dos respuestas)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--name", help="nombre de la medición (fichero <fecha>-<name>.json)")
    ap.add_argument("--casos", help="ids separados por coma (por defecto, todos)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--solo-busqueda", action="store_true", help="no redacta ni juzga: solo qué trae la búsqueda")
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"))
    ap.add_argument("--repuntuar", metavar="FICHERO", help="recalcula las causas de una medición guardada con las anclas "
                    "actuales de preguntas.json (sin volver a PRE; la verificación de la respuesta no cambia)")
    ap.add_argument("--dry", action="store_true", help="solo lista los casos")
    args = ap.parse_args()

    if args.comparar:
        comparar(Path(args.comparar[0]), Path(args.comparar[1]))
        return
    if args.repuntuar:
        path = Path(args.repuntuar)
        run = leer(path)
        por_id = {c["id"]: c for c in cargar_casos(None)}
        for f in run["filas"]:
            f["puntos"] = puntuar(por_id[f["id"]], f)
        run["resumen"] = resumen(run["filas"], run["solo_busqueda"])
        run["preguntas_version"] = json.loads(PREGUNTAS.read_text(encoding="utf-8"))["version"]
        guardar(path, run)
        imprimir(run["resumen"], path.stem)
        return
    if not args.name:
        raise SystemExit("falta --name")
    casos = cargar_casos(args.casos)
    total = len(casos) * args.reps
    print(f"{len(casos)} casos × {args.reps} rep = {total} respuestas"
          + ("" if args.solo_busqueda else f" (~{total * 0.03:.2f} $)"))
    if args.dry:
        for c in casos:
            print(f"  {c['id']} [{c['lang']}] {len(c['necesita'])} datos | {c['pregunta'][:90]}")
        return

    from scripts.pre_access import pre_ssh

    script = (f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nSOLO_BUSQUEDA_FLAG = {args.solo_busqueda!r}\n"
              f"N_REPS = {args.reps}\nVERIFICADOR_PROMPT = {VERIFICADOR_PROMPT!r}\n{_REMOTO}")
    r = pre_ssh("docker exec -i dp-pre-bot python -", input_text=script, timeout=max(600, 40 * total))
    por_id = {c["id"]: c for c in casos}
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    for f in filas:
        f["puntos"] = puntuar(por_id[f["id"]], f)
    res = resumen(filas, args.solo_busqueda)
    out = DIR / f"{date.today().isoformat()}-{args.name}.json"
    guardar(out, {"nombre": args.name, "solo_busqueda": args.solo_busqueda, "reps": args.reps,
                  "preguntas_version": json.loads(PREGUNTAS.read_text(encoding="utf-8"))["version"],
                  "resumen": res, "filas": filas})
    imprimir(res, args.name)
    print(f"→ {out}")
    if len(filas) < total:
        print(f"⚠️ faltan respuestas ({len(filas)}/{total}); stderr de PRE:\n" + (r.stderr or "")[-2000:])


if __name__ == "__main__":
    main()
