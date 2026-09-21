"""Junta una exportacion de la base de datos de Plan Coral en data/plan-coral.json.

Claude exporta cada coleccion de la pagina (herramienta ArtifactData, `list` con `out_dir`)
como un JSON por documento: `<export_dir>/<coleccion>/<id>.json`. Este script los junta en
la copia versionada que usa `embed_backup.py`:

    python docs/tracking/consolidate_export.py <export_dir>
    python docs/tracking/embed_backup.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

COLLECTIONS = ("phases", "tasks", "snapshots", "layers", "log")
OUT = Path(__file__).parent / "data" / "plan-coral.json"


def consolidate(export_dir: Path) -> dict:
    data = {
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "https://claude.ai/artifact/XiGd3kguTNwwqTnH7mQwgi",
        "about": (
            "Copia de la base de datos de la página Plan Coral (fases, tareas, fotos, capas, bitácora). "
            "La página la usa como respaldo de solo lectura si no puede conectar con su base de datos; "
            "en el repo sirve de historial versionado."
        ),
        "collections": {},
    }
    for name in COLLECTIONS:
        files = sorted((export_dir / name).glob("*.json"))
        if not files:
            raise SystemExit(f"falta la coleccion {name!r} en {export_dir}: exportala antes de consolidar")
        data["collections"][name] = [{"id": f.stem, **json.loads(f.read_text(encoding="utf-8"))} for f in files]
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    result = consolidate(Path(sys.argv[1]))
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in result["collections"].items()}, "->", OUT)
