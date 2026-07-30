"""Snapshot de TODA la superficie de prompt del bot (Fase 3.2 del refactor).

Renderiza cada prompt de sistema y cada tool-schema que el bot envía al LLM, en
todas sus variantes relevantes (idioma, y los argumentos que cambian el texto:
campos que faltan, slot preguntado, nombre del cliente, notas ya capturadas), y
escribe un JSON con el texto íntegro + su SHA-256.

**Para qué sirve:** es la prueba de equivalencia de cualquier refactor que MUEVA
prompts sin querer cambiarlos (`src/prompts/`, Fase 3.2). Se toma un snapshot
antes, se refactoriza, se toma otro, y `--compare` exige diff vacío. También
sirve para revisar la superficie de prompt entera de una lectura (el objetivo
"prompts legibles/revisables/versionados" del §4 del plan).

Uso:

    python scripts/snapshot_prompts.py -o antes.json
    ...refactor...
    python scripts/snapshot_prompts.py -o despues.json --compare antes.json

Nota: no hace NINGUNA llamada al LLM (solo renderiza texto). Requiere las env
vars del proyecto porque los módulos importan `settings` al cargarse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import llm_extractor, rag_agent  # noqa: E402
from src.prompts import booking as _booking  # noqa: E402
from src.prompts import info as _info  # noqa: E402
from src.prompts import memory as _memory  # noqa: E402
from src.prompts import router as _router  # noqa: E402

LANGS = ("es", "en")

# Qué símbolos de `src/prompts/` ha tocado el último `_collect()`. Lo alimenta el
# proxy de abajo, así la cobertura del snapshot se DERIVA de lo que de verdad se
# renderiza (no de una lista a mano que se desincroniza).
# `tests/test_prompts_surface.py` compara esto contra los símbolos públicos
# reales de cada módulo: un prompt nuevo que nadie renderice falla el test, y no
# se queda fuera de la red de seguridad sin que nos enteremos.
TOUCHED: set[str] = set()


class _Tracked:
    """Envoltorio de un módulo de prompts que anota cada símbolo leído."""

    def __init__(self, module):
        self._module = module

    def __getattr__(self, name: str):
        TOUCHED.add(f"{self._module.__name__}.{name}")
        return getattr(self._module, name)


router = _Tracked(_router)
booking = _Tracked(_booking)
info = _Tracked(_info)
memory = _Tracked(_memory)


def _collect() -> dict[str, str]:
    """dict {clave estable -> texto renderizado}. La clave lleva el nodo dueño
    (router/booking/info/memory, ver `docs/agent-arch-design.md` §7) para que el
    snapshot se lea como el mapa prompt→nodo."""
    out: dict[str, str] = {}

    def add(key: str, value: str) -> None:
        assert key not in out, f"clave duplicada en el snapshot: {key}"
        out[key] = value

    def add_json(key: str, value: object) -> None:
        add(key, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))

    # ── router · detect_routing_signals ──────────────────────────────────────
    for lang in LANGS:
        add(f"router/routing_signals.system.{lang}", router.routing_system_prompt(lang))
    add_json("router/routing_signals.tool", router.ROUTING_TOOL)

    # ── booking · extracción (fill_gaps) ─────────────────────────────────────
    # El texto interpola los campos pedidos: se cubren el caso de 1 campo, el de
    # varios, y el de TODOS los extraíbles (el máximo real).
    field_variants = {
        "one": ["activity"],
        "few": ["activity", "group_size", "location"],
        "all": list(llm_extractor.EXTRACTABLE_FIELDS),
    }
    for lang in LANGS:
        for name, fields in field_variants.items():
            add(
                f"booking/extraction.system.{lang}.{name}",
                booking.extraction_system_prompt(lang, fields),
            )
    add_json("booking/extraction.tool", booking.EXTRACTION_TOOL)

    # ── booking · señales especiales (detect_special_signals) ─────────────────
    for lang in LANGS:
        add(f"booking/special_signals.system.{lang}", booking.signals_system_prompt(lang))
    add_json("booking/special_signals.tool", booking.SIGNALS_TOOL)

    # ── booking · resolutor de slot (anti-bucle Fase C) ──────────────────────
    # Todos los slots del spec, en ambos idiomas: el prompt y el tool cambian
    # por slot (tipo, enum, significado del valor).
    for slot in sorted(booking.SLOT_RESOLVER_SPEC):
        for lang in LANGS:
            add(
                f"booking/slot_resolver.system.{slot}.{lang}",
                booking.slot_resolver_prompt(slot, lang),
            )
        add_json(f"booking/slot_resolver.tool.{slot}", booking.slot_resolver_tool(slot))

    # ── booking · acuse cálido (compose_acknowledgement) ─────────────────────
    for lang in LANGS:
        add(f"booking/acknowledgement.system.{lang}.noname", booking.acknowledgement_system_prompt(lang, None))
        add(f"booking/acknowledgement.system.{lang}.named", booking.acknowledgement_system_prompt(lang, "Sofía"))

    # ── booking/setup · detección de idioma ──────────────────────────────────
    add("booking/language_detect.prompt.template", booking.LANGUAGE_DETECT_PROMPT)

    # ── memoria · notes (extract_notes) ──────────────────────────────────────
    for lang in LANGS:
        add(f"memory/notes.system.{lang}.empty", memory.notes_system_prompt(lang, []))
        add(
            f"memory/notes.system.{lang}.existing",
            memory.notes_system_prompt(lang, ["rodilla operada del padre", "aniversario"]),
        )
    add_json("memory/notes.tool", memory.NOTES_TOOL)

    # ── memoria · resumen de conversación ────────────────────────────────────
    add("memory/summary.system.es", memory.SUMMARY_SYSTEM_ES)
    add("memory/summary.system.en", memory.SUMMARY_SYSTEM_EN)

    # ── info · reescritura de query (RAG) ────────────────────────────────────
    add("info/query_rewrite.system.es", info.QUERY_REWRITE_ES)
    add("info/query_rewrite.system.en", info.QUERY_REWRITE_EN)

    # ── info · grounding (verificación de respuesta) ─────────────────────────
    add("info/grounding_verify.system.es", info.GROUNDING_VERIFY_ES)
    add("info/grounding_verify.system.en", info.GROUNDING_VERIFY_EN)

    # ── info · persona Coral + seguridad + reglas (prompt de respuesta RAG) ──
    # Piezas por separado (lo que se mueve a src/prompts/info.py) y el prompt
    # ENSAMBLADO por `build_system_prompt` (lo que el LLM recibe de verdad —
    # incluye el bloque de tono leído de brand_tone.json). Sin `query` para que
    # sea determinista (el bloque few-shot depende de la query).
    add("info/rag.intro.es", info.RAG_INTRO_ES)
    add("info/rag.intro.en", info.RAG_INTRO_EN)
    add("info/rag.security.es", info.RAG_SECURITY_ES)
    add("info/rag.security.en", info.RAG_SECURITY_EN)
    add("info/rag.body.es", info.RAG_BODY_ES)
    add("info/rag.body.en", info.RAG_BODY_EN)
    for lang in LANGS:
        add(f"info/rag.system.assembled.{lang}", rag_agent.build_system_prompt(lang))

    return out


def _snapshot() -> dict:
    collected = _collect()
    return {
        "count": len(collected),
        "prompts": {
            key: {
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "chars": len(text),
                "text": text,
            }
            for key, text in sorted(collected.items())
        },
    }


def _compare(current: dict, baseline_path: Path) -> int:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    old, new = baseline["prompts"], current["prompts"]
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = sorted(k for k in set(old) & set(new) if old[k]["sha256"] != new[k]["sha256"])

    for key in removed:
        print(f"FALTA    {key}")
    for key in added:
        print(f"NUEVO    {key}")
    for key in changed:
        print(f"CAMBIADO {key}  {old[key]['sha256'][:12]} -> {new[key]['sha256'][:12]}")

    if removed or added or changed:
        print(
            f"\n[FAIL] {len(removed)} faltan, {len(added)} nuevos, {len(changed)} cambiados "
            f"(de {len(old)} en el baseline)."
        )
        return 1
    print(f"[OK] {len(new)} prompts idénticos byte a byte al baseline.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", type=Path, help="Escribe el snapshot JSON aquí.")
    parser.add_argument("--compare", type=Path, help="Compara contra un snapshot previo.")
    args = parser.parse_args()

    current = _snapshot()
    if args.out:
        args.out.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[SNAPSHOT] {current['count']} prompts -> {args.out}")
    else:
        print(f"[SNAPSHOT] {current['count']} prompts renderizados")

    if args.compare:
        return _compare(current, args.compare)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
