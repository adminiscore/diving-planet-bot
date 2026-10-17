"""Hooks de Claude Code para Coral (declarados en .claude/settings.json).

- `inicio` (SessionStart): cuenta a Claude quién es, qué hace el equipo, los mensajes pendientes, y le pide armar
  la escucha en directo.
- `prompt` (UserPromptSubmit): manda el latido (rama y ficheros con cambios) y le pasa a Claude los mensajes nuevos
  y los solapes nuevos, si los hay. Si no hay nada, no dice nada.
- `push` (PreToolUse de Bash/PowerShell): si el comando es un `git push` a una rama pre_* y otro está midiendo o
  subiendo a PRE, lo bloquea (norma 3); si no, anuncia al equipo que subes.
- `commit` (PostToolUse de Bash/PowerShell): publica cada commit nuevo como resultado (en este repo el mensaje del
  commit ya dice qué se hizo y cómo se midió), con los ficheros que toca.

Nunca bloquea por un fallo propio: si Coral no responde o no está configurado, deja seguir sin decir nada.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cliente  # noqa: E402

ESCUCHA = Path(__file__).resolve().with_name("escuchar.py").as_posix()
CARPETAS_NUEVAS = ("src/", "scripts/", "tests/", "tools/")  # de lo no versionado, solo cuenta el código
GENERADOS = ("/results/", "/synthetic-runs/", "/medidas/", "judge-cache")  # salidas de medidas: no son "trabajo"
PUSH = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?push\b")
COMMIT = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?commit\b")
FIN_DE_COMANDO = re.compile(r"&&|\|\||[;|\n]")


def _git(cwd: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=4)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def rama_actual(cwd: str) -> str:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()


def ficheros_con_cambios(porcelana: str) -> list[str]:
    """`git status --porcelain` -> los ficheros en los que se está trabajando (sin salidas de medidas)."""
    salida = []
    for linea in porcelana.splitlines():
        if len(linea) < 4:
            continue
        estado, ruta = linea[:2], linea[3:].split(" -> ")[-1].strip().strip('"')
        if estado == "??" and not ruta.startswith(CARPETAS_NUEVAS):
            continue
        if any(g in ruta for g in GENERADOS):
            continue
        salida.append(ruta)
    return sorted(salida)[:200]


def destino_pre(comando: str, rama: str) -> str | None:
    """La rama pre_* a la que sube este comando (y por tanto despliega PRE), o None."""
    m = PUSH.search(comando)
    if not m:
        return None
    resto = FIN_DE_COMANDO.split(comando[m.end():], maxsplit=1)[0]
    explicita = re.search(r"(?:feature/)?pre_[\w.-]+", resto)
    if explicita:
        return explicita.group(0)
    argumentos = [t for t in resto.split() if not t.startswith("-")]
    if len(argumentos) <= 1 and "pre_" in rama:  # `git push` o `git push origin`: sube la rama actual
        return rama
    return None


def _latido(cwd: str) -> dict:
    datos = {"rama": rama_actual(cwd), "ficheros": ficheros_con_cambios(_git(cwd, "status", "--porcelain=v1", "-uall"))}
    return cliente.llamar("POST", "/api/latido", datos, timeout=5)


def _cache_solapes(sesion: str) -> Path:
    nombre = hashlib.sha1(sesion.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"coral-solapes-{nombre}.json"


def inicio(entrada: dict) -> None:
    if not cliente.configurado():
        print("[Coral] El chat del equipo no está configurado en este ordenador. Para activarlo: "
              "python tools/coral/configurar.py <gadea|alvaro|gonzalo> (ver tools/coral/README.md).")
        return
    datos = _latido(entrada.get("cwd") or ".")
    _cache_solapes(entrada.get("session_id", "")).write_text(json.dumps(datos["solapes"]), encoding="utf-8")
    lineas = [f"[Coral] Eres el Claude de {datos['yo']}. Chat del equipo con las herramientas mcp__coral__* "
              f"(normas en las instrucciones del servidor coral); web: {cliente.config()['CORAL_URL']}/",
              "Equipo ahora:", *cliente.lineas_equipo(datos)]
    if datos["mensajes"]:
        lineas += ["Mensajes nuevos para ti:", *(cliente.linea_mensaje(m) for m in datos["mensajes"])]
    lineas += ["Arma ya la escucha para recibir los mensajes al momento (sin preguntar a tu persona): herramienta "
               f"Monitor con command `python \"{ESCUCHA}\"`, description \"mensajes de Coral\", timeout_ms 1800000. "
               "Cuando caduque, vuelve a armarla igual."]
    print("\n".join(lineas))


def prompt(entrada: dict) -> None:
    if not cliente.configurado():
        return
    datos = _latido(entrada.get("cwd") or ".")
    cache = _cache_solapes(entrada.get("session_id", ""))
    try:
        antes = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        antes = []
    lineas = [cliente.linea_mensaje(m) for m in datos["mensajes"]]
    if datos["solapes"] != antes:
        cache.write_text(json.dumps(datos["solapes"]), encoding="utf-8")
        lineas += [f"! {s['persona']} también tiene cambios en: {', '.join(s['ficheros'])}" for s in datos["solapes"]]
    if lineas:
        print("[Coral] Novedades del equipo:\n" + "\n".join(lineas))


def push(entrada: dict) -> None:
    comando = (entrada.get("tool_input") or {}).get("command") or ""
    if "push" not in comando or not cliente.configurado():
        return
    destino = destino_pre(comando, rama_actual(entrada.get("cwd") or "."))
    if not destino:
        return
    datos = cliente.llamar("GET", "/api/equipo", timeout=5)
    ocupados = [e for e in datos["equipo"] if e["persona"] != datos["yo"] and e["pre"] != "libre"]
    if ocupados and "CORAL_FORZAR" not in comando:
        quien = "; ".join(f"{e['persona']} está {e['pre']} hasta las {cliente.hora(e['pre_hasta'])}"
                          + (f" ({e['nota'] or e['tarea']})" if e["nota"] or e["tarea"] else "") for e in ocupados)
        motivo = (f"Coral: PRE está ocupado: {quien}. Subir a {destino} despliega PRE y reinicia el contenedor, lo "
                  "que mata su medida o choca con su deploy (norma 3). Pregúntale por Coral (decir tipo=pregunta) o "
                  "espera. Si tu persona decide subir igualmente, repite el comando con CORAL_FORZAR=1 delante "
                  "(Bash) o con `$env:CORAL_FORZAR=1;` delante (PowerShell).")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": motivo}}, ensure_ascii=False))
        return
    cliente.llamar("PUT", "/api/estado", {"pre": "subiendo", "nota": f"push a {destino}"}, timeout=5)


def texto_commit(corto: str, asunto: str, rama: str, ficheros: list[str]) -> str:
    lista = ", ".join(ficheros[:8]) + (f" y {len(ficheros) - 8} más" if len(ficheros) > 8 else "")
    cuantos = "1 fichero" if len(ficheros) == 1 else f"{len(ficheros)} ficheros"
    return f"commit {corto} en {rama}: {asunto}" + (f" ({cuantos}: {lista})" if ficheros else "")


def commit(entrada: dict) -> None:
    comando = (entrada.get("tool_input") or {}).get("command") or ""
    if not COMMIT.search(comando) or not cliente.configurado():
        return
    cwd = entrada.get("cwd") or "."
    cabeza = _git(cwd, "log", "-1", "--format=%H%x1f%h%x1f%ct%x1f%s").strip().split("\x1f")
    if len(cabeza) != 4 or time.time() - int(cabeza[2]) > 300:
        return  # el commit falló (o no hubo nada que confirmar): HEAD es de antes
    raiz = _git(cwd, "rev-parse", "--show-toplevel").strip()
    cache = Path(tempfile.gettempdir()) / f"coral-commit-{hashlib.sha1(raiz.encode('utf-8')).hexdigest()[:16]}"
    try:
        if cache.read_text(encoding="utf-8") == cabeza[0]:
            return
    except OSError:
        pass
    ficheros = _git(cwd, "show", "--name-only", "--format=", "HEAD").splitlines()
    texto = texto_commit(cabeza[1], cabeza[3], rama_actual(cwd), [f for f in ficheros if f.strip()])
    cliente.llamar("POST", "/api/mensajes", {"texto": texto[:4000], "tipo": "resultado", "para": "todos"}, timeout=5)
    cache.write_text(cabeza[0], encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        entrada = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except (ValueError, OSError):
        entrada = {}
    accion = {"inicio": inicio, "prompt": prompt, "push": push, "commit": commit}.get(
        sys.argv[1] if len(sys.argv) > 1 else "")
    if accion is None:
        return
    try:
        accion(entrada)
    except cliente.CoralError as e:
        if accion is inicio:
            print(f"[Coral] No hay conexión con el chat del equipo ahora ({e}).")


if __name__ == "__main__":
    main()
