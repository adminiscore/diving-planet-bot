"""Acceso por SSH al VPS de PRE, en un solo sitio (lo usan `turn_metrics` y `check_deploy`).

Clave `~/.ssh/dp_pre_vps` y `root@89.167.4.161` por defecto; se cambian con `PRE_SSH_KEY` y
`PRE_SSH_HOST`. Solo lectura: nadie despliega por aquí (el deploy lo hace CI al hacer push a `pre_*`).
"""

import os
import subprocess
from pathlib import Path

# 17-oct: una medida del banco ENTERO (71 casos = 71 conexiones seguidas) empezó a fallar a partir del caso 10 y los
# fallos NO se vieron: `_reproducir_en_pre` devolvía una lista vacía y el caso quedaba como "0/0", o sea igual que un
# caso que pasa. El servidor corta las conexiones seguidas (sshd las limita), así que aquí se reintenta con espera.
_REINTENTOS = 3
_ESPERAS = (5, 15, 30)
_FALLO_DE_CONEXION = ("connection refused", "connection reset", "connection closed", "broken pipe",
                      "timed out", "temporary failure", "too many authentication", "kex_exchange")


def _es_fallo_de_conexion(r: subprocess.CompletedProcess) -> bool:
    if r.returncode == 0:
        return False
    err = (r.stderr or "").lower()
    return any(t in err for t in _FALLO_DE_CONEXION) or r.returncode == 255


def pre_ssh(cmd: str, *, input_text: str | None = None, timeout: int = 60,
            stdin_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """Ejecuta `cmd` en el VPS de PRE y devuelve el resultado (stdout/stderr en texto). `stdin_bytes` manda
    datos binarios por la entrada (p. ej. un .tgz); si no, `input_text`.

    Reintenta hasta 3 veces (5, 15 y 30 s) si la CONEXIÓN falla: con muchas llamadas seguidas (una medida del banco
    entero son 71) el servidor empieza a rechazarlas, y antes eso se veía como un caso sin fallos."""
    import time

    key = os.environ.get("PRE_SSH_KEY") or str(Path.home() / ".ssh" / "dp_pre_vps")
    host = os.environ.get("PRE_SSH_HOST") or "root@89.167.4.161"
    args = ["ssh", "-i", key, "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", host, cmd]
    ultimo = None
    for intento in range(_REINTENTOS):
        if stdin_bytes is not None:
            r = subprocess.run(args, input=stdin_bytes, capture_output=True, timeout=timeout)
            ultimo = subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                                 r.stderr.decode("utf-8", "replace"))
        else:
            ultimo = subprocess.run(args, input=input_text, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=timeout)
        if not _es_fallo_de_conexion(ultimo) or intento == _REINTENTOS - 1:
            return ultimo
        espera = _ESPERAS[min(intento, len(_ESPERAS) - 1)]
        print(f"  [pre_ssh] la conexión falló ({(ultimo.stderr or '').strip()[:80]}): reintento en {espera} s")
        time.sleep(espera)
    return ultimo


def _carpeta_del_codigo() -> str:
    """Una carpeta DISTINTA por proceso dentro del contenedor.

    17-oct: dos medidas con `--codigo-local` a la vez (dos procesos míos, o Álvaro y yo) se pisaban, porque las dos
    subían a `/tmp/codigo-local` y la subida empieza por `rm -rf`: la segunda borró la copia que la primera estaba
    importando y el turno murió con `ModuleNotFoundError: src.agents.grounding_check`. Con el pid en el nombre, dos
    medidas en paralelo no se tocan. `PRE_CODIGO_DIR` lo fija a mano si hace falta repetir con la misma copia."""
    a_mano = os.environ.get("PRE_CODIGO_DIR")
    if a_mano:
        return a_mano
    quien = (os.environ.get("USER") or os.environ.get("USERNAME") or "local").lower()
    quien = "".join(c for c in quien if c.isalnum()) or "local"
    return f"/tmp/codigo-local-{quien}-{os.getpid()}"


CODIGO_LOCAL = "/tmp/codigo-local"  # compatibilidad: quien pase un destino a mano sigue funcionando


def subir_codigo_local(destino: str | None = None) -> str:
    """rag-2: copia el código LOCAL (src, scripts, data; lo versionado y lo nuevo sin versionar) a una carpeta
    temporal DENTRO de `dp-pre-bot`, para medir un cambio con la base, claves y modelos de PRE sin desplegar. El
    bot que está corriendo no lo ve (sigue en /app). Devuelve la carpeta, que es propia de este proceso."""
    import io
    import tarfile

    destino = destino or _carpeta_del_codigo()
    tgz = f"{destino}.tgz"
    raiz = Path(__file__).resolve().parent.parent
    ficheros = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src", "scripts", "data"],
        cwd=raiz, capture_output=True, text=True, check=True).stdout.split()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in ficheros:
            if (raiz / f).is_file():
                tar.add(raiz / f, arcname=f)
    r = pre_ssh(f"rm -rf {tgz} && cat > {tgz} && docker exec dp-pre-bot rm -rf {destino} "
                f"&& docker exec dp-pre-bot mkdir -p {destino} && docker cp {tgz} dp-pre-bot:{tgz} "
                f"&& docker exec dp-pre-bot tar xzf {tgz} -C {destino} && rm {tgz} && echo OK",
                timeout=120, stdin_bytes=buf.getvalue())
    if "OK" not in (r.stdout or ""):
        raise RuntimeError(f"no se pudo subir el código local: {r.stderr[-500:]}")
    return destino


def docker_python(entorno: dict[str, str] | None = None, codigo_local: str | None = None) -> str:
    """El `docker exec` para correr `python -` en `dp-pre-bot`, con variables de entorno y, si se pide, desde la
    copia del código local (PYTHONPATH y directorio de trabajo)."""
    env = dict(entorno or {})
    partes = ["docker exec -i"]
    if codigo_local:
        env["PYTHONPATH"] = codigo_local
        partes.append(f"-w {codigo_local}")
    partes += [f"-e {k}={v}" for k, v in env.items()]
    return " ".join(partes + ["dp-pre-bot python -"])
