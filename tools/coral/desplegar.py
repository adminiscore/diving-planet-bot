"""Instala o actualiza Coral en el VPS de PRE: `python tools/coral/desplegar.py`.

1. Copia `tools/coral/hub/` a /opt/coral-hub (FUERA del checkout del bot: los deploys de pre_* no lo tocan).
2. Crea los tokens que falten en /opt/coral-hub/.env (uno por persona; nunca se imprimen).
3. Levanta el contenedor `coral-hub` en la red de Caddy.
4. Recarga Caddy (sin cortar nada) con el Caddyfile de este repo, que añade la ruta /coral a pre.is-core.dev.
   Solo si el Caddyfile del VPS es el mismo que el de aquí quitando el bloque de Coral; si no, se para y avisa.

No reinicia el bot ni despliega PRE. La ruta de Caddy se carga en caliente desde una copia; cuando una rama con el
bloque de Coral se despliegue, queda también en el fichero del VPS y sobrevive a un reinicio de Caddy.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cliente  # noqa: E402

from scripts.pre_access import pre_ssh  # noqa: E402

PERSONAS = ("gadea", "alvaro", "gonzalo")
HUB = Path(__file__).resolve().with_name("hub")
DESTINO = "/opt/coral-hub"
CADDYFILE_VPS = "/opt/diving-planet-bot/Caddyfile"
BLOQUE_CORAL = re.compile(r"[ \t]*# >>> coral.*?# <<< coral[^\n]*\n", re.S)


def _ssh(cmd: str, timeout: int = 120, **kw) -> str:
    r = pre_ssh(cmd, timeout=timeout, **kw)
    if r.returncode != 0:
        raise SystemExit(f"Falló en el VPS: {cmd[:80]}\n{(r.stderr or r.stdout)[-800:]}")
    return r.stdout


def _sin_coral(texto: str) -> str:
    return BLOQUE_CORAL.sub("", texto.replace("\r\n", "\n")).strip()


def comprobar_caddyfile() -> str:
    """El Caddyfile de aquí, si es el del VPS más el bloque de Coral (si no, para antes de tocar nada)."""
    local = (RAIZ / "Caddyfile").read_text(encoding="utf-8").replace("\r\n", "\n")
    if "# >>> coral" not in local:
        raise SystemExit("El Caddyfile de este repo no tiene el bloque de Coral.")
    if _sin_coral(_ssh(f"cat {CADDYFILE_VPS}")) != _sin_coral(local):
        raise SystemExit("El Caddyfile del VPS no coincide con el de este repo (quitando el bloque de Coral): no "
                         "toco nada para no cambiar otras rutas. Integra la rama que sirve PRE y repite.")
    return local


def subir_hub() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nombre in ("app.py", "pagina.html", "Dockerfile", "docker-compose.yml"):
            datos = (HUB / nombre).read_bytes().replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            tar.addfile(info, io.BytesIO(datos))
    _ssh(f"mkdir -p {DESTINO} && tar xzf - -C {DESTINO}", stdin_bytes=buf.getvalue())
    print(f"1. Copiado a {DESTINO}")


def preparar_env() -> None:
    redes = json.loads(_ssh("docker inspect dp-caddy --format '{{json .NetworkSettings.Networks}}'"))
    red = next((n for n in redes if n.endswith("dp-net")), next(iter(redes)))
    tokens: dict[str, str] = {}
    for linea in _ssh(f"cat {DESTINO}/.env 2>/dev/null || true").splitlines():
        if linea.startswith("CORAL_TOKENS="):
            tokens = dict(p.split(":", 1) for p in linea.split("=", 1)[1].split(",") if ":" in p)
    nuevos = [p for p in PERSONAS if p not in tokens]
    for p in nuevos:
        tokens[p] = secrets.token_hex(24)
    texto = f"CORAL_TOKENS={','.join(f'{p}:{t}' for p, t in tokens.items())}\nCORAL_RED={red}\n"
    _ssh(f"umask 077 && cat > {DESTINO}/.env", input_text=texto)
    print(f"2. Tokens: {len(tokens)} ({'nuevos: ' + ', '.join(nuevos) if nuevos else 'sin cambios'}); red {red}")


def levantar() -> None:
    salida = _ssh(f"cd {DESTINO} && docker compose -p coral up -d --build 2>&1 | tail -3", timeout=900)
    print("3. Contenedor coral-hub levantado\n   " + salida.strip().replace("\n", "\n   "))


def recargar_caddy(caddyfile: str) -> None:
    _ssh("docker exec -i dp-caddy sh -c 'cat > /tmp/Caddyfile.coral'", input_text=caddyfile)
    _ssh("docker exec dp-caddy caddy validate --config /tmp/Caddyfile.coral --adapter caddyfile")
    _ssh("docker exec dp-caddy caddy reload --config /tmp/Caddyfile.coral --adapter caddyfile")
    print("4. Caddy recargado con la ruta /coral")


def comprobar() -> None:
    for url, que in ((cliente.URL_POR_DEFECTO + "/salud", "Coral"), ("https://pre.is-core.dev/health", "el bot"),
                     ("https://chatwoot.is-core.dev/", "Chatwoot")):
        error = None
        for _ in range(20):
            try:
                with urllib.request.urlopen(url, timeout=10, context=cliente.contexto_ssl()) as r:
                    if r.status == 200:
                        print(f"5. Responde {que}: {url}")
                        break
            except OSError as e:
                error = e
            time.sleep(3)
        else:
            raise SystemExit(f"{que} no responde en {url} ({error}): mira `docker logs coral-hub` y "
                             "`docker logs dp-caddy`.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    caddyfile = comprobar_caddyfile()
    subir_hub()
    preparar_env()
    levantar()
    recargar_caddy(caddyfile)
    comprobar()


if __name__ == "__main__":
    main()
