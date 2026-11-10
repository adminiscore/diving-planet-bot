"""Línea base (decidida por Gadea el 10-nov): Luna sola, con lo mismo que lee el juez y sin nuestras piezas, sobre el panel.

Luna recibe la referencia del juez entera (catálogo, enlaces, políticas, FAQ y decisiones: `judge_golden_set.load_reference`)
y la hora fija de cada diálogo (la misma regla que `reproducir_juez_pre --reloj`), y contesta turno a turno con todo el
historial. Sin Jev, sin extractor, sin tablas, sin compositor y sin correctores. Llama directamente a OpenAI con la clave del
bot (nunca se imprime); no toca PRE ni el código del bot. Las instrucciones se escribieron el 6-nov, una vez, sin mirar el
panel, y no se ajustan con lo que salga. Cada línea sale con el formato del panel, así que se juzga con
`scripts.juez_claude --panel` y se compara con `scripts.marcador`.

    ENV_FILE=<repo>/.env.dev python -m scripts.linea_base_luna --out docs/robustness/caln/panel/luna-sola-a.jsonl

Se compara con la versión actual en el mismo panel y con el umbral de 4 clientes (Gadea, 10-nov): 4 o más clientes con grave
menos que el bot, se replantea la arquitectura con el equipo; a menos de 4, deciden coste, latencia y control; 4 o más más,
se sigue con el plan. Solo es una medida.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODELO = "gpt-6-luna"  # el de `settings.rag_answer_model`
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
INSTRUCCIONES = """Eres Coral, el asistente de reservas por WhatsApp de Diving Planet (buceo en las Islas del Rosario, Colombia). Atiendes a clientes que piden información o quieren reservar.

Cómo trabajas:
- Contestas en el idioma del cliente, con mensajes breves, como en WhatsApp.
- Tu única fuente es la REFERENCIA de abajo: precios, planes, horarios, políticas, enlaces de reserva y decisiones del negocio. Las «Decisiones del negocio» mandan sobre lo demás.
- No inventes nada que no esté en la referencia. Si algo no está o no se puede resolver aquí, dilo y pasa al cliente con un asesor.
- Para pasar a un cliente con un asesor, dilo claramente en tu mensaje: el equipo sigue la conversación por este mismo chat.

REFERENCIA:
{referencia}"""


def sistema_para(referencia: str, reloj: str | None) -> str:
    """El prompt de sistema: la parte fija primero (se cachea entre diálogos) y la hora al final."""
    if reloj:
        t = datetime.fromisoformat(reloj)
        ahora = f"{_DIAS[t.weekday()]} {t:%Y-%m-%d}, {t:%H:%M}"
    else:
        ahora = datetime.now().astimezone().strftime("%Y-%m-%d, %H:%M")
    return INSTRUCCIONES.format(referencia=referencia) + f"\n\nAhora es {ahora}, hora de Colombia."


def _clave() -> str:
    env = Path(os.environ.get("ENV_FILE") or RAIZ.parent / "diving-planet-bot" / ".env.dev")
    for linea in env.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*OPENAI_API_KEY\s*=\s*(.*)", linea)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit(f"sin OPENAI_API_KEY en {env}")


def llamar(clave: str, mensajes: list[dict]) -> tuple[str, dict]:
    # Como `llm_client.adaptar_parametros` para los modelos nuevos: max_completion_tokens y sin razonar (si no, Luna rechaza
    # la temperatura 0).
    cuerpo = json.dumps({"model": MODELO, "messages": mensajes, "temperature": 0, "max_completion_tokens": 700,
                         "reasoning_effort": "none"}).encode()
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


def cliente(clave: str, referencia: str, d: dict, reloj: str | None) -> list[dict]:
    historial = [{"role": "system", "content": sistema_para(referencia, reloj)}]
    filas = []
    for i, msg in enumerate(d["turnos"], 1):
        historial.append({"role": "user", "content": msg})
        t0 = time.time()
        try:
            texto, m = llamar(clave, historial)
            errores = 0
        except RuntimeError as exc:
            texto, m, errores = f"ERROR {exc}", {"s": 0, "u": {"in": 0, "ca": 0, "out": 0}}, 1
        historial.append({"role": "assistant", "content": texto})
        filas.append({"dialogo": d["id"], "rep": 0, "turn": i, "msg": msg, "reply": texto, "rag": [], "juicios": [],
                      "segundos": round(time.time() - t0, 2), "estado": {}, "traza": [], "reloj": reloj,
                      "metricas": [{"turn_type": "luna-sola", "llm_errores": errores,
                                    "llamadas": [{"p": "luna-sola", "m": MODELO, **m}]}]})
    return filas


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--panel", default="docs/robustness/caln/panel-vara.json")
    ap.add_argument("--reloj", default="alterno", help="como en reproducir_juez_pre; alterno por defecto")
    ap.add_argument("--ids", help="solo estos diálogos, separados por comas (para probar)")
    args = ap.parse_args(argv)
    from scripts.judge_golden_set import REFERENCIA_POR_DEFECTO, load_reference
    from scripts.reproducir_juez_pre import relojes_de

    panel = json.loads((RAIZ / args.panel).read_text(encoding="utf-8"))["dialogos"]
    if args.ids:
        panel = [d for d in panel if d["id"] in args.ids.split(",")]
    relojes = relojes_de([d["id"] for d in panel], args.reloj)
    referencia, clave = load_reference(REFERENCIA_POR_DEFECTO), _clave()
    filas: list[dict] = []
    with cf.ThreadPoolExecutor(4) as ex:
        for hecho in ex.map(lambda d: cliente(clave, referencia, d, relojes.get(d["id"])), panel):
            filas += hecho
    Path(args.out).write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8", newline="\n")
    llamadas = [f["metricas"][0]["llamadas"][0]["u"] for f in filas]
    ent, cac, sal = (sum(u[k] for u in llamadas) for k in ("in", "ca", "out"))
    usd = (ent - cac) * 0.10 / 1e6 + cac * 0.01 / 1e6 + sal * 0.50 / 1e6
    errores = sum(f["metricas"][0]["llm_errores"] for f in filas)
    print(f"{len(filas)} turnos de {len(panel)} clientes → {args.out}; entrada {ent} (cacheada {cac}), salida {sal}, ~{usd:.3f} $; "
          f"errores {errores}")
    if errores:
        print(f"⚠️ {errores} turnos sin respuesta de Luna (¿saldo de OpenAI?): esta tirada no vale")
    return 3 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
