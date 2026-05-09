import json
import re
from pathlib import Path


CONVERSATIONS_PATH = Path(__file__).parent.parent / "data" / "knowledge_base" / "conversations.json"

CHUNKED_ID_RE = re.compile(r"^whatsapp_import_.*_part\d+$")
LEGACY_IMPORT_ID_RE = re.compile(r"^whatsapp_import_")


def main() -> int:
    if not CONVERSATIONS_PATH.exists():
        raise SystemExit(f"File not found: {CONVERSATIONS_PATH}")

    data = json.loads(CONVERSATIONS_PATH.read_text(encoding="utf-8"))
    examples = list(data.get("conversation_examples", []))

    kept: list[dict] = []
    removed_legacy = 0
    removed_invalid = 0

    for ex in examples:
        if not isinstance(ex, dict):
            removed_invalid += 1
            continue

        ex_id = str(ex.get("id") or "")

        # Keep all non-import curated examples.
        if not LEGACY_IMPORT_ID_RE.match(ex_id):
            kept.append(ex)
            continue

        # Keep only chunked WhatsApp imports.
        if CHUNKED_ID_RE.match(ex_id):
            kept.append(ex)
            continue

        removed_legacy += 1

    data["conversation_examples"] = kept

    backup_path = CONVERSATIONS_PATH.with_suffix(".json.pre_dedup.bak")
    backup_path.write_text(CONVERSATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    CONVERSATIONS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Removed legacy whatsapp_import_* (non-chunked): {removed_legacy}")
    print(f"Removed invalid entries: {removed_invalid}")
    print(f"Kept total examples: {len(kept)}")
    print(f"Backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
