"""Banco de calibración de la pregunta de Jev `needs_staff` (paso 6, s4-20, flag `s4_fixes`, 27-sep).

Post-venta y trato de empresa: lo que solo resuelve una persona del equipo (el bot no ve reservas,
pagos ni correos). Positivos escritos para el banco (variantes de post-venta, agencia, revisión de
documentos); negativos: preguntas normales de información y de reserva nueva, incluidas las que se
parecen ("¿cuál es la política de cancelación?", "¿cómo pago?", "ya reservé el hotel en la isla").

    python -m scripts.sonda_necesita_persona
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from scripts.sonda_afirma_vs_pregunta import _preguntar  # noqa: E402
from src.agents import jev_router  # noqa: E402

POSITIVOS = [
    "Hola, ya hice la reserva por la web para el sábado, ¿me confirman que la recibieron?",
    "I paid online yesterday, can you check my booking went through?",
    "¿Está todo bien con nuestras reservas del 12 de marzo?",
    "Buenas, les escribo de la agencia Mar Azul, queremos las tarifas 2026 para operadores",
    "We are a travel agency and would like to discuss net rates for our groups",
    "Les mandé un correo la semana pasada y nadie me ha contestado",
    "I sent you my dive logs, could the instructor approve them so I can join the advanced?",
    "¿Pueden revisar mi certificado PADI que les envié por correo?",
    "Reservé para 4 pero no me llegó el correo de confirmación",
    "Soy Laura de la agencia de viajes Caribe Tours",
    "Hello, we booked the 5 dive package for next week under my name, just checking everything is fine",
]
NEGATIVOS = [
    "¿Cuál es la política de cancelación?",
    "how do I pay?",
    "Quiero reservar 2 inmersiones para el sábado",
    "¿Tienen disponibilidad el 24 de abril?",
    "Ya reservé el hotel en la isla, ¿me recogen allí?",
    "We will book diving with you on the website",
    "¿Qué tengo que llevar el día del buceo?",
    "somos 3 y uno hace snorkel",
    "¿Cuánto cuesta el curso Open Water?",
    "si cancelo me devuelven el dinero?",
    "Do we use WhatsApp to book or is there somewhere on the website?",
    "Me pasas el contacto del hotel cocoliso?",
    "¿Se puede pagar con transferencia?",
    "Hola, quisiera averiguar por las salidas de buceo de 2 días",
    "Somos un grupo de 8 amigos, ¿tienen descuento de grupo?",
    "Trabajo en una empresa y quiero regalar un minicurso a mi jefe",
]
N = 2


async def main() -> None:
    q = jev_router._NEEDS_STAFF_Q["instructions"]
    async with httpx.AsyncClient() as cli:
        async def score(m):
            vals = [await _preguntar(cli, m, q) for _ in range(N)]
            return sum(vals) / len(vals)
        pos = await asyncio.gather(*(score(m) for m in POSITIVOS))
        neg = await asyncio.gather(*(score(m) for m in NEGATIVOS))
    for label, msgs, vals in (("POS", POSITIVOS, pos), ("NEG", NEGATIVOS, neg)):
        for m, v in sorted(zip(msgs, vals), key=lambda x: x[1]):
            print(f"{label} {v:.2f}  {m[:90]}")
    t = jev_router.NEEDS_STAFF_MIN
    print(f"\numbral {t}: positivos {sum(v >= t for v in pos)}/{len(pos)}, "
          f"falsas alarmas {sum(v >= t for v in neg)}/{len(neg)}")


if __name__ == "__main__":
    asyncio.run(main())
