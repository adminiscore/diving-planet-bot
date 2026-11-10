"""Simplificar (10-nov), V1: Luna en UNA llamada por turno, con la base del bot y salida estructurada. Prototipo fuera de src.

Diseño: `docs/robustness/caln/diseno-simple.md` (acordado con el Claude de Álvaro, #3756-#3758). Luna lee solo lo que el bot
puede tener en producción: las piezas de `judge_golden_set.load_reference` sin `escalation_rules.json` (que solo lee el
juez) y con las decisiones de Gadea como reglas. Recibe la línea del cierre del 3.1 con el reloj fijo y devuelve, en la misma
llamada, su texto, lo que entendió del cliente (que se le vuelve a dar en el turno siguiente, como estado) y si hay que pasar
con una persona. Cada línea sale con el formato del panel, para `juez_claude --panel` y `marcador`. Las instrucciones se
escriben una vez y no se ajustan con lo que salga.

    ENV_FILE=<repo>/.env.dev python -m scripts.simple_v1 --out docs/robustness/caln/simple/v1-a.jsonl
    ENV_FILE=<repo>/.env.dev python -m scripts.simple_v1 --banco <fichero> --out <salida> --ids visto-6914
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from scripts.linea_base_luna import _DIAS, MODELO, _clave

RAIZ = Path(__file__).resolve().parents[1]
INSTRUCCIONES = """Eres Coral, el asistente de reservas por WhatsApp de Diving Planet (buceo en las Islas del Rosario, Colombia). Atiendes a clientes que piden información o quieren reservar.

Cómo trabajas:
- Contestas en el idioma del cliente.
- Escribes como una persona del equipo por WhatsApp: breve y al grano, unos 300 caracteres como mucho salvo que una regla te pida dar varios datos (por ejemplo los dos orígenes, o USD y COP), sin listas salvo que el cliente compare o pida varias cosas, y con una pregunta como mucho, solo si la necesitas para avanzar. No repites el saludo ni lo que ya dijiste.
- Tu única fuente es la BASE de abajo: precios, planes, horarios, políticas, enlaces de reserva y las reglas del negocio. Las reglas del negocio mandan sobre lo demás.
- No inventas nada que no esté en la base. Si algo no está o no se puede resolver aquí, lo dices y pasas al cliente con una persona del equipo.
- Para pasar a un cliente con una persona, se lo dices en tu mensaje (el equipo sigue la conversación por este mismo chat) y lo marcas en «pasar».

Respondes SIEMPRE con un único objeto JSON, sin nada fuera de él:
{"entendido": {"origen": "cartagena" | "islas" | null, "hotel": texto o null, "nacionalidad": "colombiana" | "residente" | "extranjera" | null, "personas": número o null, "edades": lista de números o null, "actividad": texto o null, "plan": id del catálogo o null, "certificado": true | false | null, "refresher": true | false | null, "fecha": texto o null, "dias": número o null, "quiere_reservar": true | false, "ya_reservo": true | false},
 "pasar": {"si": true | false, "motivo": texto o null},
 "texto": tu mensaje al cliente, coherente con «entendido» y con «pasar»}
En «entendido» pones lo que sabes del cliente hasta ahora (lo que ya entendiste en turnos anteriores más lo nuevo de su mensaje). Si un dato no lo ha dicho, null: no lo adivines.

BASE:
{base}"""
_FUERA = ("### escalation_rules.json",)
_ENTENDIDO_VACIO = {"origen": None, "hotel": None, "nacionalidad": None, "personas": None, "edades": None, "actividad": None,
                    "plan": None, "certificado": None, "refresher": None, "fecha": None, "dias": None, "quiere_reservar": False,
                    "ya_reservo": False}


def base_del_bot() -> str:
    """Lo que el bot puede tener en producción: `load_reference` sin lo que solo lee el juez, y las decisiones como reglas."""
    from scripts.judge_golden_set import REFERENCIA_POR_DEFECTO, load_reference

    secciones = load_reference(REFERENCIA_POR_DEFECTO).split("\n\n### ")
    secciones = [secciones[0], *("### " + s for s in secciones[1:])]
    quedan = [s for s in secciones if not s.startswith(_FUERA) and not s.startswith("### Decisiones del negocio")]
    lugares = (RAIZ / "data" / "knowledge_base" / "lugares.json").read_text(encoding="utf-8-sig")
    return "\n\n".join([*quedan, "### lugares.json (hoteles con recogida, lugares de las islas y barrios)\n" + lugares,
                        reglas_del_negocio()])


def reglas_del_negocio() -> str:
    """Las decisiones de Gadea como reglas para el escritor: su `instruccion_es` si la tienen; si no, su texto."""
    datos = json.loads((RAIZ / "data" / "knowledge_base" / "decisiones.json").read_text(encoding="utf-8"))["decisiones"]
    reglas = [re.sub(r"^Decisión de Gadea:\s*", "", d.get("instruccion_es") or d["texto"]) for d in datos]
    return "### Reglas del negocio (decisiones de Gadea)\n" + "\n".join(f"- {r}" for r in reglas)


def sistema_para(base: str, reloj: str | None, lang: str = "es") -> str:
    from zoneinfo import ZoneInfo

    from src.agents.rutas.contexto_rag import _el_cierre

    t = datetime.fromisoformat(reloj) if reloj else datetime.now(ZoneInfo("America/Bogota"))
    ahora = f"{_DIAS[t.weekday()]} {t:%Y-%m-%d}, {t:%H:%M}"
    return INSTRUCCIONES.replace("{base}", base) + f"\n\nAhora es {ahora}, hora de Colombia. {_el_cierre(t, lang)}"


def llamar(clave: str, mensajes: list[dict]) -> tuple[str, dict]:
    cuerpo = json.dumps({"model": MODELO, "messages": mensajes, "temperature": 0, "max_completion_tokens": 1200,
                         "reasoning_effort": "none", "response_format": {"type": "json_object"}}).encode()
    espera = 2.0
    for intento in range(7):
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=cuerpo,
                                     headers={"Authorization": "Bearer " + clave, "Content-Type": "application/json"})
        t0 = time.time()
        try:
            d = json.load(urllib.request.urlopen(req, timeout=180))
            u = d.get("usage") or {}
            return d["choices"][0]["message"]["content"] or "", {"s": round(time.time() - t0, 2), "u": {
                "in": u.get("prompt_tokens", 0), "ca": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                "out": u.get("completion_tokens", 0)}}
        except urllib.error.HTTPError as e:
            texto = re.sub(r"sk-[A-Za-z0-9_-]+", "[clave]", e.read().decode("utf-8", "replace"))[:200]
            if e.code not in (408, 409, 429, 500, 502, 503, 504) or intento == 6 or "credit_balance" in texto:
                raise RuntimeError(f"HTTP {e.code}: {texto}")
        except (urllib.error.URLError, TimeoutError) as e:
            if intento == 6:
                raise RuntimeError(type(e).__name__)
        time.sleep(espera + random.random())
        espera = min(espera * 2, 40)
    raise RuntimeError("sin respuesta")


def leer(salida: str) -> tuple[dict | None, str | None]:
    """El JSON de Luna, o None con el motivo si no se puede leer."""
    try:
        d = json.loads(salida)
    except json.JSONDecodeError as exc:
        return None, f"JSON roto: {exc.msg}"
    if not isinstance(d, dict) or not isinstance(d.get("texto"), str):
        return None, "sin «texto»"
    return d, None


def cliente(clave: str, base: str, d: dict, reloj: str | None) -> list[dict]:
    historial = [{"role": "system", "content": sistema_para(base, reloj)}]
    entendido, filas = dict(_ENTENDIDO_VACIO), []
    for i, msg in enumerate(d["turnos"], 1):
        mensajes = [*historial, {"role": "system", "content": "Lo que ya entendiste del cliente: "
                                 + json.dumps(entendido, ensure_ascii=False)}, {"role": "user", "content": msg}]
        t0, errores, pasar = time.time(), 0, None
        try:
            salida, m = llamar(clave, mensajes)
            datos, fallo = leer(salida)
            if datos is None:
                texto, errores = salida, 1
            else:
                texto, pasar = datos["texto"], datos.get("pasar")
                entendido = {**entendido, **{k: v for k, v in (datos.get("entendido") or {}).items() if k in _ENTENDIDO_VACIO}}
        except RuntimeError as exc:
            texto, m, errores, fallo = f"ERROR {exc}", {"s": 0, "u": {"in": 0, "ca": 0, "out": 0}}, 1, str(exc)
        historial += [{"role": "user", "content": msg}, {"role": "assistant", "content": texto}]
        filas.append({"dialogo": d["id"], "rep": 0, "turn": i, "msg": msg, "reply": texto, "rag": [], "juicios": [],
                      "segundos": round(time.time() - t0, 2), "estado": {"entendido": dict(entendido), "pasar": pasar},
                      "traza": [f"[SIMPLE] {fallo}"] if errores else [], "reloj": reloj,
                      "metricas": [{"turn_type": "simple-v1", "llm_errores": errores,
                                    "llamadas": [{"p": "simple-v1", "m": MODELO, **m}]}]})
    return filas


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--banco", default="docs/robustness/caln/panel-vara.json")
    ap.add_argument("--reloj", default="alterno", help="como en reproducir_juez_pre; alterno por defecto")
    ap.add_argument("--ids", help="solo estos diálogos, separados por comas (para probar)")
    args = ap.parse_args(argv)
    from scripts.reproducir_juez_pre import relojes_de

    dialogos = json.loads(Path(args.banco).read_text(encoding="utf-8"))["dialogos"]
    if args.ids:
        dialogos = [d for d in dialogos if d["id"] in args.ids.split(",")]
    relojes = relojes_de([d["id"] for d in dialogos], args.reloj)
    base, clave = base_del_bot(), _clave()
    filas: list[dict] = []
    with cf.ThreadPoolExecutor(4) as ex:
        for hecho in ex.map(lambda d: cliente(clave, base, d, relojes.get(d["id"])), dialogos):
            filas += hecho
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8", newline="\n")
    llamadas = [f["metricas"][0]["llamadas"][0]["u"] for f in filas]
    ent, cac, sal = (sum(u[k] for u in llamadas) for k in ("in", "ca", "out"))
    usd = (ent - cac) * 0.10 / 1e6 + cac * 0.01 / 1e6 + sal * 0.50 / 1e6
    errores = sum(f["metricas"][0]["llm_errores"] for f in filas)
    print(f"{len(filas)} turnos de {len(dialogos)} clientes → {args.out}; base {len(base)} caracteres; entrada {ent} (cacheada "
          f"{cac}), salida {sal}, ~{usd:.3f} $; turnos con fallo {errores}")
    return 3 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
