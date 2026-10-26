"""
Knowledge base loader.

Loads JSON files from data/knowledge_base/ (today, the brand tone for the RAG agent). The policies have ONE reader:
`src/domain/politicas.py` (sim-7, 26-oct).
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


def load_brand_tone() -> dict:
    return load_json("brand_tone.json")

