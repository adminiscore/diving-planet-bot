"""G9 (17-oct, decisión de Gadea): genera el EXAMEN OCULTO SINTÉTICO, que se congela y se pasa UNA sola vez al final.

Por qué así: el examen oculto real (conversaciones nuevas de Diving Planet) se pide a Andrés cuando el bot ya esté
robusto. Mientras, este examen hace de oculto. Para que examine de verdad y no lo que ya sabemos arreglar:

- Los PERFILES salen de una combinación mecánica de dimensiones (idioma, actividad, origen, nacionalidad, etapa,
  estilo, trampa) con una semilla fija, no escogidos a mano por quien ha visto los fallos del bot.
- Las CONVERSACIONES y sus CRITERIOS los escribe OTRO modelo (`--modelo`, gpt-4.1 por defecto) con la referencia del
  negocio delante (`judge_golden_set.load_reference('curada')`, la misma que usa el juez) y el estilo de los diálogos
  reales del golden visible.
- Una segunda pasada comprueba que cada criterio esté respaldado por la referencia; los dudosos se marcan para que
  una persona los revise. Nadie más los mira.
- Se guarda con su huella (sha256). NO SE USA PARA AJUSTAR EL BOT: se pasa una vez con `run_synthetic_pre` y se juzga
  con `judge_golden_set` (mismos criterios globales). Lo que falle se arregla por causa y se mide en el banco.

    ENV_FILE=.env.dev python -m scripts.generar_examen_sintetico --n 72 --out docs/robustness/golden-set/examen-sintetico-g9.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"

# ---------------------------------------------------------------- perfiles: dimensiones (combinación mecánica)
IDIOMAS = ["es"] * 6 + ["en"] * 3 + ["pt"]
ACTIVIDADES = [
    "buceo certificado de un día", "paquete de varios días de buceo", "minicurso (primera vez, nunca ha buceado)",
    "curso Open Water (quiere certificarse)", "curso referido (empezó la teoría en otro centro)", "curso Advanced",
    "snorkel", "buzo certificado que lleva más de 2 años sin bucear", "grupo mixto: unos bucean y otros no",
    "familia con niños (da las edades)", "buceo adaptado / persona con discapacidad", "especialidad PADI",
    "no sabe qué quiere: pide recomendación",
]
ORIGENES = [
    "sale desde Cartagena", "ya está alojado en las islas (hotel base)", "ya está en las islas (otro hotel de la zona)",
    "dice un hotel que no se sabe dónde está", "pregunta por Barú u otro sitio donde no se opera", "no lo dice al principio",
]
NACIONALIDADES = ["colombiano", "extranjero", "grupo mixto colombianos y extranjeros", "residente con cédula de extranjería",
                  "no lo dice"]
ETAPAS = [
    "pre-venta: pregunta precios y qué incluye", "quiere reservar ya y pide el enlace", "pregunta disponibilidad para una fecha",
    "post-venta: ya reservó y pregunta qué llevar o la hora", "post-venta: quiere cambiar la fecha o cancelar",
    "problema con el pago o el enlace", "agencia o empresa pidiendo tarifas de grupo", "pregunta fotos, comida o recogida",
]
ESTILOS = [
    "mensajes muy cortos, sin tildes", "un mensaje largo con varias preguntas a la vez", "cambia de idea a mitad",
    "con faltas de ortografía y abreviaturas de WhatsApp", "muy educado y formal", "da fechas relativas (mañana, el finde)",
    "da sus datos poco a poco cuando el bot pregunta", "escribe como si fuera un audio transcrito",
]
EXTRAS = [None] * 7 + [
    "tiene una condición médica (asma, embarazo, medicación)", "se va mañana al mediodía (poco tiempo)",
    "pide un descuento especial", "pregunta por el clima", "intenta que el bot haga algo fuera de su papel",
    "pide hablar con una persona", "presupuesto ajustado",
]


def perfiles(n: int, semilla: int) -> list[dict]:
    rnd = random.Random(semilla)
    salida = []
    for i in range(n):
        salida.append({
            "id": f"g9-{i + 1:03d}",
            "idioma": IDIOMAS[i % len(IDIOMAS)],
            "actividad": ACTIVIDADES[i % len(ACTIVIDADES)],
            # Pesos parecidos a lo que llega de verdad (la mayoría sale de Cartagena o no lo dice, pre-venta), para que
            # lo raro (Barú, agencias, residentes con cédula de extranjería) esté pero no domine.
            "origen": rnd.choices(ORIGENES, weights=[35, 12, 10, 10, 8, 25])[0],
            "nacionalidad": rnd.choices(NACIONALIDADES, weights=[30, 35, 10, 5, 20])[0],
            "etapa": rnd.choices(ETAPAS, weights=[25, 15, 15, 10, 8, 7, 5, 15])[0],
            "estilo": rnd.choice(ESTILOS),
            "extra": rnd.choice(EXTRAS),
        })
    rnd.shuffle(salida)
    return salida


# ---------------------------------------------------------------- generación
SISTEMA = """Escribes casos de EXAMEN para el chatbot de WhatsApp de Diving Planet (centro de buceo PADI en Cartagena e Islas del Rosario, Colombia). Cada caso es una conversación: los mensajes del CLIENTE (no los del bot) y los CRITERIOS con los que un juez comprobará las respuestas del bot.

Reglas de los mensajes del cliente:
- Realistas, como un cliente de verdad por WhatsApp, siguiendo el perfil (idioma, estilo, lo que quiere, lo que sabe de sí mismo). Entre 2 y 6 mensajes. Si el idioma es "pt", escribe en portugués (el bot contestará en inglés).
- Los mensajes van fijos: el bot puede preguntar cosas; escribe los mensajes de forma que tengan sentido como respuestas típicas a un asesor (el cliente va dando sus datos), sin depender de una pregunta concreta del bot.
- Nada de datos personales reales: nombres inventados genéricos o ninguno; nunca teléfonos, correos ni documentos.

Reglas de los CRITERIOS (2 a 4 por caso):
- Cada criterio comprueba una CONDUCTA observable del bot en esta conversación, escrita como los del ejemplo: concreta y verificable con la REFERENCIA (precios, qué incluye, políticas, requisitos, horarios). Si el criterio depende de un dato, el dato tiene que estar en la REFERENCIA tal cual.
- Si el bot podría razonablemente preguntar un dato que falta antes de contestar, el criterio lo admite ("da el precio en COP… o pregunta desde dónde sale").
- Si el caso no llega a un punto (la conversación acaba antes), el criterio dice "si la conversación llega a…, …; si no, no aplica".
- No pongas criterios de estilo ni de idioma, ni de no inventar, ni de no repreguntar: esos los aplica el examen a todos los casos.
- Política del negocio que debes respetar en los criterios: el chatbot no da teléfonos ni WhatsApp (pasa a un asesor); los colombianos y residentes pagan en COP y el resto en USD, mismo precio; el 10 % online es automático, sin código; reservas y pagos por el enlace online; lo ya reservado o pagado (cambios, cancelaciones, comprobar pagos) lo gestiona una persona del equipo.

Devuelve SOLO JSON: {"casos": [{"id": "<el id del perfil>", "category": "<una palabra: info, reserva, curso, grupo, post-venta, pago, escalado, logistica, seguridad, ...>", "turns": ["mensaje 1", "..."], "criteria": [{"id": "<kebab-case>", "check": "<criterio>"}], "cobertura": {"idioma": "<es|en|pt>", "actividad": "<...>", "etapa": "<...>"}}]}"""

VALIDA = """Revisas criterios de un examen de un chatbot de buceo. Para cada criterio, di si lo que exige está RESPALDADO por la REFERENCIA del negocio (no contradice ningún dato y los datos que exige están en ella) y si es comprobable con los mensajes del cliente del caso. Devuelve SOLO JSON: {"criterios": [{"caso": "<id del caso>", "id": "<id del criterio>", "respaldado": true|false, "motivo": "<una frase si es false>"}]}"""


def _ejemplos_de_estilo(k: int = 4) -> str:
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    reales = [d for d in g["dialogues"] if d.get("turns") and "real" in json.dumps(d.get("source") or "", ensure_ascii=False)]
    reales = reales or [d for d in g["dialogues"] if d.get("turns")]
    rnd = random.Random(7)
    elegidos = rnd.sample(reales, min(k, len(reales)))
    return json.dumps([{"turns": d["turns"], "criteria": d["criteria"]} for d in elegidos], ensure_ascii=False)


async def _llamar(cliente, modelo: str, sistema: str, usuario: str, temperatura: float) -> dict:
    from src.llm_client import adaptar_parametros

    resp = await cliente.chat.completions.create(**adaptar_parametros(dict(
        model=modelo, temperature=temperatura, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])))
    return json.loads(resp.choices[0].message.content or "{}")


async def generar(n: int, semilla: int, modelo: str, por_llamada: int) -> list[dict]:
    from openai import AsyncOpenAI

    from scripts.judge_golden_set import load_reference
    from src.config import settings

    cliente = AsyncOpenAI(api_key=settings.openai_api_key)
    referencia = load_reference("curada")
    ejemplos = _ejemplos_de_estilo()
    perf = perfiles(n, semilla)
    lotes = [perf[i:i + por_llamada] for i in range(0, len(perf), por_llamada)]
    sem = asyncio.Semaphore(4)

    async def un_lote(lote):
        async with sem:
            # La referencia va DELANTE y es igual en todas las llamadas: OpenAI cachea el prefijo.
            usuario = (f"REFERENCIA DEL NEGOCIO:\n{referencia}\n\nEJEMPLOS DE CASOS REALES (estilo y forma de los "
                       f"criterios):\n{ejemplos}\n\nPERFILES (un caso por perfil, con su id):\n"
                       f"{json.dumps(lote, ensure_ascii=False)}")
            datos = await _llamar(cliente, modelo, SISTEMA, usuario, 0.8)
            return datos.get("casos") or []

    casos = [c for lote in await asyncio.gather(*(un_lote(lt) for lt in lotes)) for c in lote]

    async def validar(lote):
        # Por lotes y con la referencia delante (mismo prefijo, cacheado): una llamada por cada 4 casos.
        async with sem:
            usuario = (f"REFERENCIA:\n{referencia}\n\nCASOS:\n" + json.dumps(
                [{"caso": c.get("id"), "turns": c.get("turns"), "criteria": c.get("criteria")} for c in lote],
                ensure_ascii=False))
            v = await _llamar(cliente, modelo, VALIDA, usuario, 0.0)
            for x in v.get("criterios", []):
                if not x.get("respaldado", True):
                    caso = next((c for c in lote if c.get("id") == x.get("caso")), None)
                    if caso is not None:
                        caso.setdefault("revisar", {})[x.get("id")] = x.get("motivo", "")

    await asyncio.gather(*(validar(casos[i:i + por_llamada]) for i in range(0, len(casos), por_llamada)))
    por_id = {p["id"]: p for p in perf}
    for c in casos:
        c["source"] = {"tipo": "sintetico-g9", "perfil": por_id.get(c.get("id"))}
    return casos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--semilla", type=int, default=20261017)
    ap.add_argument("--modelo", default="gpt-4.1")
    ap.add_argument("--por-llamada", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--solo-perfiles", action="store_true", help="solo imprime los perfiles (sin API)")
    args = ap.parse_args()
    if args.solo_perfiles:
        for p in perfiles(args.n, args.semilla):
            print(json.dumps(p, ensure_ascii=False))
        return
    casos = asyncio.run(generar(args.n, args.semilla, args.modelo, args.por_llamada))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cuerpo = json.dumps(casos, ensure_ascii=False, sort_keys=True)
    salida = {
        "version": 1,
        "status": "CONGELADO: no se usa para ajustar el bot; se pasa UNA vez al final (G9)",
        "about": __doc__.split("\n\n")[0],
        "generado": {"at": datetime.now(UTC).isoformat(timespec="seconds"), "modelo": args.modelo,
                     "semilla": args.semilla, "n": args.n, "sha256": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()},
        "global_criteria": golden["global_criteria"],
        "dialogues": casos,
    }
    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    revisar = [c["id"] for c in casos if c.get("revisar")]
    print(f"{len(casos)} casos → {args.out} · criterios a revisar en {len(revisar)} casos: {revisar}")


if __name__ == "__main__":
    main()
