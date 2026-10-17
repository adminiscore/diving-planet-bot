"""G3 (17-oct, decisión de Gadea): Claude contra el chatbot, EN DIRECTO. Un turno cada vez, por el mismo canal que las
rondas (Chatwoot -> PRE), para que quien prueba se adapte a lo que contesta el bot como haría un cliente de verdad.

    ENV_FILE=.env.dev python -m scripts.charla_pre nueva --nombre g3-reserva-familia     # -> conv 1234
    ENV_FILE=.env.dev python -m scripts.charla_pre di --conv 1234 "hola, somos 4 y queremos bucear"
    ENV_FILE=.env.dev python -m scripts.charla_pre ver --conv 1234                        # la charla entera

Cada turno se guarda en `docs/robustness/g3/charlas/<conv>.jsonl` (mensaje, respuesta, latencia): los fallos que se
encuentren pasan al banco con su conversación. Coste: el del bot en PRE (céntimos por turno).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_synthetic_pre import Chatwoot, _env, run_turn

ROOT = Path(__file__).resolve().parent.parent
CHARLAS = ROOT / "docs/robustness/g3/charlas"


def _chatwoot() -> Chatwoot:
    token = _env("SYNTH_CHATWOOT_TOKEN")
    if not token:
        sys.exit("Falta SYNTH_CHATWOOT_TOKEN (entorno o ENV_FILE).")
    return Chatwoot(_env("SYNTH_CHATWOOT_URL") or "https://chatwoot.is-core.dev", token,
                    int(_env("SYNTH_CHATWOOT_ACCOUNT") or 1), int(_env("SYNTH_CHATWOOT_INBOX") or 2))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="accion", required=True)
    n = sub.add_parser("nueva", help="abre una conversación nueva")
    n.add_argument("--nombre", default="g3")
    d = sub.add_parser("di", help="manda un mensaje y espera la respuesta")
    d.add_argument("--conv", type=int, required=True)
    d.add_argument("mensaje")
    v = sub.add_parser("ver", help="imprime la charla guardada")
    v.add_argument("--conv", type=int, required=True)
    args = ap.parse_args()

    CHARLAS.mkdir(parents=True, exist_ok=True)
    if args.accion == "nueva":
        conv = _chatwoot().new_conversation(args.nombre)
        (CHARLAS / f"{conv}.jsonl").write_text("", encoding="utf-8")
        print(f"conv {conv} ({args.nombre})")
        return
    ruta = CHARLAS / f"{args.conv}.jsonl"
    if args.accion == "ver":
        for ln in ruta.read_text(encoding="utf-8").splitlines():
            t = json.loads(ln)
            print(f"[{t['turno']}] CLIENTE: {t['msg']}\n    BOT ({t['client_latency_s']} s): {t['reply']}\n")
        return
    turnos = len(ruta.read_text(encoding="utf-8").splitlines()) if ruta.exists() else 0
    r = run_turn(_chatwoot(), args.conv, args.mensaje)
    fila = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "conv": args.conv, "turno": turnos + 1,
            "msg": args.mensaje, **r}
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"BOT ({r['client_latency_s']} s, {r['bubbles']} burbuja/s):\n{r['reply']}")


if __name__ == "__main__":
    main()
