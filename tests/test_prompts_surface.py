"""Fase 3.2 — invariantes del paquete `src/prompts/`.

No prueban el TEXTO de ningún prompt (eso lo hacen los tests de cada red, p. ej.
`test_rag_safety` con los guardarraíles de seguridad): prueban las propiedades
ESTRUCTURALES que hacen que la superficie de prompt siga siendo revisable y que
la red de seguridad del refactor no se quede ciega.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.agents import (
    conversation_summarizer,
    escalation,
    grounding_check,
    language_detector,
    llm_extractor,
    notes_extractor,
    query_rewriter,
    rag_agent,
)
from src.prompts import booking, info, memory, router

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src" / "prompts"


def _prompt_modules() -> list[Path]:
    return sorted(p for p in PROMPTS_DIR.glob("*.py") if p.name != "__init__.py")


def test_prompt_modules_are_a_leaf_no_src_imports():
    """`src/prompts/*` no importa NADA de `src/` (regla #1 del paquete).

    Es lo que permite (a) leer/diffear un prompt sin arrastrar el runtime y (b)
    que cualquier módulo de `src/agents/` pueda importar su prompt sin riesgo de
    import circular — el problema que obligó a los imports perezosos de
    `supervisor` en los nodos-agente.
    """
    offenders = []
    for path in [*_prompt_modules(), PROMPTS_DIR / "__init__.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}: import {a.name}" for a in node.names if a.name.startswith("src")
                ]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src"):
                offenders.append(f"{path.name}: from {node.module} import ...")
    assert not offenders, f"src/prompts debe ser una hoja del grafo de imports: {offenders}"


@pytest.mark.parametrize(
    ("net_module", "attr", "prompt_module"),
    [
        # router
        (escalation, "ROUTING_TOOL", router),
        (escalation, "routing_system_prompt", router),
        # booking (subgrafo)
        (language_detector, "LANGUAGE_DETECT_PROMPT", booking),
        (llm_extractor, "EXTRACTION_TOOL", booking),
        (llm_extractor, "extraction_system_prompt", booking),
        (llm_extractor, "SIGNALS_TOOL", booking),
        (llm_extractor, "signals_system_prompt", booking),
        (llm_extractor, "SLOT_RESOLVER_SPEC", booking),
        (llm_extractor, "slot_resolver_prompt", booking),
        (llm_extractor, "slot_resolver_tool", booking),
        (llm_extractor, "acknowledgement_system_prompt", booking),
        # info
        (query_rewriter, "QUERY_REWRITE_ES", info),
        (query_rewriter, "QUERY_REWRITE_EN", info),
        (grounding_check, "GROUNDING_VERIFY_ES", info),
        (grounding_check, "GROUNDING_VERIFY_EN", info),
        (rag_agent, "RAG_INTRO_ES", info),
        (rag_agent, "RAG_SECURITY_ES", info),
        (rag_agent, "RAG_BODY_ES", info),
        (rag_agent, "RAG_INTRO_EN", info),
        (rag_agent, "RAG_SECURITY_EN", info),
        (rag_agent, "RAG_BODY_EN", info),
        # memoria
        (notes_extractor, "NOTES_TOOL", memory),
        (notes_extractor, "notes_system_prompt", memory),
        (conversation_summarizer, "SUMMARY_SYSTEM_ES", memory),
        (conversation_summarizer, "SUMMARY_SYSTEM_EN", memory),
    ],
)
def test_each_net_uses_the_prompt_from_its_node_module(net_module, attr, prompt_module):
    """Cada red LLM usa EL MISMO objeto que define su módulo de prompts.

    Si alguien vuelve a meter una copia del prompt dentro del módulo de la red
    (el patrón que la Fase 3.2 deshizo), estas identidades dejan de coincidir y
    el test falla — en vez de que las dos versiones se desincronicen en silencio.
    """
    assert getattr(net_module, attr) is getattr(prompt_module, attr)


def test_prompt_snapshot_covers_every_prompt_defined():
    """El snapshot de equivalencia (`scripts/snapshot_prompts.py`) renderiza
    TODOS los símbolos públicos de `src/prompts/`.

    Es lo que mantiene honesta la red de seguridad del refactor: un prompt que el
    snapshot no renderice se podría cambiar en un movimiento futuro sin que nada
    lo detectara. La cobertura se DERIVA de lo que `_collect()` toca de verdad
    (`TOUCHED`), no de una lista paralela — si añades un prompt, este test te
    obliga a añadirlo también al snapshot.
    """
    from scripts import snapshot_prompts

    snapshot_prompts.TOUCHED.clear()
    snapshot_prompts._collect()

    missing = []
    for module in (router, booking, info, memory):
        for name in dir(module):
            if name.startswith("_") or name == "annotations":
                continue
            if f"{module.__name__}.{name}" not in snapshot_prompts.TOUCHED:
                missing.append(f"{module.__name__}.{name}")
    assert not missing, (
        "prompts que el snapshot no renderiza (añádelos a scripts/snapshot_prompts.py): "
        f"{missing}"
    )
