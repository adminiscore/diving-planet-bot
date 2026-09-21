"""Junta una exportacion de la base de datos de Plan Coral en data/plan-coral.json.

Claude exporta cada coleccion de la pagina (herramienta ArtifactData, `list` con `out_dir`)
como un JSON por documento: `<export_dir>/<coleccion>/<id>.json`. Este script los junta en
la copia versionada que usa `embed_backup.py`:

    python docs/tracking/consolidate_export.py <export_dir>
    python docs/tracking/embed_backup.py

AVISO DE PERDIDA DE DATOS (2026-09-21): la BD de la pagina solo la puede escribir su cuenta
propietaria; el resto del equipo edita `data/plan-coral.json` por git. Si se exporta la BD viva
y se consolida sin mas, esos cambios hechos SOLO en el repo desaparecen. Por eso este script
compara con la copia actual y AVISA de los documentos que se perderian; para tirarlos hay que
decirlo a proposito con `--drop-missing`. Ver README ("Quien puede actualizar la pagina").
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

COLLECTIONS = ("phases", "tasks", "snapshots", "layers", "log")
OUT = Path(__file__).parent / "data" / "plan-coral.json"


def missing_from_export(previous: dict, fresh: dict) -> dict[str, list[str]]:
    """Ids que estaban en la copia del repo y NO vienen en la exportacion (candidatos a
    perderse: normalmente cambios hechos por git que nadie replico en la pagina)."""
    gone: dict[str, list[str]] = {}
    for name in COLLECTIONS:
        before = {d["id"] for d in previous.get("collections", {}).get(name, [])}
        after = {d["id"] for d in fresh["collections"][name]}
        if lost := sorted(before - after):
            gone[name] = lost
    return gone


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
    args = [a for a in sys.argv[1:] if a != "--drop-missing"]
    drop_missing = "--drop-missing" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    result = consolidate(Path(args[0]))

    # Guardarrail: no tirar en silencio lo que solo existe en el repo (ver AVISO arriba).
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    gone = missing_from_export(previous, result)
    if gone and not drop_missing:
        detalle = "; ".join(f"{col}: {', '.join(ids)}" for col, ids in gone.items())
        raise SystemExit(
            f"ABORTADO: la exportacion no trae documentos que SI estan en la copia del repo ({detalle}). "
            "Suelen ser cambios hechos por git que nadie replico en la pagina: replicalos en la "
            "pagina y vuelve a exportar, o repite con --drop-missing si de verdad quieres borrarlos."
        )
    if gone:
        print("AVISO: se descartan documentos que solo estaban en el repo:", gone)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in result["collections"].items()}, "->", OUT)
