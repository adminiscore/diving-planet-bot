"""G9 (17-oct, decisión de Gadea): genera el EXAMEN OCULTO SINTÉTICO, que se congela y se pasa UNA sola vez al final.

Por qué así: el examen oculto real (conversaciones nuevas de Diving Planet) se pide a Andrés cuando el bot ya esté
robusto. Mientras, este examen hace de oculto. Para que examine de verdad y no lo que ya sabemos arreglar:

- Los PERFILES salen de una combinación mecánica de dimensiones (idioma, actividad, origen, nacionalidad, etapa,
  estilo, trampa) con una semilla fija, no escogidos a mano por quien ha visto los fallos del bot.
- Las CONVERSACIONES y sus CRITERIOS los escribe OTRO modelo (`--modelo`, gpt-5-mini por defecto desde el 26-oct: como
  máximo gpt-5-mini sin permiso de Gadea; G9 y G10 se generaron con gpt-4.1) con la referencia del negocio delante
  (`judge_golden_set.load_reference('curada')`, la misma que usa el juez) y el estilo de los diálogos reales del golden
  visible (nunca del examen oculto).
- Los criterios CITAN las decisiones del negocio («(decisión «moneda»)», de data/knowledge_base/decisiones.json, que
  está en la referencia) y «lo que dice la base» para los datos, sin copiarlos (punto 2, 26-oct): el que copia una regla
  (`scripts/criterios_sin_reglas.py`, lo mismo que vigila el test del golden) se quita.
- Una segunda pasada comprueba que cada criterio esté respaldado por la referencia; los dudosos se marcan para que
  una persona los revise. Nadie más los mira.
- Se guarda con su huella (sha256). NO SE USA PARA AJUSTAR EL BOT: se pasa una vez con `run_synthetic_pre` y se juzga
  con `judge_golden_set` (mismos criterios globales). Lo que falle se arregla por causa y se mide en el banco.

    ENV_FILE=.env.dev python -m scripts.generar_examen_sintetico --n 72 --out docs/robustness/golden-set/examen-sintetico-g9.json

TANDA ROTATIVA (punto 3, 26-oct, decisión de Gadea): el golden visible lleva semanas de arreglos encima y sube sin que
suba el oculto. Una tanda nueva cada vez (semilla del día, ids `rot<fecha>-NNN`, en docs/robustness/rotativo/) mide si
el bot generaliza sin gastar el examen oculto: se pasa con la misma A/B que el golden, se juzga una vez y la siguiente
medida usa otra tanda. No se arregla caso a caso (se mira la cifra y las causas, como con el oculto).

    ENV_FILE=.env.dev python -m scripts.generar_examen_sintetico --rotativo            # 30 casos con gpt-5-mini
    ENV_FILE=.env.dev python -m scripts.ronda_local_pre --name rot-B --golden docs/robustness/rotativo/<fecha>.json \\
        --sample golden --codigo-local --metricas
    ENV_FILE=.env.dev python -m scripts.judge_golden_set --run <la ronda> --golden docs/robustness/rotativo/<fecha>.json
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


def perfiles(n: int, semilla: int, prefijo: str = "g9") -> list[dict]:
    rnd = random.Random(semilla)
    salida = []
    for i in range(n):
        salida.append({
            "id": f"{prefijo}-{i + 1:03d}",
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
- Si el bot podría razonablemente preguntar un dato que falta antes de contestar, el criterio lo admite, salvo que una decisión del negocio diga qué hacer cuando falta ese dato (entonces la cita: "si no sabe desde dónde sale, como manda la decisión «origen-y-precio»").
- Si el caso no llega a un punto (la conversación acaba antes), el criterio dice "si la conversación llega a…, …; si no, no aplica".
- No pongas criterios de estilo ni de idioma, ni de no inventar, ni de no repreguntar: esos los aplica el examen a todos los casos.
- Las decisiones del negocio están en la REFERENCIA, en «Decisiones del negocio». Si un criterio depende de una, la CITA por su id así: "(decisión «moneda»)", y NO la copia (nada de "en USD por ser extranjero" ni "antes de dar el precio pregunta el origen"). Si depende de un dato del negocio (un precio, una hora, una edad mínima, los días o las noches de un plan), dice "el de la base" o "lo que dice la base" y NO escribe la cifra. Así el criterio sigue valiendo si el negocio cambia una decisión o un dato. Los datos del CLIENTE (su edad, la cifra que cita, la moneda que pide) sí se escriben.
- Lo ya reservado o pagado (cambios, cancelaciones, comprobar pagos) lo gestiona una persona del equipo. No pongas criterios que exijan un dato que no esté en la REFERENCIA (por ejemplo, una lista de qué llevar o un mínimo de personas que la referencia no da).

Devuelve SOLO JSON: {"casos": [{"id": "<el id del perfil>", "category": "<una palabra: info, reserva, curso, grupo, post-venta, pago, escalado, logistica, seguridad, ...>", "turns": ["mensaje 1", "..."], "criteria": [{"id": "<kebab-case>", "check": "<criterio>"}], "cobertura": {"idioma": "<es|en|pt>", "actividad": "<...>", "etapa": "<...>"}}]}"""

# G10 (21-oct) añadía aquí, copiadas, las decisiones de octubre (POLITICA_DESDE_G10, con la moneda de entonces: «si no
# se sabe la nacionalidad, en USD»). Desde el 26-oct están en la referencia (decisiones.json) y los criterios las citan.

VALIDA = """Revisas criterios de un examen de un chatbot de buceo. Para cada criterio, di si lo que exige está RESPALDADO por la REFERENCIA del negocio (no contradice ningún dato y los datos que exige están en ella) y si es comprobable con los mensajes del cliente del caso. Devuelve SOLO JSON: {"criterios": [{"caso": "<id del caso>", "id": "<id del criterio>", "respaldado": true|false, "motivo": "<una frase si es false>"}]}"""


def _ejemplos_de_estilo(k: int = 4) -> str:
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # Nunca del examen oculto (que va dentro del golden con `suite: "oculto"`): sus casos no se le enseñan a nadie.
    visibles = [d for d in g["dialogues"] if d.get("turns") and d.get("suite") != "oculto"]
    reales = [d for d in visibles if "real" in json.dumps(d.get("source") or "", ensure_ascii=False)] or visibles
    rnd = random.Random(7)
    elegidos = rnd.sample(reales, min(k, len(reales)))
    return json.dumps([{"turns": d["turns"], "criteria": d["criteria"]} for d in elegidos], ensure_ascii=False)


async def _llamar(cliente, modelo: str, sistema: str, usuario: str, temperatura: float) -> dict:
    from src.llm_client import adaptar_parametros

    kwargs = dict(model=modelo, response_format={"type": "json_object"},
                  messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])
    # gpt-5 / gpt-5-mini razonan y solo admiten la temperatura por defecto.
    if not (modelo.startswith("gpt-5") and not modelo.startswith(("gpt-5.4", "gpt-5.5", "gpt-5.6"))):
        kwargs["temperature"] = temperatura
    resp = await cliente.chat.completions.create(**adaptar_parametros(kwargs))
    return json.loads(resp.choices[0].message.content or "{}")


async def generar(n: int, semilla: int, modelo: str, por_llamada: int, prefijo: str = "g9",
                  quitar_no_respaldados: bool = False) -> list[dict]:
    from openai import AsyncOpenAI

    from scripts.judge_golden_set import load_reference
    from src.config import settings

    cliente = AsyncOpenAI(api_key=settings.openai_api_key)
    referencia = load_reference("curada")
    ejemplos = _ejemplos_de_estilo()
    perf = perfiles(n, semilla, prefijo)
    sistema = SISTEMA
    lotes = [perf[i:i + por_llamada] for i in range(0, len(perf), por_llamada)]
    sem = asyncio.Semaphore(4)

    async def un_lote(lote):
        async with sem:
            # La referencia va DELANTE y es igual en todas las llamadas: OpenAI cachea el prefijo.
            usuario = (f"REFERENCIA DEL NEGOCIO:\n{referencia}\n\nEJEMPLOS DE CASOS REALES (estilo y forma de los "
                       f"criterios):\n{ejemplos}\n\nPERFILES (un caso por perfil, con su id):\n"
                       f"{json.dumps(lote, ensure_ascii=False)}")
            datos = await _llamar(cliente, modelo, sistema, usuario, 0.8)
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
                        if quitar_no_respaldados:
                            # G10: sin revisión humana (nadie abre el examen): el criterio dudoso se quita.
                            caso["criteria"] = [k for k in caso.get("criteria") or [] if k.get("id") != x.get("id")]

    await asyncio.gather(*(validar(casos[i:i + por_llamada]) for i in range(0, len(casos), por_llamada)))
    # Punto 2: el criterio que copia una regla o un dato del negocio en vez de citarlo se quita (las mismas reglas que
    # vigilan el golden), para que la tanda no se desfase cuando el negocio decida otra cosa.
    from scripts.criterios_sin_reglas import reglas_copiadas

    for c in casos:
        copian = [k for k in c.get("criteria") or [] if reglas_copiadas(k.get("check") or "")]
        if copian:
            c["criteria"] = [k for k in c["criteria"] if k not in copian]
            c.setdefault("revisar", {}).update({k.get("id"): "copiaba una regla o un dato del negocio" for k in copian})
    por_id = {p["id"]: p for p in perf}
    for c in casos:
        c["source"] = {"tipo": f"sintetico-{prefijo}", "perfil": por_id.get(c.get("id"))}
    return [c for c in casos if c.get("criteria")]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--semilla", type=int, default=20261017)
    ap.add_argument("--modelo", default="gpt-5-mini")
    ap.add_argument("--por-llamada", type=int, default=4)
    ap.add_argument("--out")
    ap.add_argument("--solo-perfiles", action="store_true", help="solo imprime los perfiles (sin API)")
    ap.add_argument("--prefijo", default="g9", help="prefijo de los ids (g10: el examen nuevo, con la política nueva)")
    ap.add_argument("--quitar-no-respaldados", action="store_true",
                    help="quita los criterios que la segunda pasada no ve respaldados (sin revisión humana)")
    ap.add_argument("--rotativo", action="store_true",
                    help="tanda rotativa (punto 3): 30 casos, semilla e ids del día, sin revisión humana, en "
                         "docs/robustness/rotativo/<fecha>.json")
    args = ap.parse_args()
    if args.rotativo:
        hoy = datetime.now(UTC)
        if args.n == ap.get_default("n"):
            args.n = 30
        if args.semilla == ap.get_default("semilla"):
            args.semilla = int(f"{hoy:%Y%m%d%H}")
        args.prefijo = f"rot{hoy:%Y%m%d%H}"
        args.quitar_no_respaldados = True
        args.out = args.out or str(ROOT / "docs/robustness/rotativo" / f"{hoy:%Y-%m-%d-%H}.json")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if not args.out and not args.solo_perfiles:
        ap.error("falta --out (o --rotativo)")
    args.status = ("ROTATIVA (punto 3): se juzga en la A/B de una medida y la siguiente usa otra tanda; no se arregla "
                   "caso a caso" if args.rotativo else
                   f"CONGELADO: no se usa para ajustar el bot; se pasa UNA vez al final ({args.prefijo.upper()})")
    if args.solo_perfiles:
        for p in perfiles(args.n, args.semilla, args.prefijo):
            print(json.dumps(p, ensure_ascii=False))
        return
    casos = asyncio.run(generar(args.n, args.semilla, args.modelo, args.por_llamada, args.prefijo,
                                args.quitar_no_respaldados))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cuerpo = json.dumps(casos, ensure_ascii=False, sort_keys=True)
    salida = {
        "version": 1,
        "status": args.status,
        "about": __doc__.split("\n\n")[0],
        "generado": {"at": datetime.now(UTC).isoformat(timespec="seconds"), "modelo": args.modelo,
                     "semilla": args.semilla, "n": args.n, "prefijo": args.prefijo,
                     "quitar_no_respaldados": args.quitar_no_respaldados,
                     "sha256": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()},
        "global_criteria": golden["global_criteria"],
        "dialogues": casos,
    }
    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    revisar = [c["id"] for c in casos if c.get("revisar")]
    criterios = sum(len(c.get("criteria") or []) for c in casos)
    # Solo cuentas: el contenido del examen no se imprime (nadie lo mira).
    print(f"{len(casos)} casos, {criterios} criterios → {args.out} · casos con criterios dudosos: {len(revisar)}"
          + (" (quitados)" if args.quitar_no_respaldados else f": {revisar}"))


if __name__ == "__main__":
    main()
