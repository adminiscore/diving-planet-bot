"""Calibra una pregunta nueva de Jev: ¿empieza el cliente un caso NUEVO (borrar memoria) o sigue con el de antes?"""
# Con red (Jev por OpenRouter, ~0,0001 $ por llamada). Desde la raíz del repo:
#   ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_nuevo_caso.py "<instrucciones de la pregunta>"

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

for k, v in expected_from_compose().items():
    if hasattr(settings, k):
        setattr(settings, k, v)
from src.agents import jev_router as j  # noqa: E402
from src.agents.rutas.router import _is_new_scenario_restart  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

Q = {"type": "noul", "instructions": sys.argv[1] if len(sys.argv) > 1 else ""}
HIST = [
    {"role": "user", "content": "hola, somos 2 y queremos bucear el sábado, nos quedamos en Bocagrande"},
    {"role": "assistant", "content": "¡Genial! 2 personas para bucear el sábado. ¿Ya son buzos certificados?"},
    {"role": "user", "content": "no, nunca hemos buceado"},
    {"role": "assistant", "content": "Entonces el minicurso es ideal para ustedes. ¿Les reservo para el sábado?"},
]
CASOS = [  # (mensaje, ¿caso nuevo?)
    ("Hola, soy Laura. Quiero información del curso Open Water para mí sola en noviembre", True),
    ("Hola, me llamo Pedro, somos 5 amigos y queremos hacer snorkel el 20 de diciembre", True),
    ("Hi, I'm Mark, my wife and I are certified and want to dive next month, what options do you have?", True),
    ("Buenas tardes, mi nombre es Carla, quería saber precios de buceo para un grupo de 8 en enero", True),
    ("Hola, somos 3 al final, ¿sigue en pie lo del sábado?", False),
    ("Hola buenos días, soy Ana, ya hablamos ayer, al final somos 3", False),
    ("Hola! soy María, la que escribió ayer por el buceo del sábado, ¿ya me pueden mandar el link?", False),
    ("Buenas tardes, me llamo Juan, ¿al final a qué hora sale la lancha el sábado?", False),
    ("Hi, I'm Tom again, we are 3 now instead of 2", False),
    ("Hola, soy la esposa de Juan, él me pidió que siguiera yo con la reserva del sábado", False),
]


async def main():
    st = ConversationState(conversation_id="nc", language="es")
    st.history = list(HIST)
    st.detected_group_size = 2
    bien = 0
    for msg, quiero in CASOS:
        ps = []
        for _ in range(2):
            r = await j._http().post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                                     json={"model": settings.jev_model, "state": j._estado_para_jev(msg, HIST),
                                           "questions": {"nuevo_caso": Q}}, timeout=15)
            ps.append(round(r.json()["answers"]["nuevo_caso"].get("noul", 0.0), 2))
        ok = all((p >= 0.7) == quiero for p in ps)
        bien += ok
        print(f"{msg[:70]!r:74} quiero={quiero!s:5} regex={_is_new_scenario_restart(msg, st)!s:5} jev={ps}"
              f"{'' if ok else '  <-- MAL'}")
    print("bien", bien, "/", len(CASOS))


asyncio.run(main())
