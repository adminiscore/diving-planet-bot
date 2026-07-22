"""
Knowledge base loader.

Loads service catalog, FAQs, and policies from JSON files
in data/knowledge_base/ for use by the decision tree and RAG agent.
"""

import json
from pathlib import Path

import structlog

logger = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "knowledge_base"


def load_json(filename: str) -> dict:
    """Load a JSON file from the knowledge base directory."""
    filepath = DATA_DIR / filename
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
            logger.info("knowledge_loaded", file=filename, items=len(data))
            return data
    except FileNotFoundError:
        logger.warning("knowledge_file_not_found", file=filename)
        return {}
    except json.JSONDecodeError as e:
        logger.error("knowledge_parse_error", file=filename, error=str(e))
        return {}


def load_services() -> dict:
    return load_json("services.json")


def load_faqs() -> dict:
    return load_json("faqs.json")


def load_policies() -> dict:
    return load_json("policies.json")


def load_brand_tone() -> dict:
    return load_json("brand_tone.json")


def load_conversations() -> dict:
    return load_json("conversations.json")
