"""Cliente de Coral para lo que corre en cada ordenador: el servidor MCP, los hooks y la escucha.

Solo biblioteca estándar (cada uno tiene su Python y no hay que instalar nada). La configuración sale de las
variables `CORAL_URL`, `CORAL_TOKEN` y `CORAL_PERSONA` o, si no están, del fichero `.env.coral` de la raíz del
repo (lo escribe `python tools/coral/configurar.py <tu nombre>`; está en .gitignore).
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from functools import cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FICHERO = RAIZ / ".env.coral"
URL_POR_DEFECTO = "https://pre.is-core.dev/coral"


class CoralError(RuntimeError):
    pass


def config() -> dict[str, str]:
    valores: dict[str, str] = {}
    try:
        for linea in FICHERO.read_text(encoding="utf-8").splitlines():
            clave, _, valor = linea.partition("=")
            if clave.strip() and not clave.lstrip().startswith("#"):
                valores[clave.strip()] = valor.strip().strip('"')
    except OSError:
        pass
    for clave in ("CORAL_URL", "CORAL_TOKEN", "CORAL_PERSONA"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    valores.setdefault("CORAL_URL", URL_POR_DEFECTO)
    return valores


def configurado() -> bool:
    return bool(config().get("CORAL_TOKEN"))


@cache
def contexto_ssl() -> ssl.SSLContext:
    """Con los certificados de certifi si está (viene con httpx, en requirements.txt). 17-oct: el Python de Windows,
    con el almacén del sistema, daba por CADUCADA la cadena nueva de Let's Encrypt de pre.is-core.dev (YE2 -> Root YE
    -> X2 -> X1) porque encontraba antes una firma cruzada vieja de X2 que caducó en 2025; curl sí funcionaba."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def llamar(metodo: str, ruta: str, datos: dict | None = None, timeout: float = 10):
    c = config()
    if not c.get("CORAL_TOKEN"):
        raise CoralError("Coral no está configurado: python tools/coral/configurar.py <tu nombre>")
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
    req = urllib.request.Request(c["CORAL_URL"].rstrip("/") + ruta, data=cuerpo, method=metodo, headers={
        "Authorization": f"Bearer {c['CORAL_TOKEN']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=contexto_ssl()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:
            detalle = e.reason
        raise CoralError(f"Coral respondió {e.code}: {detalle}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CoralError(f"no hay conexión con Coral ({c['CORAL_URL']}): {e}") from None


def hora(iso: str | None) -> str:
    if not iso:
        return "—"
    d = datetime.fromisoformat(iso).astimezone()
    return d.strftime("%H:%M") if d.date() == datetime.now().date() else d.strftime("%d-%m %H:%M")


def linea_mensaje(m: dict) -> str:
    autor = m["de"] + (" (Claude)" if m["origen"] == "claude" else "")
    tipo = "" if m["tipo"] == "aviso" else f" [{m['tipo']}]"
    responde = f" (responde a #{m['responde_a']})" if m.get("responde_a") else ""
    return f"#{m['id']} {hora(m['ts'])} {autor} → {m['para']}{tipo}{responde}: {m['texto']}"


def lineas_equipo(datos: dict) -> list[str]:
    salida = []
    for e in datos["equipo"]:
        if e["persona"] == datos["yo"]:
            continue
        partes = [f"visto {hora(e['visto'])}" if e["visto"] else "sin señales"]
        if e["tarea"]:
            partes.append(f"tarea: {e['tarea']}")
        if e["rama"]:
            partes.append(f"rama {e['rama']}")
        if e["ficheros"]:
            partes.append(f"{len(e['ficheros'])} ficheros con cambios")
        partes.append(f"PRE {e['pre']}" + (f" hasta {hora(e['pre_hasta'])}" if e["pre"] != "libre" else ""))
        if e["nota"]:
            partes.append(f"nota: {e['nota']}")
        salida.append(f"- {e['persona']}: " + " · ".join(partes))
    for s in datos["solapes"]:
        salida.append(f"! {s['persona']} también tiene cambios en: {', '.join(s['ficheros'])}")
    return salida
