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

from src.agents import llm_extractor, rag_agent, redactor_hechos  # noqa: E402
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
    # gen-3 (20-oct, flag `dieta_no_es_medica`): la misma definición con la exclusión de la dieta (sobre una copia).
    tool_dieta = json.loads(json.dumps(router.ROUTING_TOOL))
    router.con_dieta_no_es_medica(tool_dieta)
    add_json("router/routing_signals.tool.dieta_no_es_medica", tool_dieta)

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
    # Variante con los campos que solo viajan cuando el nucleo los pide (hallazgo A).
    add_json("booking/extraction.tool+mixed_nationality", booking.extraction_tool(["mixed_nationality"]))
    add_json("booking/extraction.tool+evidence", booking.extraction_tool(["evidence"]))
    add_json("booking/evidence.fields", list(booking.EVIDENCE_FIELDS))

    # (mej-1d: el veto y el prompt combinado se quitaron; no corrian desde ex-9.)

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
    # 18-oct (flag `resolutor_sin_contradicciones`): lo que se añade al prompt del resolutor.
    add("booking/slot_resolver.contradiccion", booking.SLOT_RESOLVER_CONTRADICCION)
    # G3-06 (flag `baru_no_es_rosario`): los textos de lugar sin Barú entre "las islas".
    for lang in LANGS:
        add(f"booking/slot_resolver.system.location.{lang}.sin_baru",
            booking.lugar_sin_baru(booking.slot_resolver_prompt("location", lang)))
    add_json("booking/extraction.tool.sin_baru", booking.tool_sin_baru(booking.EXTRACTION_TOOL))

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
    add("info/rag.pase_ofrecido.es", info.RAG_PASE_OFRECIDO_ES)
    add("info/rag.pase_ofrecido.en", info.RAG_PASE_OFRECIDO_EN)
    add("info/rag.sin_precio.es", info.RAG_SIN_PRECIO_ES)
    add("info/rag.sin_precio.en", info.RAG_SIN_PRECIO_EN)
    add("info/redactor_hechos.es", info.REDACTOR_HECHOS_ES)
    add("info/redactor_hechos.en", info.REDACTOR_HECHOS_EN)
    add("info/redactor_sin_preguntas.es", info.REDACTOR_SIN_PREGUNTAS_ES)
    add("info/redactor_sin_preguntas.en", info.REDACTOR_SIN_PREGUNTAS_EN)
    add("info/redactor_listas_por_codigo.es", info.REDACTOR_LISTAS_POR_CODIGO_ES)
    add("info/redactor_listas_por_codigo.en", info.REDACTOR_LISTAS_POR_CODIGO_EN)
    add("info/redactor_frases_por_codigo.es", info.REDACTOR_FRASES_POR_CODIGO_ES)
    add("info/redactor_frases_por_codigo.en", info.REDACTOR_FRASES_POR_CODIGO_EN)
    add("info/redactor_en_que_consiste.es", info.REDACTOR_EN_QUE_CONSISTE_ES)
    add("info/redactor_en_que_consiste.en", info.REDACTOR_EN_QUE_CONSISTE_EN)
    add("info/redactor_clima_pago.es", info.REDACTOR_CLIMA_PAGO_ES)  # arq-1i
    add("info/redactor_clima_pago.en", info.REDACTOR_CLIMA_PAGO_EN)
    add("info/redactor_que_faltaban.es", info.REDACTOR_QUE_FALTABAN_ES)  # arq-5f
    add("info/redactor_que_faltaban.en", info.REDACTOR_QUE_FALTABAN_EN)
    add("info/rag.con_hechos.es", info.RAG_CON_HECHOS_ES)
    add("info/rag.con_hechos.en", info.RAG_CON_HECHOS_EN)
    add("memory/seguridad.notas.es", memory.MEMORIA_SEGURA_NOTAS_ES)
    add("memory/seguridad.notas.en", memory.MEMORIA_SEGURA_NOTAS_EN)
    add("memory/seguridad.resumen.es", memory.MEMORIA_SEGURA_RESUMEN_ES)
    add("memory/seguridad.resumen.en", memory.MEMORIA_SEGURA_RESUMEN_EN)

    # ── info · reescritura de query (RAG) ────────────────────────────────────
    add("info/query_rewrite.system.es", info.QUERY_REWRITE_ES)
    add("info/query_rewrite.system.en", info.QUERY_REWRITE_EN)

    # ── info · grounding (verificación de respuesta) ─────────────────────────
    add("info/grounding_verify_v2.system.es", info.GROUNDING_VERIFY_V2_ES)
    add("info/grounding_verify_v2.system.en", info.GROUNDING_VERIFY_V2_EN)
    add("info/grounding_verify_v3.system.es", info.GROUNDING_VERIFY_V3_ES)
    add("info/grounding_verify_v3.system.en", info.GROUNDING_VERIFY_V3_EN)
    add("info/grounding_verify_v3_luna.system.es", info.GROUNDING_VERIFY_V3_LUNA_ES)
    add("info/grounding_verify_v3_luna.system.en", info.GROUNDING_VERIFY_V3_LUNA_EN)
    add("info/rag_condiciones.es", info.RAG_CONDICIONES_ES)
    add("info/rag_condiciones.en", info.RAG_CONDICIONES_EN)
    add("info/rag_no_supone.es", info.RAG_NO_SUPONE_ES)
    add("info/rag_no_supone.en", info.RAG_NO_SUPONE_EN)
    add("info/rag_no_adivina.es", info.RAG_NO_ADIVINA_ES)
    add("info/rag_no_adivina.en", info.RAG_NO_ADIVINA_EN)
    # lat-9 paso 1 (26-oct): las reglas de cualquier escritor y la parte de no adivinar que es solo del RAG.
    add("info/escritor_no_adivina.es", info.ESCRITOR_NO_ADIVINA_ES)
    add("info/escritor_no_adivina.en", info.ESCRITOR_NO_ADIVINA_EN)
    add("info/rag_pregunta_lo_que_falta.es", info.RAG_PREGUNTA_LO_QUE_FALTA_ES)
    add("info/rag_pregunta_lo_que_falta.en", info.RAG_PREGUNTA_LO_QUE_FALTA_EN)
    for lang in LANGS:
        add(f"info/reglas_del_escritor.{lang}", info.reglas_del_escritor(lang))
    add("info/rag_abre_con_la_respuesta.es", info.RAG_ABRE_CON_LA_RESPUESTA_ES)  # gen-2 (20-oct)
    add("info/rag_abre_con_la_respuesta.en", info.RAG_ABRE_CON_LA_RESPUESTA_EN)
    add("info/rag_sin_genero.es", info.RAG_SIN_GENERO_ES)  # gen-12 (21-oct)
    add("info/rag_sin_genero.en", info.RAG_SIN_GENERO_EN)
    add("info/rag_varios_planes.es", info.RAG_VARIOS_PLANES_ES)
    add("info/rag_varios_planes.en", info.RAG_VARIOS_PLANES_EN)
    # La viñeta de la disponibilidad, dentro de RAG_BODY_* (arq-2a; escrita en el cuerpo desde lat-9 paso 1).
    add("info/rag_disponibilidad_corta.es", info.RAG_DISPONIBILIDAD_CORTA_ES)
    add("info/rag_disponibilidad_corta.en", info.RAG_DISPONIBILIDAD_CORTA_EN)
    add("info/rag_regen_feedback.es", info.RAG_REGEN_FEEDBACK_ES)
    add("info/rag_regen_feedback.en", info.RAG_REGEN_FEEDBACK_EN)
    add_json("info/rag_regen_guard.es", info.RAG_REGEN_GUARD_ES)
    add_json("info/rag_regen_guard.en", info.RAG_REGEN_GUARD_EN)

    # ── info · persona Coral + seguridad + reglas (prompt de respuesta RAG) ──
    # Piezas por separado (lo que se mueve a src/prompts/info.py) y el prompt
    # ENSAMBLADO por `build_system_prompt` (lo que el LLM recibe de verdad —
    # incluye el bloque de tono leído de brand_tone.json). Sin `query` para que
    # sea determinista (el bloque few-shot depende de la query).
    add("info/rag.intro.es", info.RAG_INTRO_ES)
    add("info/rag.intro.en", info.RAG_INTRO_EN)
    add("info/presentacion.es", info.PRESENTACION_ES)
    add("info/presentacion.en", info.PRESENTACION_EN)
    add("info/juez_presentacion.es", info.JUEZ_PRESENTACION_ES)
    add("info/juez_presentacion.en", info.JUEZ_PRESENTACION_EN)
    add("info/rag.security.es", info.RAG_SECURITY_ES)
    add("info/rag.security.en", info.RAG_SECURITY_EN)
    add("info/rag.body.es", info.RAG_BODY_ES)
    add("info/rag.body.en", info.RAG_BODY_EN)
    for lang in LANGS:
        add(f"info/rag.system.assembled.{lang}", rag_agent.build_system_prompt(lang))
        # lat-9 paso 1: el del redactor de hechos, ensamblado (comparte las reglas del escritor con el del RAG).
        add(f"info/redactor.system.assembled.{lang}", redactor_hechos._mensajes(lang, [], "", "{}")[0]["content"])

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
