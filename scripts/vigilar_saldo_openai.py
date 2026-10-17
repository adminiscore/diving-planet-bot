"""r6-1(c): ¿le queda saldo a la cuenta de OpenAI de PRE? Una llamada mínima (1 token) con la clave del bot.

Se lanza cada hora desde GitHub Actions (`.github/workflows/vigilar-saldo-openai.yml`) DENTRO del contenedor de PRE:

    docker exec dp-pre-bot python -m scripts.vigilar_saldo_openai [--coral]

Sale con 0 si OpenAI contesta, y con 2 si la cuenta no puede contestar (sin saldo, clave inválida, caído tras
reintentos): el job de GitHub falla y GitHub manda un correo. Con `--coral` y la identidad `vigilante` del chat del
equipo (CORAL_URL + CORAL_TOKEN_VIGILANTE), además escribe un aviso en Coral. Un 429 de "demasiadas peticiones"
suelto no es falta de saldo: se reintenta. Nunca imprime la clave ni el token.

Por qué (17-oct): esta semana PRE se quedó mudo dos veces porque se acabó el crédito, y nadie se enteró hasta que
alguien probó el bot. Coste: ~1 token por hora.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

MODELO = "gpt-4o-mini"
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
            cliente.chat.completions.create(model=MODELO, max_tokens=1,
                                            messages=[{"role": "user", "content": "ok"}])
            return True, "OpenAI contesta"
        except Exception as exc:  # noqa: BLE001
            motivo, alarma = clasificar(exc)
            if alarma and "insufficient_quota" in motivo:
                return False, motivo  # sin saldo no se arregla reintentando
            if intento < REINTENTOS - 1:
                time.sleep(pausa)
    return False, motivo


def avisar_en_coral(motivo: str) -> str:
    url = os.environ.get("CORAL_URL", "").rstrip("/")
    token = os.environ.get("CORAL_TOKEN_VIGILANTE", "")
    if not url or not token:
        return "sin identidad 'vigilante' en Coral: solo el correo de GitHub"
    texto = (f"⚠️ ALERTA: la cuenta de OpenAI de PRE no puede contestar: {motivo}. El bot dice a los clientes que hay "
             "un problema técnico y los pasa a un asesor (si AVISO_SI_OPENAI_FALLA está encendido). Revisad el saldo "
             "y la clave de OpenAI.")
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
    ok, motivo = comprobar()
    if ok:
        print(f"[SALDO][OPENAI] ok: {motivo}")
        return 0
    print(f"[SALDO][OPENAI] ALERTA: {motivo}")
    if args.coral:
        print(f"[SALDO][OPENAI] {avisar_en_coral(motivo)}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
