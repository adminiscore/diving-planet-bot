"""La memoria compartida del equipo (opción A de Coral #3686, decidida por Álvaro el 9-nov).

Vive en una rama fija, `memoria`, con `docs/plan/memoria.md` y `docs/plan/marcador.md`. El gancho de inicio la muestra en cada sesión y
tras cada compactación (`hook.py inicio`), siempre la última de origin, sea cual sea la rama en la que trabajes.

    python tools/coral/memoria.py ver [marcador]          # la trae de origin y la muestra
    python tools/coral/memoria.py publicar FICHERO [marcador] -m "qué cambias"

`publicar` sube el contenido de FICHERO (tu copia editada) a la rama `memoria` sin cambiar de rama ni tocar tu índice, y se niega si
alguien la cambió después de tu último `ver`: vuelve a verla y junta tus cambios. Solo biblioteca estándar y git.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAMA = "memoria"
RUTAS = {"memoria": "docs/plan/memoria.md", "marcador": "docs/plan/marcador.md"}
RAIZ = Path(__file__).resolve().parents[2]


def _git(*args: str, cwd: Path = RAIZ, entorno: dict | None = None, entrada: str | None = None, timeout: float = 15) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env={**os.environ, **(entorno or {})}, input=entrada)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def _leida(cwd: Path) -> Path:
    """Dónde se apunta el blob de la última memoria leída en este repo (dentro de .git: no se versiona)."""
    carpeta = Path(_git("rev-parse", "--git-common-dir", cwd=cwd).strip())
    return (carpeta if carpeta.is_absolute() else Path(cwd) / carpeta).resolve() / "coral-memoria-leida"


def traer(cwd: Path = RAIZ, timeout: float = 8) -> bool:
    try:
        _git("fetch", "-q", "origin", f"+refs/heads/{RAMA}:refs/remotes/origin/{RAMA}", cwd=cwd, timeout=timeout)
        return True
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return False  # sin red: vale la última que se trajo


def leer(que: str = "memoria", cwd: Path = RAIZ, traer_antes: bool = True) -> str | None:
    """El texto de origin/memoria (None si la rama no existe aún). Apunta lo leído para la guarda de `publicar`."""
    if traer_antes:
        traer(cwd)
    ruta = f"origin/{RAMA}:{RUTAS[que]}"
    try:
        texto, blob = _git("show", ruta, cwd=cwd), _git("rev-parse", ruta, cwd=cwd).strip()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    try:
        _leida(cwd).with_suffix(f".{que}").write_text(blob, encoding="utf-8")
    except (OSError, RuntimeError):
        pass
    return texto


def publicar(fichero: Path, que: str = "memoria", mensaje: str = "", cwd: Path = RAIZ) -> str:
    """Sube `fichero` como la nueva versión de la memoria (o del marcador). Devuelve el commit. Se niega si origin cambió desde el
    último `leer`, para no pisar el cambio de otro."""
    if not traer(cwd):
        raise RuntimeError("no se pudo traer la rama memoria de origin; prueba otra vez")
    ruta, padre = RUTAS[que], f"origin/{RAMA}"
    actual = _git("rev-parse", f"{padre}:{ruta}", cwd=cwd).strip()
    try:
        leido = _leida(cwd).with_suffix(f".{que}").read_text(encoding="utf-8").strip()
    except OSError:
        leido = ""
    if leido != actual:
        raise RuntimeError(f"alguien cambió {ruta} después de tu último «ver»: vuelve a verla, junta tus cambios y publica otra vez")
    blob = _git("hash-object", "-w", "--path", ruta, str(fichero), cwd=cwd).strip()
    if blob == actual:
        return _git("rev-parse", padre, cwd=cwd).strip()  # sin cambios
    with tempfile.TemporaryDirectory() as tmp:
        indice = {"GIT_INDEX_FILE": str(Path(tmp) / "indice")}
        _git("read-tree", padre, cwd=cwd, entorno=indice)
        _git("update-index", "--add", "--cacheinfo", f"100644,{blob},{ruta}", cwd=cwd, entorno=indice)
        arbol = _git("write-tree", cwd=cwd, entorno=indice).strip()
    commit = _git("commit-tree", arbol, "-p", padre, cwd=cwd, entrada=mensaje or f"memoria: {ruta}").strip()
    _git("push", "-q", "origin", f"{commit}:refs/heads/{RAMA}", cwd=cwd)
    _git("update-ref", f"refs/remotes/origin/{RAMA}", commit, cwd=cwd)
    _leida(cwd).with_suffix(f".{que}").write_text(blob, encoding="utf-8")
    return commit


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # en Windows, con la salida a un fichero, «−» o «→» rompían el cp1252
    if not argv or argv[0] not in ("ver", "publicar"):
        print(__doc__)
        return 2
    if argv[0] == "ver":
        que = argv[1] if len(argv) > 1 and argv[1] in RUTAS else "memoria"
        texto = leer(que)
        print(texto if texto is not None else f"(la rama {RAMA} aún no existe en origin)")
        return 0
    resto = argv[1:]
    mensaje = ""
    if "-m" in resto:
        i = resto.index("-m")
        mensaje = " ".join(resto[i + 1:])
        resto = resto[:i]
    if not resto:
        print("falta el fichero: python tools/coral/memoria.py publicar FICHERO [marcador] -m \"qué cambias\"")
        return 2
    que = resto[1] if len(resto) > 1 and resto[1] in RUTAS else "memoria"
    try:
        commit = publicar(Path(resto[0]).resolve(), que, mensaje)
    except RuntimeError as exc:
        print(f"No se publicó: {exc}")
        return 1
    print(f"Publicada {RUTAS[que]} en la rama {RAMA}: {commit[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
