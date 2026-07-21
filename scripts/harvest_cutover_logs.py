"""Fase 6 (docs/robustness/plan.md §4, docs/robustness/review-2026-07-21.md H1/H8):
cierre del bucle de datos reales.

Parsea las líneas `[EXTRACT][CUTOVER] applied=... msg=...` y
`[EXTRACT][SHADOW] msg=... gaps_before=... llm_patch=...` que el bot emite en
producción (supervisor.py) y las convierte en:

  - (default) casos CANDIDATOS para docs/robustness/eval-set.json — con el
    `message` real y los campos que el LLM rellenó como `expected` de PARTIDA.
    OJO: ese `expected` NO es ground truth — hay que validarlo contra el pipeline
    real antes de fijarlo (la lección de proceso del plan). El script lo marca
    explícitamente en `notes` y en un aviso.
  - (--summary) un contador por campo/dominio de cuántas veces disparó el cutover
    en el tráfico real (observabilidad, review H8).

Uso típico contra PRE (los logs no salen del VPS a mano):

    ssh vps "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs --summary
    ssh vps "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs > candidatos.json

o sobre un fichero de logs ya descargado:

    python -m scripts.harvest_cutover_logs --file dp-pre.log --summary

El objetivo NO es añadir casos automáticamente al eval-set (eso reproduciría el
error de "asumir en vez de medir"), sino darle a un humano la lista deduplicada
de mensajes reales interesantes para revisar y curar.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from datetime import date

# Los dominios y sus campos, espejo de _*_CUTOVER_FIELDS en supervisor.py.
DOMAIN_FIELDS = {
    "certification": {"is_certified", "activity"},
    "group": {"group_size", "group_allocation", "ages"},
    "location": {"location", "island", "hotel"},
}

# Greedy dict/list captures so nested dicts (e.g. group_allocation={'x': 2})
# are grabbed whole; msg is non-greedy up to the next key.
_CUTOVER_RE = re.compile(r"\[EXTRACT\]\[CUTOVER\]\s+applied=(\{.*\})\s+msg=(.+?)\s*$")
_SHADOW_RE = re.compile(
    r"\[EXTRACT\]\[SHADOW\]\s+msg=(.+?)\s+gaps_before=(\[.*\])\s+llm_patch=(\{.*\})\s*$"
)


def _safe_literal(text: str):
    """ast.literal_eval that returns None on anything malformed (logs can be cut)."""
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _domain_of(field: str) -> str:
    for domain, fields in DOMAIN_FIELDS.items():
        if field in fields:
            return domain
    return "other"


def parse_lines(lines) -> list[dict]:
    """Parse CUTOVER/SHADOW log lines into records: {source_kind, message, patch}.

    Malformed / truncated lines are skipped silently (production logs get cut).
    """
    records: list[dict] = []
    for line in lines:
        m = _CUTOVER_RE.search(line)
        if m:
            patch = _safe_literal(m.group(1))
            message = _safe_literal(m.group(2))
            if isinstance(patch, dict) and patch and isinstance(message, str):
                records.append({"source_kind": "cutover", "message": message, "patch": patch})
            continue
        m = _SHADOW_RE.search(line)
        if m:
            message = _safe_literal(m.group(1))
            patch = _safe_literal(m.group(3))
            if isinstance(patch, dict) and patch and isinstance(message, str):
                records.append({"source_kind": "shadow", "message": message, "patch": patch})
    return records


def summarize(records: list[dict]) -> dict:
    """Per-field and per-domain firing counts (observability, H8)."""
    by_field: Counter = Counter()
    by_domain: Counter = Counter()
    by_kind: Counter = Counter()
    for rec in records:
        by_kind[rec["source_kind"]] += 1
        for field in rec["patch"]:
            by_field[field] += 1
            by_domain[_domain_of(field)] += 1
    return {
        "records": len(records),
        "by_kind": dict(by_kind),
        "by_domain": dict(by_domain.most_common()),
        "by_field": dict(by_field.most_common()),
    }


def to_candidates(records: list[dict]) -> list[dict]:
    """Deduplicated candidate eval-set cases (one per unique message).

    `expected` is the LLM patch as a STARTING point — must be human-validated
    against the real IntentDetector pipeline before being trusted (plan §5).
    """
    seen: dict[str, dict] = {}
    for rec in records:
        msg = rec["message"].strip()
        if not msg or msg in seen:
            continue
        seen[msg] = rec["patch"]
    today = date.today().isoformat()
    candidates = []
    for i, (msg, patch) in enumerate(seen.items(), 1):
        candidates.append({
            "id": f"harvested-{today}-{i:03d}",
            "message": msg,
            "lang": "es" if re.search(r"[áéíóúñ¿¡]", msg) else "unknown",
            "expected": patch,
            "source": f"harvested-from-PRE-logs-{today}",
            "notes": "CANDIDATO sin validar — el `expected` viene del LLM, NO es ground truth. "
                     "Validar contra IntentDetector real + routing antes de fijarlo (plan.md §5).",
        })
    return candidates


def _read_lines(path: str | None):
    if path:
        with open(path, encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        yield from sys.stdin


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cosecha logs [EXTRACT][CUTOVER]/[SHADOW] de PRE.")
    ap.add_argument("--file", help="Fichero de logs (por defecto: stdin).")
    ap.add_argument("--summary", action="store_true", help="Solo el contador por campo/dominio (H8).")
    args = ap.parse_args(argv)

    records = parse_lines(_read_lines(args.file))

    if args.summary:
        print(json.dumps(summarize(records), ensure_ascii=False, indent=2))
        return 0

    candidates = to_candidates(records)
    print(json.dumps({"cases": candidates}, ensure_ascii=False, indent=2))
    if candidates:
        print(
            f"\n# {len(candidates)} candidatos deduplicados. RECUERDA: valida cada `expected` "
            "contra el pipeline real antes de añadirlo al eval-set.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
