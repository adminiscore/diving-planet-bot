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
import logging
_TRAZA = []
class _Traza(logging.Handler):
    def emit(self, rec):
        m = rec.getMessage()
        if any(t in m for t in ("[EXTRACT]", "[LLM_EXTRACTOR]", "[CORE]", "[INTENT]", "[HECHOS]", "[RAG][LAT5]")):
            _TRAZA.append(m[:400])
logging.getLogger().addHandler(_Traza())
logging.getLogger().setLevel(logging.INFO)
CAMPOS = ("core_pending_slot", "detected_activity", "is_certified", "location", "detected_group_size",
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


def _fichero(nombre: str) -> Path:
    return CHARLAS / f"{nombre}.jsonl"


def _filas(nombre: str) -> list[dict]:
    f = _fichero(nombre)
    if not f.exists():
        raise SystemExit(f"no existe la charla {nombre}: ábrela con `nueva --nombre {nombre}`")
    return [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _nueva(nombre: str) -> None:
    CHARLAS.mkdir(parents=True, exist_ok=True)
    f = _fichero(nombre)
    if f.exists():
        raise SystemExit(f"ya existe {f}")
    f.write_text("", encoding="utf-8")
    print(f"charla {nombre} -> {f} (rama {_git('rev-parse', '--abbrev-ref', 'HEAD')}, {_git('rev-parse', '--short', 'HEAD')})")


def _di(nombre: str, mensaje: str, entorno: dict[str, str] | None = None) -> None:
    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    filas = _filas(nombre)
    estado = filas[-1]["guardado"] if filas else None
    script = (f"CONV = {('charla-rama-' + nombre)!r}\nMENSAJE = {mensaje!r}\nESTADO = {estado!r}\n{_REMOTO}")
    r = pre_ssh(docker_python(entorno or {}, codigo_local=subir_codigo_local()), input_text=script, timeout=300)
    salida = next((json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")), None)
    if salida is None:
        raise SystemExit("el turno no devolvió nada; stderr de PRE:\n" + (r.stderr or "")[-2000:])
    fila = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "turno": len(filas) + 1,
            "commit": _git("rev-parse", "--short", "HEAD"), "msg": mensaje, **salida}
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
        if accion == "di":
            p.add_argument("mensaje")
            p.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                           help="variable de entorno SOLO en este turno (p. ej. RAG_KB_ESQUEMA=kb_v2_gadea: la base curada"
                                " de la rama, cargada con `scripts.kb_v2 --esquema`)")
    args = ap.parse_args()
    if args.accion == "nueva":
        _nueva(args.nombre)
    elif args.accion == "di":
        _di(args.nombre, args.mensaje, dict(e.split("=", 1) for e in args.env))
    else:
        _ver(args.nombre)


if __name__ == "__main__":
    main()
