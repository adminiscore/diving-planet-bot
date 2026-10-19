"""Banco del paso 5 de ex-9b: classify_route con señales de verdad (Jev + router LLM de respaldo), flag apagado/encendido."""
# Con red (Jev y el enrutador de respaldo por OpenRouter, ~0,0001 $ por llamada). Desde la raíz del repo:
#   ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_router.py

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.agents import supervisor  # noqa: E402
from src.agents.supervisor import detect_routing_signals  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402
from src.orchestration.router import classify_route  # noqa: E402

# La configuración de PRE (Jev encendido, sus preguntas, modelos), como en el compose.
_PRE = {k: v for k, v in expected_from_compose().items() if hasattr(settings, k)}
for _k, _v in _PRE.items():
    setattr(settings, _k, _v)
print('config de PRE:', len(_PRE), 'ajustes; jev_router_enabled =', settings.jev_router_enabled)

# (mensaje, idioma, rutas válidas)
CASOS = [
    # falsos positivos de hoy (no deben salir de la reserva/info)
    ("¿está mal si hago el pago mañana?", "es", {"booking", "info"}),
    ("quiero hablar con mi esposa antes de reservar", "es", {"booking", "info"}),
    ("me mandas el link por whatsapp?", "es", {"booking", "info"}),
    ("¿Dónde cojo la lancha al muelle?", "es", {"booking", "info"}),
    ("somos 4 adultos, ¿hay descuento?", "es", {"booking", "info"}),
    ("can I change my mind later about the date?", "en", {"booking", "info"}),
    # verdaderos positivos (sí deben dispararse)
    ("el link de pago no me funciona, me da error al pagar", "es", {"safety"}),
    ("quiero cancelar mi reserva del sábado", "es", {"changes"}),
    ("necesito cambiar la fecha de mi reserva al domingo", "es", {"changes"}),
    ("I need to cancel my booking for tomorrow", "en", {"changes"}),
    ("¿me pasas el número de teléfono de la oficina?", "es", {"deflection", "safety"}),
    ("quiero hablar con una persona, por favor", "es", {"safety"}),
    ("can I talk to a human?", "en", {"safety"}),
    ("me dio un ataque de asma ayer, ¿puedo bucear?", "es", {"safety"}),
    ("quiero poner una queja por el trato de ayer", "es", {"safety"}),
    ("mi hijo tiene autismo, ¿puede hacer el minicurso?", "es", {"info", "safety"}),
    ("éramos 4 pero uno no puede venir, ¿podemos cambiar a 3 personas?", "es", {"changes"}),
]


# El flag `regex_solo_si_ia_calla` se promocionó y se quitó (limpieza ex9b): "sin flag" es el regex decidiendo
# siempre, que es lo que hacía `supervisor.regex_decide` con el flag apagado.
_REGEX_DECIDE = supervisor.regex_decide


async def main():
    bien = {False: 0, True: 0}
    for msg, lang, validas in CASOS:
        sig = await detect_routing_signals(msg, lang=lang, pending_slot=None, history=[])
        fila = []
        for flag in (False, True):
            supervisor.regex_decide = _REGEX_DECIDE if flag else (lambda _signals: True)
            ruta = classify_route(ConversationState(conversation_id="b", language=lang), msg, sig or {})
            bien[flag] += ruta in validas
            fila.append(ruta)
        marca = "" if fila[1] in validas else "  <-- MAL con el flag"
        print(f"{msg[:58]!r:62} quiero={'/'.join(sorted(validas)):12} sin={fila[0]:8} con={fila[1]:8}{marca}")
    print(f"BIEN sin flag {bien[False]}/{len(CASOS)} · con flag {bien[True]}/{len(CASOS)}")


asyncio.run(main())
