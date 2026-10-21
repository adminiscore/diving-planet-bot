"""r6-1(c): ¿le queda saldo a la cuenta de OpenAI de PRE? Una llamada mínima (1 token) con la clave del bot.

Se lanza cada hora desde GitHub Actions (`.github/workflows/vigilar-saldo-openai.yml`) DENTRO del contenedor de PRE:

    docker exec dp-pre-bot python -m scripts.vigilar_saldo_openai [--coral]

Sale con 0 si OpenAI contesta, y con 2 si la cuenta no puede contestar (sin saldo, clave inválida, caído tras
reintentos): el job de GitHub falla y GitHub manda un correo. Con `--coral` y la identidad `vigilante` del chat del
equipo (CORAL_URL + CORAL_TOKEN_VIGILANTE), además escribe un aviso en Coral. Un 429 de "demasiadas peticiones"
suelto no es falta de saldo: se reintenta. Nunca imprime la clave ni el token.

Por qué (17-oct): esta semana PRE se quedó mudo dos veces porque se acabó el crédito, y nadie se enteró hasta que
alguien probó el bot. Coste: ~1 token por hora.

mej-5 (21-oct): también vigila OpenRouter (saldo de la cuenta y límite de la clave, sin gastar nada; ver
`comprobar_openrouter`). Sale con 2 si cualquiera de los dos da alarma.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

MODELO = "gpt-5.4-nano"  # mod (18-oct): fuera de gpt-4; antes "gpt-4o-mini"
REINTENTOS = 3


def clasificar(exc: Exception) -> tuple[str, bool]:
    """(motivo, es_alarma) de un error de OpenAI. La falta de saldo, la clave y una caída son alarma; un 429 de
    ritmo (rate limit) no lo es: se reintenta."""
    codigo = getattr(exc, "status_code", None)
    cuerpo = str(getattr(exc, "body", "") or exc)
    if codigo == 429 and "insufficient_quota" in cuerpo:
        return "sin saldo (429 insufficient_quota)", True
    if codigo == 429:
        return "demasiadas peticiones (429 rate limit)", False
    if codigo in (401, 403):
        return f"clave inválida o sin permiso ({codigo})", True
    return f"OpenAI no responde ({codigo or type(exc).__name__})", True


def comprobar(cliente=None, pausa: float = 5.0) -> tuple[bool, str]:
    """(ok, motivo). `cliente`: un cliente OpenAI (para los tests); por defecto, el de la clave del bot."""
    if cliente is None:
        from openai import OpenAI

        from src.config import settings

        cliente = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=30)
    motivo = ""
    for intento in range(REINTENTOS):
        try:
            # mej-5 (21-oct, Gonzalo): los gpt-5 rechazan `max_tokens` (400 "Unsupported parameter") y la alarma saltaba
            # siempre, con o sin saldo; hoy, sin crédito a las 12:45, no se distinguía. 16, porque razona.
            cliente.chat.completions.create(model=MODELO, max_completion_tokens=16,
                                            messages=[{"role": "user", "content": "ok"}])
            return True, "OpenAI contesta"
        except Exception as exc:  # noqa: BLE001
            motivo, alarma = clasificar(exc)
            if alarma and "insufficient_quota" in motivo:
                return False, motivo  # sin saldo no se arregla reintentando
            if intento < REINTENTOS - 1:
                time.sleep(pausa)
    return False, motivo


# mej-5 (21-oct): el 21-oct OpenAI se vació tres veces en una tarde y la causa fue OPENROUTER: su clave llegó a su
# límite (403 "Key limit exceeded"), todo lo de OpenRouter (Jev, el extractor, el revisor) fallaba y el bot lo repetía
# en OpenAI (~17 llamadas por turno). OpenRouter dice cuánto queda SIN gastar nada: el saldo de la cuenta
# (GET /credits) y el límite de la clave (GET /key). Se avisa antes de llegar a cero.
UMBRAL_OPENROUTER_USD = 5.0


def _leer_openrouter(ruta: str, clave: str, base: str, abrir) -> dict:
    peticion = urllib.request.Request(f"{base.rstrip('/')}{ruta}", headers={"Authorization": f"Bearer {clave}"})
    with abrir(peticion, timeout=15) as r:
        return json.loads(r.read() or b"{}").get("data") or {}


def comprobar_openrouter(abrir=None, clave: str | None = None, base: str | None = None,
                         umbral: float = UMBRAL_OPENROUTER_USD) -> tuple[bool, str]:
    """(ok, motivo) de la cuenta y la clave de OpenRouter, sin gastar: alarma si a la cuenta o al límite de la clave
    les quedan menos de `umbral` dólares, o si OpenRouter rechaza la clave. Sin clave configurada, no se vigila."""
    if clave is None or base is None:
        from src.config import settings

        clave = settings.openrouter_api_key if clave is None else clave
        base = settings.openrouter_base_url if base is None else base
    if not clave:
        return True, "sin clave de OpenRouter: no se vigila"
    abrir = abrir or urllib.request.urlopen
    try:
        cuenta = _leer_openrouter("/credits", clave, base, abrir)
        llave = _leer_openrouter("/key", clave, base, abrir)
    except Exception as exc:  # noqa: BLE001
        codigo = getattr(exc, "code", None)
        if codigo in (401, 402, 403):
            return False, f"OpenRouter rechaza la clave o no tiene saldo ({codigo})"
        return False, f"OpenRouter no responde ({codigo or type(exc).__name__})"
    quedan = []
    if isinstance(cuenta.get("total_credits"), (int, float)) and isinstance(cuenta.get("total_usage"), (int, float)):
        resto = cuenta["total_credits"] - cuenta["total_usage"]
        quedan.append(("a la cuenta", resto))
    if isinstance(llave.get("limit_remaining"), (int, float)):
        quedan.append(("al límite de la clave", llave["limit_remaining"]))
    poco = [(donde, resto) for donde, resto in quedan if resto < umbral]
    if poco:
        return False, "; ".join(f"OpenRouter: le quedan {resto:.2f} $ {donde}" for donde, resto in poco)
    detalle = ", ".join(f"{resto:.2f} $ {donde}" for donde, resto in quedan) or "sin datos de saldo"
    return True, f"OpenRouter contesta ({detalle})"


def avisar_en_coral(motivo: str) -> str:
    url = os.environ.get("CORAL_URL", "").rstrip("/")
    token = os.environ.get("CORAL_TOKEN_VIGILANTE", "")
    if not url or not token:
        return "sin identidad 'vigilante' en Coral: solo el correo de GitHub"
    texto = (f"⚠️ ALERTA de saldo de PRE: {motivo}. Si OpenAI no contesta, el bot dice a los clientes que hay un "
             "problema técnico y los pasa a un asesor (si AVISO_SI_OPENAI_FALLA está encendido); si se acaba "
             "OpenRouter, el bot lo repite todo en OpenAI y lo vacía. Revisad el saldo y las claves.")
    peticion = urllib.request.Request(
        f"{url}/api/mensajes", method="POST",
        data=json.dumps({"texto": texto, "tipo": "aviso", "para": "todos"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(peticion, timeout=15) as r:
            return f"aviso en Coral ({r.status})"
    except Exception as exc:  # noqa: BLE001 — el correo de GitHub llega igual
        return f"no se pudo avisar en Coral: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--coral", action="store_true", help="si falla, avisar también en Coral (identidad 'vigilante')")
    args = ap.parse_args(argv)
    alarmas = []
    for pieza, (ok, motivo) in (("OPENAI", comprobar()), ("OPENROUTER", comprobar_openrouter())):
        print(f"[SALDO][{pieza}] {'ok' if ok else 'ALERTA'}: {motivo}")
        if not ok:
            alarmas.append(motivo)
    if not alarmas:
        return 0
    if args.coral:
        print(f"[SALDO] {avisar_en_coral('; '.join(alarmas))}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
