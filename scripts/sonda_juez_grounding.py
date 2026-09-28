"""Banco del juez de grounding v2 (flag `rag_v2`): ¿rechaza los datos del negocio inventados y deja
pasar lo que no es un dato? Casos: los inventos que el juez v2 dejó pasar en las rondas B del 27-sep
("llevamos 30 años", "debes haber completado la teoría"…) y respuestas correctas o de cortesía que el
juez v1 mandaba al "no lo tengo". Compara el prompt en uso con un candidato.

    python -m scripts.sonda_juez_grounding
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import AsyncOpenAI  # noqa: E402

from src.config import settings  # noqa: E402
from src.prompts import info  # noqa: E402

CTX_5 = ("Paquete de 5 inmersiones (2 dias): requisitos: Ser buzo certificado y presentar tu carnet; Con este plan "
         "debes alojarte 1 noche en las Islas del Rosario (hotel no incluido); Despues de bucear, esperar minimo 18 "
         "horas antes de tomar un vuelo. Debes completar el formato del seguro que enviamos por correo.")
CTX_FOTOS = ("Fotos y videos: no estan incluidos; el instructor puede tomarlos de forma voluntaria y se agradece una "
             "propina. Salidas de Buceo - 2 inmersiones (1 dia): 178 USD online. Punto de encuentro: Muelle de la "
             "Bodeguita a las 8:00 a.m.")
CTX_PICKUP = ("Curso Open Water desde Cartagena: incluye transporte en lancha Cartagena-Islas-Cartagena; punto de "
              "encuentro Muelle de la Bodeguita 8:00 a.m. Si ya estas en las islas: recogida en tu hotel si tiene "
              "acceso maritimo.")
CTX_RESCHEDULE = ("Los cambios de fecha estan sujetos a disponibilidad y a los terminos y condiciones: "
                  "https://divingplanet.org/terminos-y-condiciones/")

# (contexto, respuesta, lo que DEBE decir el juez)
CASOS = [
    (CTX_FOTOS, "¡Claro! Llevamos 30 años en las Islas del Rosario mostrando los arrecifes. Las fotos no están "
                "incluidas, el instructor puede tomarlas si quiere.", "HALLUCINATED"),
    (CTX_5, "Si no has tenido un largo periodo sin bucear no necesitas nada especial. Solo recuerda que antes de "
            "bucear debes haber completado la teoría y el formato del seguro.", "HALLUCINATED"),
    (CTX_PICKUP, "Yes! The Open Water course from Cartagena includes hotel pick-up and the boat to the islands.",
     "HALLUCINATED"),
    (CTX_RESCHEDULE, "Tranquilo: puedes esperar y avisarnos cuando decidas, así no pierdes tu reserva ni tu dinero.",
     "HALLUCINATED"),
    (CTX_FOTOS, "En las Islas del Rosario hay barcos hundidos que visitamos en algunas inmersiones.", "HALLUCINATED"),
    (CTX_5, "Para el paquete de 5 inmersiones necesitas ser buzo certificado, presentar tu carnet y alojarte 1 noche "
            "en las islas (el hotel no está incluido).", "GROUNDED"),
    (CTX_FOTOS, "¡Hola! Soy Coral, de Diving Planet 🪸 ¿En qué te puedo ayudar hoy?", "GROUNDED"),
    (CTX_PICKUP, "Sí: desde Cartagena el curso incluye la lancha ida y vuelta; el punto de encuentro es el Muelle de "
                 "la Bodeguita a las 8:00 a.m. ¿Quieres que te ayude con la reserva?", "GROUNDED"),
    (CTX_RESCHEDULE, "Ese detalle puntual no lo tengo a la mano, pero te puedo pasar con un asesor para revisarlo.",
     "GROUNDED"),
    (CTX_FOTOS, "¡Qué bonito plan! El buceo en el Caribe es una experiencia increíble. Las fotos no van incluidas; "
                "el instructor puede tomarlas de forma voluntaria.", "GROUNDED"),
    # Ronda B del 28-sep: un precio correcto con otros separadores y el nocturno dicho en otra frase.
    ("- Paquete de 5 inmersiones (2 dias): 392 USD / 1.429.000 COP online, 436 USD / 1.587.000 COP normal; 2 días; "
     "incluye un buceo nocturno; hay que dormir en las islas (alojamiento no incluido).",
     "El paquete de 5 inmersiones (2 días, con un buceo nocturno) cuesta $1,587,000 COP precio normal y $1,429,000 "
     "COP online.", "GROUNDED"),
]
# Paso 9 (28-sep): el contexto REAL es largo (catalogo + documentos + historial); con contextos cortos el
# banco no vio que una variante del juez rechazaba precios del catalogo. Estos casos van con el catalogo entero.
def _ctx_largo():
    from src.flows.catalog import catalog_booking_links, catalog_facts
    nl = chr(10)
    docs = nl.join([
        "Pregunta: ¿Como es el Curso Basico PADI (Open Water)? Respuesta: Curso de 2 dias: teoria online, piscina y 4 "
        "inmersiones. Dia 1: Muelle de la Bodeguita 8:00 a.m., noche en las islas (hotel no incluido).",
        "Pregunta: ¿Que medios de pago aceptan? Respuesta: Para extranjeros: 100% online con tarjeta, o presencial "
        "con tarjeta o efectivo.",
    ])
    return nl.join([catalog_facts("es"), catalog_booking_links("es"), "", docs, "", "Contexto adicional: cliente colombiano."])


CTX_LARGO = _ctx_largo()
CASOS += [
    (CTX_LARGO, "El curso básico PADI para colombianos cuesta 2.450.000 COP online o 2.722.000 COP con tarifa normal. Dura "
                "2 días y pasas la noche en las islas (hotel no incluido).", "GROUNDED"),
    (CTX_LARGO, "También puedes pagar presencialmente con tarjeta o efectivo cuando llegues.", "GROUNDED"),
    (CTX_LARGO, "¡Claro! Llevamos 30 años explorando esos sitios y operamos con instructores PADI 5 estrellas.",
     "HALLUCINATED"),
]
N = 3


async def judge(client, prompt, ctx, answer):
    r = await client.chat.completions.create(
        model=os.environ.get("JUEZ_MODEL", settings.rag_answer_model), temperature=0, max_tokens=300,
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": f"CONTEXTO:\n{ctx}\n\nRESPUESTA:\n{answer}"}],
    )
    from src.agents.grounding_check import verdict_from_fact_list
    if prompt in (info.GROUNDING_VERIFY_V2_ES,):
        return "GROUNDED" if (r.choices[0].message.content or "").strip().upper().startswith("GROUNDED") else "HALLUCINATED"
    return "GROUNDED" if verdict_from_fact_list(r.choices[0].message.content or "") else "HALLUCINATED"


async def main() -> None:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompts = {"v2": info.GROUNDING_VERIFY_V2_ES, "v3": info.GROUNDING_VERIFY_V3_ES}
    for name, prompt in prompts.items():
        ok = 0
        for ctx, ans, want in CASOS:
            p_case = info.GROUNDING_VERIFY_V3_EN if (name == "v3" and ans.startswith("Yes!")) else prompt
            got = await asyncio.gather(*(judge(client, p_case, ctx, ans) for _ in range(N)))
            hits = sum(g == want for g in got)
            ok += hits
            print(f"{name} {hits}/{N} {want:12} {ans[:70]}")
        print(f"== {name}: {ok}/{N * len(CASOS)}\n")


if __name__ == "__main__":
    asyncio.run(main())
