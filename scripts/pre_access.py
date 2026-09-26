"""Acceso por SSH al VPS de PRE, en un solo sitio (lo usan `turn_metrics` y `check_deploy`).

Clave `~/.ssh/dp_pre_vps` y `root@89.167.4.161` por defecto; se cambian con `PRE_SSH_KEY` y
`PRE_SSH_HOST`. Solo lectura: nadie despliega por aquí (el deploy lo hace CI al hacer push a `pre_*`).
"""

import os
import subprocess
from pathlib import Path


def pre_ssh(cmd: str, *, input_text: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Ejecuta `cmd` en el VPS de PRE y devuelve el resultado (stdout/stderr en texto)."""
    key = os.environ.get("PRE_SSH_KEY") or str(Path.home() / ".ssh" / "dp_pre_vps")
    host = os.environ.get("PRE_SSH_HOST") or "root@89.167.4.161"
    return subprocess.run(
        ["ssh", "-i", key, "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", host, cmd],
        input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
