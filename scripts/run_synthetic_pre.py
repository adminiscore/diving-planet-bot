"""Lanza conversaciones sinteticas contra PRE por Chatwoot y guarda cada turno (plan maestro, M0).

Cada conversacion se abre en el inbox "Synthetic Test" (tipo Api, separado del widget
real) y cada mensaje entra como `incoming`, asi que recorre el mismo camino que un
cliente: webhook -> dp-pre-bot -> respuesta en Chatwoot. Por cada turno guarda el
mensaje, la respuesta, las burbujas y el tiempo que ve el cliente (de `created_at` del
mensaje a la primera respuesta).

Los lotes viven en `docs/robustness/synthetic-runs/batches.json`. La salida es un JSONL
en `docs/robustness/synthetic-runs/<fecha>-<nombre>.jsonl`, que luego alimenta la foto:

    ENV_FILE=.env.dev python -m scripts.langfuse_snapshot --from-run docs/robustness/synthetic-runs/<fichero>.jsonl --label "..."

Uso (manda trafico real a PRE: gasta LLM y cuota de Langfuse; va de uno en uno a proposito):

    ENV_FILE=.env.dev python -m scripts.run_synthetic_pre --name m0 --sample m0
    ENV_FILE=.env.dev python -m scripts.run_synthetic_pre --name lote7 --batches 7
    ENV_FILE=.env.dev python -m scripts.run_synthetic_pre --name todo --all [--dry]

Claves: `SYNTH_CHATWOOT_TOKEN` (token de API de un agente de PRE), opcionales
`SYNTH_CHATWOOT_URL` (https://chatwoot.is-core.dev), `SYNTH_CHATWOOT_ACCOUNT` (1) y
`SYNTH_CHATWOOT_INBOX` (2). Se leen del entorno o de `ENV_FILE`.
"""

import argparse
import json
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from scripts.langfuse_snapshot import _env

RUNS_DIR = Path("docs/robustness/synthetic-runs")
BATCHES_FILE = RUNS_DIR / "batches.json"
REPLY_TIMEOUT_S = 90
EXTRA_BUBBLES_WAIT_S = 3


def load_batches() -> dict[str, list[tuple[str, list[str]]]]:
    doc = json.loads(BATCHES_FILE.read_text(encoding="utf-8"))
    return {k: [(c["tag"], c["turns"]) for c in v["cases"]] for k, v in doc["batches"].items()}


def select_cases(batches: dict, sample: str | None, only: list[str] | None) -> list[tuple[str, str, list[str]]]:
    if only:
        return [(b, tag, turns) for b in only for tag, turns in batches[b]]
    if sample == "m0":
        # Muestra de la linea base M0 (2026-09-17): largas, frontera entre rutas y grupos
        # mixtos enteros; 15 largas del lote 6 y 15 cortas de cada lote 2-4.
        pick = [(b, t, turns) for b in ("5", "7", "8") for t, turns in batches[b]]
        pick += [("6", t, turns) for t, turns in batches["6"][::10]][:5]
        pick += [("6", t, turns) for t, turns in batches["6"][3::5]][:10]
        for b in ("2", "3", "4"):
            pick += [(b, t, turns) for t, turns in batches[b][::3]][:15]
        seen: set[tuple[str, str]] = set()
        return [p for p in pick if (p[0], p[1]) not in seen and not seen.add((p[0], p[1]))]
    return [(b, tag, turns) for b, cases in batches.items() for tag, turns in cases]


class Chatwoot:
    def __init__(self, base: str, token: str, account: int, inbox: int):
        self.base, self.token, self.account, self.inbox = base.rstrip("/"), token, account, inbox

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.base}/api/v1/accounts/{self.account}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            # `Api-Access-Token` con guion: con guion bajo lo descarta el proxy de PRE.
            headers={"Api-Access-Token": self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)

    def new_conversation(self, tag: str) -> int:
        contact = self._req(
            "POST",
            "/contacts",
            {"inbox_id": self.inbox, "name": f"Synth {tag}", "identifier": f"synth-{tag}-{uuid.uuid4().hex[:8]}"},
        )["payload"]
        conv = self._req(
            "POST",
            "/conversations",
            {
                "source_id": contact["contact_inbox"]["source_id"],
                "inbox_id": self.inbox,
                "contact_id": contact["contact"]["id"],
                "status": "open",
            },
        )
        return conv["id"]

    def send(self, conv: int, text: str) -> dict:
        return self._req("POST", f"/conversations/{conv}/messages", {"content": text, "message_type": "incoming"})

    def replies_after(self, conv: int, msg_id: int) -> list[dict]:
        msgs = self._req("GET", f"/conversations/{conv}/messages")["payload"]
        return [m for m in msgs if m["id"] > msg_id and m["message_type"] == 1 and not m.get("private")]


def run_turn(cw: Chatwoot, conv: int, text: str) -> dict:
    sent = cw.send(conv, text)
    t0 = time.monotonic()
    while time.monotonic() - t0 < REPLY_TIMEOUT_S:
        time.sleep(1)
        if cw.replies_after(conv, sent["id"]):
            time.sleep(EXTRA_BUBBLES_WAIT_S)  # burbujas extra del mismo turno
            msgs = cw.replies_after(conv, sent["id"])
            return {
                "reply": "\n---\n".join(m["content"] or "" for m in msgs),
                "bubbles": len(msgs),
                "client_latency_s": round(msgs[0]["created_at"] - sent["created_at"], 1),
            }
    return {"reply": None, "bubbles": 0, "client_latency_s": None}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="nombre corto de la ejecucion (va en el fichero)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sample", choices=["m0"])
    group.add_argument("--batches", help="lotes separados por coma, p. ej. 5,7")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry", action="store_true", help="solo cuenta conversaciones y turnos")
    args = parser.parse_args(argv)

    cases = select_cases(load_batches(), args.sample, args.batches.split(",") if args.batches else None)
    print(f"{len(cases)} conversaciones, {sum(len(t) for _, _, t in cases)} turnos", flush=True)
    if args.dry:
        return 0

    token = _env("SYNTH_CHATWOOT_TOKEN")
    if not token:
        print("Falta SYNTH_CHATWOOT_TOKEN (entorno o ENV_FILE).", file=sys.stderr)
        return 2
    cw = Chatwoot(
        _env("SYNTH_CHATWOOT_URL") or "https://chatwoot.is-core.dev",
        token,
        int(_env("SYNTH_CHATWOOT_ACCOUNT") or 1),
        int(_env("SYNTH_CHATWOOT_INBOX") or 2),
    )
    out = RUNS_DIR / f"{datetime.now(UTC):%Y-%m-%d}-{args.name}.jsonl"
    print(f"Guardando en {out}", flush=True)

    failures = 0
    with out.open("a", encoding="utf-8") as fh:
        for n, (batch, tag, turns) in enumerate(cases, 1):
            try:
                conv = cw.new_conversation(tag)
            except Exception as exc:  # noqa: BLE001 — una conversacion que no se crea no para la tanda
                print(f"!!! no se pudo crear {tag}: {exc}", flush=True)
                failures += 1
                if failures >= 3:
                    break
                continue
            print(f"[{n}/{len(cases)}] lote {batch} {tag} conv {conv}", flush=True)
            for i, text in enumerate(turns, 1):
                result = run_turn(cw, conv, text)
                record = {
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "batch": batch,
                    "tag": tag,
                    "conv": conv,
                    "turn": i,
                    "turns": len(turns),
                    "msg": text,
                    **result,
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"  t{i} {result['client_latency_s']}s {result['bubbles']}b", flush=True)
                if result["reply"] is None:
                    print(f"!!! sin respuesta en {REPLY_TIMEOUT_S} s, paso a la siguiente conversacion", flush=True)
                    failures += 1
                    break
                failures = 0
                time.sleep(2)
            if failures >= 3:
                print("!!! 3 fallos seguidos, paro", flush=True)
                break
    print(f"FIN {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
