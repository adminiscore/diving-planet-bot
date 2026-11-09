"""CALN (27-oct): sparring contra el código de una RAMA, sin desplegarla. Como `charla_pre` (Claude hace de cliente, un
turno cada vez, para adaptarse a lo que contesta el bot), pero cada turno corre dentro de `dp-pre-bot` con el código
LOCAL (`--codigo-local` de `reproducir_juez_pre`): mismos modelos, base e interruptores que PRE, y PRE no cambia. El
estado de la conversación se guarda serializado tras cada turno y el siguiente sigue desde él.

    python -m scripts.charla_rama nueva --nombre familia-abuela        # -> docs/robustness/g3/charlas-rama/<nombre>.jsonl
    python -m scripts.charla_rama di --nombre familia-abuela "hola, somos 4 y queremos bucear"
    python -m scripts.charla_rama ver --nombre familia-abuela

Sirve para el sparring de cada integración ANTES de subirla a PRE (decisión de Gadea, 27-oct: «detectar antes de que
vengan clientes reales»). Coste: el del bot (céntimos por turno); sin juez.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHARLAS = ROOT / "docs/robustness/g3/charlas-rama"

_REMOTO = r'''
import asyncio, json, time
from src.agents import supervisor
from src.flows.state import ConversationState
from src.state_store import deserialize_state, serialize_state
# Bloque 0 (10-nov): reloj fijo, como en reproducir_juez_pre: la hora del bot solo se lee en contexto_rag y se sustituye ahí.
from datetime import datetime as _dt
import src.agents.rutas.contexto_rag as _ctx
_FIJO = _dt.fromisoformat(RELOJ) if RELOJ else None
class _Reloj(_dt):
    @classmethod
    def now(cls, tz=None):
        return _dt.now(tz) if _FIJO is None else (_FIJO.astimezone(tz) if tz else _FIJO)
_ctx.datetime = _Reloj
import logging
_TRAZA = []
class _Traza(logging.Handler):
    def emit(self, rec):
        m = rec.getMessage()
        if any(t in m for t in ("[EXTRACT]", "[LLM_EXTRACTOR]", "[CORE]", "[INTENT]", "[HECHOS]", "[RAG][LAT5]", "[ESPIA]")):
            _TRAZA.append(m[:400])
logging.getLogger().addHandler(_Traza())
logging.getLogger().setLevel(logging.INFO)
ESPIA_CODIGO
CAMPOS =("core_pending_slot", "detected_activity", "is_certified", "location", "detected_group_size",
          "detected_group_allocation", "pending_undecided_qty", "needs_companion_activity", "pending_companion_activity",
          "detected_ages", "is_colombian", "last_dive_over_2_years", "detected_duration")

async def main():
    st = deserialize_state(ESTADO, CONV) if ESTADO else ConversationState(conversation_id=CONV)
    t0 = time.perf_counter()
    try:
        reply = await supervisor.route_message(st, MENSAJE)
    except Exception as exc:  # noqa: BLE001
        reply = f"ERROR {type(exc).__name__}: {exc}"
    estado = {c: getattr(st, c, None) for c in CAMPOS if getattr(st, c, None) not in (None, "", [], {})}
    print(json.dumps({"reply": reply, "segundos": round(time.perf_counter() - t0, 2), "estado": estado,
                      "traza": _TRAZA, "guardado": serialize_state(st)}, ensure_ascii=False, default=str), flush=True)

asyncio.run(main())
'''

# CALN-16 (3-nov): con `--espia`, cada búsqueda del RAG (la consulta y las claves de su top-8) y las fichas que llegan al
# escritor van también a la traza, con [ESPIA]: en la conversación entera se ve lo que `rag_piezas` ve en una pregunta
# suelta (el cava: la marca del origen pegada a la búsqueda por pregunta).
_ESPIA = r'''
from src.agents import rag_agent as _ra
_lg_e = logging.getLogger("espia")
_buscar = _ra.search_knowledge_base
async def _espia_buscar(query, lang="es", top_k=None, **kw):
    docs = await _buscar(query, lang=lang, top_k=top_k, **kw)
    _lg_e.warning("[ESPIA] busca %r -> %s", str(query)[:160], [(d.get("metadata") or {}).get("key") for d in docs][:8])
    return docs
_ra.search_knowledge_base = _espia_buscar
_fichas = _ra.fichas_del_origen
def _espia_fichas(docs, origin, lang):
    out = _fichas(docs, origin, lang)
    _lg_e.warning("[ESPIA] al escritor %s", [(d.get("metadata") or {}).get("key") for d in out])
    return out
_ra.fichas_del_origen = _espia_fichas
'''


def _fichero(nombre: str) -> Path:
    return CHARLAS / f"{nombre}.jsonl"


def _filas(nombre: str) -> list[dict]:
    f = _fichero(nombre)
    if not f.exists():
        raise SystemExit(f"no existe la charla {nombre}: ábrela con `nueva --nombre {nombre}`")
    return [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _reloj_de(nombre: str) -> str | None:
    f = CHARLAS / f"{nombre}.reloj"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def _nueva(nombre: str, reloj: str | None = None) -> None:
    CHARLAS.mkdir(parents=True, exist_ok=True)
    f = _fichero(nombre)
    if f.exists():
        raise SystemExit(f"ya existe {f}")
    f.write_text("", encoding="utf-8")
    if reloj:  # la hora fija de toda la charla (bloque 0): la misma regla que el panel
        from scripts.reproducir_juez_pre import relojes_de

        (CHARLAS / f"{nombre}.reloj").write_text(relojes_de([nombre], reloj)[nombre], encoding="utf-8")
    print(f"charla {nombre} -> {f} (rama {_git('rev-parse', '--abbrev-ref', 'HEAD')}, {_git('rev-parse', '--short', 'HEAD')})"
          + (f"; reloj {_reloj_de(nombre)}" if reloj else ""))


def _di(nombre: str, mensaje: str, entorno: dict[str, str] | None = None, espia: bool = False) -> None:
    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    filas = _filas(nombre)
    estado = filas[-1]["guardado"] if filas else None
    remoto = _REMOTO.replace("ESPIA_CODIGO\n", _ESPIA if espia else "")
    reloj = _reloj_de(nombre)
    script = (f"CONV = {('charla-rama-' + nombre)!r}\nMENSAJE = {mensaje!r}\nESTADO = {estado!r}\nRELOJ = {reloj!r}\n{remoto}")
    r = pre_ssh(docker_python(entorno or {}, codigo_local=subir_codigo_local()), input_text=script, timeout=300)
    salida = next((json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")), None)
    if salida is None:
        raise SystemExit("el turno no devolvió nada; stderr de PRE:\n" + (r.stderr or "")[-2000:])
    fila = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "turno": len(filas) + 1,
            "commit": _git("rev-parse", "--short", "HEAD"), "msg": mensaje, "reloj": reloj, **salida}
    with _fichero(nombre).open("a", encoding="utf-8") as g:
        g.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"BOT ({salida['segundos']} s):\n{salida['reply']}\n\nESTADO: {json.dumps(salida['estado'], ensure_ascii=False)}")


def _ver(nombre: str) -> None:
    for f in _filas(nombre):
        print(f"== {f['turno']} CLIENTE: {f['msg']}\nBOT: {f['reply']}\nESTADO: {json.dumps(f['estado'], ensure_ascii=False)}\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="accion", required=True)
    for accion in ("nueva", "di", "ver"):
        p = sub.add_parser(accion)
        p.add_argument("--nombre", required=True)
        if accion == "nueva":
            p.add_argument("--reloj", help="hora fija de toda la charla: alterno (por el nombre), antes, despues o ISO con zona")
        if accion == "di":
            p.add_argument("mensaje")
            p.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                           help="variable de entorno SOLO en este turno (p. ej. RAG_KB_ESQUEMA=kb_v2_gadea: la base curada"
                                " de la rama, cargada con `scripts.kb_v2 --esquema`)")
            p.add_argument("--espia", action="store_true",
                           help="las búsquedas del RAG y las fichas que llegan al escritor, en la traza ([ESPIA])")
    args = ap.parse_args()
    if args.accion == "nueva":
        _nueva(args.nombre, args.reloj)
    elif args.accion == "di":
        _di(args.nombre, args.mensaje, dict(e.split("=", 1) for e in args.env), args.espia)
    else:
        _ver(args.nombre)


if __name__ == "__main__":
    main()
