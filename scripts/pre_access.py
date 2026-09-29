"""Acceso por SSH al VPS de PRE, en un solo sitio (lo usan `turn_metrics` y `check_deploy`).

Clave `~/.ssh/dp_pre_vps` y `root@89.167.4.161` por defecto; se cambian con `PRE_SSH_KEY` y
`PRE_SSH_HOST`. Solo lectura: nadie despliega por aquí (el deploy lo hace CI al hacer push a `pre_*`).
"""

import os
import subprocess
from pathlib import Path


def pre_ssh(cmd: str, *, input_text: str | None = None, timeout: int = 60,
            stdin_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """Ejecuta `cmd` en el VPS de PRE y devuelve el resultado (stdout/stderr en texto). `stdin_bytes` manda
    datos binarios por la entrada (p. ej. un .tgz); si no, `input_text`."""
    key = os.environ.get("PRE_SSH_KEY") or str(Path.home() / ".ssh" / "dp_pre_vps")
    host = os.environ.get("PRE_SSH_HOST") or "root@89.167.4.161"
    args = ["ssh", "-i", key, "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", host, cmd]
    if stdin_bytes is not None:
        r = subprocess.run(args, input=stdin_bytes, capture_output=True, timeout=timeout)
        return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                           r.stderr.decode("utf-8", "replace"))
    return subprocess.run(
        args, input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


CODIGO_LOCAL = "/tmp/codigo-local"


def subir_codigo_local(destino: str = CODIGO_LOCAL) -> str:
    """rag-2: copia el código LOCAL (src, scripts, data; lo versionado y lo nuevo sin versionar) a una carpeta
    temporal DENTRO de `dp-pre-bot`, para medir un cambio con la base, claves y modelos de PRE sin desplegar. El
    bot que está corriendo no lo ve (sigue en /app). Devuelve la carpeta."""
    import io
    import tarfile

    raiz = Path(__file__).resolve().parent.parent
    ficheros = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src", "scripts", "data"],
        cwd=raiz, capture_output=True, text=True, check=True).stdout.split()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in ficheros:
            if (raiz / f).is_file():
                tar.add(raiz / f, arcname=f)
    r = pre_ssh(f"rm -rf /tmp/codigo-local.tgz && cat > /tmp/codigo-local.tgz && docker exec dp-pre-bot rm -rf {destino} "
                f"&& docker exec dp-pre-bot mkdir -p {destino} && docker cp /tmp/codigo-local.tgz dp-pre-bot:/tmp/c.tgz "
                f"&& docker exec dp-pre-bot tar xzf /tmp/c.tgz -C {destino} && rm /tmp/codigo-local.tgz && echo OK",
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
