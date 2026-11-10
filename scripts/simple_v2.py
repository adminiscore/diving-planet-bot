"""Simplificar (10-nov), V2: V1 más la puerta del código. Prototipo fuera de src.

Diseño: `docs/robustness/caln/diseno-puerta-v2.md` (v2, tras la revisión independiente). Luna escribe en una llamada, como en V1
(`scripts/simple_v1.py`, que no se toca, #3763) y dice qué entendió. El código decide y comprueba cuatro cosas sobre eso: el pase
(C1), los importes (C2), el enlace (C3) y la pregunta (C4). Lo que no cumple se rehace una vez con el motivo; si vuelve a fallar,
manda la decisión del código (norma 5: nunca se recorta). Cada turno guarda en `estado.puerta` qué falló, si rehízo y qué puso el
código, para los topes fijados antes de medir (rehechos ≤ 25 %, plantilla ≤ 3 %).

    ENV_FILE=<repo>/.env.dev python -m scripts.simple_v2 --out docs/robustness/caln/simple/v2-a.jsonl
    ENV_FILE=<repo>/.env.dev python -m scripts.simple_v2 --banco <fichero> --out <salida> --ids visto-6914
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from pathlib import Path

from scripts import simple_v1 as v1

# ── 1. El esquema de V2: el de V1 más lo que la puerta necesita (solo en este envoltorio) ─────────────────────────────────────────
MOTIVOS = ("reservar_con_asesor", "ya_reservo", "salud", "clima_del_dia", "recogida_fuera", "pide_persona", "horario",
           "origen_sin_saber", "la_base_no_lo_tiene")
TEMAS = ("origen", "fecha", "personas", "certificado", "hotel", "nacionalidad", "edades", "refresher", "plan", "otra")
ESQUEMA_V2 = """Respondes SIEMPRE con un único objeto JSON, sin nada fuera de él:
{"entendido": {"origen": "cartagena" | "islas" | null, "hotel": texto o null, "nacionalidad": "colombiana" | "residente" | "extranjera" | "mixta" | null, "personas": número o null, "edades": lista de números o null, "reparto": {tipo: personas} o null, "plan": id del catálogo o null, "certificado": true | false | null, "refresher": true | false | null, "fecha": texto o null, "dias": número o null, "equipo_propio": true | false, "a_nombre_de_otro": true | false, "idioma": "es" | "en", "quiere_reservar": true | false, "ya_reservo": true | false},
 "pasar": {"si": true | false, "motivo": uno de [MOTIVOS] o null, "tema": texto corto o null},
 "pregunta": {"tema": uno de [TEMAS]} o null,
 "texto": tu mensaje al cliente, coherente con «entendido», «pasar» y «pregunta»}
En «entendido» pones lo que sabes del cliente hasta ahora (lo que ya entendiste en turnos anteriores más lo nuevo de su mensaje). Si un dato no lo ha dicho, null: no lo adivines. «mixta»: un grupo con colombianos y extranjeros. «reparto»: cuántas personas hacen cada cosa, con estos tipos: certified_diving (buceo de certificados), minicourse, bubble_makers (niños de 8 a 10), snorkel, companion (va en la lancha sin actividad), padi_open_water, padi_open_water_referral, padi_advanced, padi_rescue, padi_divemaster, specialty_nitrox, specialty_buoyancy, specialty_naturalist, specialty_fish_identification, specialty_mindful_diving. «plan»: el id exacto del catálogo, o null.
No ofreces pasar con una persona: si toca pasar, lo dices y lo marcas en «pasar» con su motivo; si no toca, no lo nombras. Un plan que reserva un asesor (colombianos o residentes, grupos de 5 o más, una parte o un plan sin enlace, equipo propio, a nombre de otro, una recogida que hay que confirmar) se pasa con «reservar_con_asesor» solo cuando el cliente ya quiere reservar o pagar; antes, le dices una vez por qué lo reserva un asesor y sigues contestando. No pasas por lo que contesta la base (hoteles, puntos de inmersión, qué llevar, comida, precios, horarios, disponibilidad). Los precios los das tal cual están en la base, por persona y en la moneda del cliente: nunca aplicas tú un descuento (los descuentos se nombran, no se restan) ni sumas un total. Solo preguntas si necesitas un dato para reservar y el cliente ya quiere reservar, o el origen cuando das precios sin saberlo; no preguntas para seguir la charla. «pregunta»: el tema de la pregunta que hace tu texto, o null si no pregunta nada.""".replace(
    "[MOTIVOS]", ", ".join(MOTIVOS)).replace("[TEMAS]", ", ".join(TEMAS))
_INICIO, _FIN = "Respondes SIEMPRE", "no lo adivines."
INSTRUCCIONES_V2 = (v1.INSTRUCCIONES[:v1.INSTRUCCIONES.index(_INICIO)] + ESQUEMA_V2
                    + v1.INSTRUCCIONES[v1.INSTRUCCIONES.index(_FIN) + len(_FIN):])
ENTENDIDO_VACIO = {**{k: v for k, v in v1._ENTENDIDO_VACIO.items() if k != "actividad"}, "nacionalidad": None, "reparto": None,
                   "equipo_propio": False, "a_nombre_de_otro": False, "idioma": None}

# ── 2. La decisión del momento de reservar, sobre lo entendido ────────────────────────────────────────────────────────────────────
POSVENTA, HOTEL_PRIMERO, ORIGEN_PRIMERO, ASESOR, ENLACE = "posventa", "hotel_primero", "origen_primero", "asesor", "enlace"
CON_DESCUENTO_DE_GRUPO = frozenset({"certified_diving", "minicourse", "snorkel", "companion"})  # como_reserva / discounts.json
SIN_ENLACE_EN_LA_WEB = frozenset({"bubble_makers", "companion", "padi_divemaster"})  # P10: una parte sin enlace


def _servicios() -> dict:
    from src.flows.catalog import SERVICES  # lazy

    return SERVICES


def servicio_del_plan(ent: dict) -> str | None:
    """El id del servicio del plan para su origen (el de las islas es `<plan>_already_on_island`); None si no es del catálogo."""
    plan, servicios = ent.get("plan"), _servicios()
    if plan not in servicios:
        return None
    base = plan.removesuffix("_already_on_island")
    if ent.get("origen") == "islas":
        return f"{base}_already_on_island" if f"{base}_already_on_island" in servicios else plan
    if ent.get("origen") == "cartagena":
        return base if base in servicios else plan
    return plan


def tiene_enlace(servicio: str) -> bool:
    s = _servicios().get(servicio) or {}
    return bool(s.get("booking_url")) and not s.get("contact_only")


_SIN_HOTEL = re.compile(r"no s[eé]|todav[ií]a|a[uú]n no|por confirmar|to be confirmed|not sure|don'?t know|yet", re.I)


def hotel_dicho(ent: dict) -> str | None:
    """El hotel que dijo, o None si no dijo ninguno de verdad («todavía no sé», «por confirmar», el nombre de una isla), como
    `como_reserva.hotel_conocido`."""
    from src.domain.lugares import solo_nombra_una_isla  # lazy

    hotel = ent.get("hotel")
    if not isinstance(hotel, str) or not hotel.strip() or _SIN_HOTEL.search(hotel) or solo_nombra_una_isla(hotel):
        return None
    return hotel


def decision(ent: dict) -> tuple[str, str | None]:
    """(forma, motivo del asesor). En el orden de `como_reserva.entrega` (4R): el hotel y el origen antes que el asesor (P5)."""
    from src.domain.lugares import recogida_conocida  # lazy
    from src.flows.como_reserva import minimo_del_grupo  # lazy

    if ent.get("ya_reservo"):
        return POSVENTA, None
    origen, hotel = ent.get("origen"), hotel_dicho(ent)
    if origen == "islas" and not hotel:
        return HOTEL_PRIMERO, None
    if origen not in ("cartagena", "islas"):
        return ORIGEN_PRIMERO, None
    if ent.get("nacionalidad") in ("colombiana", "residente"):
        return ASESOR, "pago en pesos"
    if origen == "islas" and not recogida_conocida(hotel):
        return ASESOR, "recogida por confirmar"
    reparto = ent.get("reparto") or {}
    plan = _servicios().get(ent.get("plan")) or {}
    # Sin reparto, cuentan las personas, salvo en un curso PADI, que no tiene descuento de grupo (discounts.json).
    con_descuento = (sum(n for a, n in reparto.items() if a in CON_DESCUENTO_DE_GRUPO) if reparto
                     else 0 if plan.get("category") == "course" else (ent.get("personas") or 0))
    if con_descuento >= minimo_del_grupo():
        return ASESOR, "grupo de 5 o más"
    if set(reparto) & SIN_ENLACE_EN_LA_WEB:  # una parte del plan, o todo, sin enlace (P10)
        return ASESOR, "una parte del plan sin enlace" if len(reparto) > 1 else "el plan no tiene enlace"
    if (servicio := servicio_del_plan(ent)) and not tiene_enlace(servicio):
        return ASESOR, "el plan no tiene enlace"
    if ent.get("equipo_propio"):
        return ASESOR, "equipo propio"
    if ent.get("a_nombre_de_otro"):
        return ASESOR, "a nombre de otro"
    return ENLACE, None


def enlace_que_toca(ent: dict) -> str | None:
    from src.flows.catalog import enlace_en_su_idioma  # lazy

    if decision(ent)[0] != ENLACE or not (servicio := servicio_del_plan(ent)) or not tiene_enlace(servicio):
        return None
    return enlace_en_su_idioma(_servicios()[servicio]["booking_url"], "en" if ent.get("idioma") == "en" else "es")


# ── 3. Lo que hay en el texto ──────────────────────────────────────────────────────────────────────────────────────────────────────
_URL = re.compile(r"https?://[^\s\"'<>]+?(?=[.,;:!?)\]*_\"'<>]*(?:[\s\"'<>]|$))")
_RESERVA = re.compile(r"https?://book\.divingplanet\.org/[^\s\"'<>]+?(?=[.,;:!?)\]*_\"'<>]*(?:[\s\"'<>]|$))")
_CIFRA = r"\d[\d.,']*\d|\d"
_IMPORTE = re.compile(rf"(?:\b(USD|US\$|COP)\b|\$)\s?({_CIFRA})(\s?mil\b)?|({_CIFRA})(\s?mil\b)?\s?(USD\b|US\$|d[oó]lares\b|dollars\b|COP\b|pesos\b)",
                      re.I)
_PORCENTAJE = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")


def _numero(cifra: str, moneda: str) -> float:
    cifra = cifra.replace("'", "")
    if moneda == "COP":
        return float(re.sub(r"[.,]", "", re.sub(r",\d{2}$", "", cifra)))  # «630.000,00 COP»: sin los céntimos
    if "," in cifra and len(cifra.rsplit(",", 1)[1]) in (1, 2):
        cifra = cifra.replace(".", "").replace(",", ".")
    elif "." in cifra and len(cifra.rsplit(".", 1)[1]) == 3:
        cifra = cifra.replace(".", "")
    return float(cifra.replace(",", ""))


def importes(texto: str) -> list[tuple[float, str]]:
    """Las cifras con moneda del texto, como (valor, «USD» | «COP»): «178 USD», «USD 178», «178 dólares», «630.000 COP», «COP 630
    mil», «$630 mil pesos», «448 mil pesos». «$N» sin más: COP desde 5.000, si no USD."""
    salen = []
    for m in _IMPORTE.finditer(_URL.sub(" ", texto or "")):
        if m.group(2):
            simbolo, cifra, mil = (m.group(1) or "$").upper(), m.group(2), bool(m.group(3))
            if simbolo == "$" and re.match(r"\s?(mil\s)?pesos", texto[m.end():m.end() + 12] or "", re.I):
                simbolo = "COP"
        else:
            cifra, mil, simbolo = m.group(4), bool(m.group(5)), m.group(6).upper()
        moneda = "COP" if simbolo in ("COP", "PESOS") or mil else "USD"
        if simbolo == "$" and not mil:
            moneda = "COP" if float(re.sub(r"[.,']", "", cifra)) >= 5000 else "USD"
        valor = _numero(cifra, moneda) * (1000 if mil else 1)
        salen.append((round(valor, 2), moneda))
    return salen


def preguntas(texto: str) -> int:
    return len(re.findall(r"\?+", _URL.sub(" ", texto or "")))


# ── 4. Las cuatro comprobaciones ──────────────────────────────────────────────────────────────────────────────────────────────────
_LA_BASE_CONTESTA = re.compile(r"hotel|alojamiento|hospedaje|lodging|accommodation|punto|dive site|llevar|bring|comida|almuerzo|"
                               r"food|lunch|precio|price|horario|schedule|hora|disponib|availab", re.I)
# discounts.json (10, 10, 5), el 20 % de online y grupo juntos (discounts.json), y el 50/50 y el 100 % de las políticas.
_PORCENTAJES_DE_LA_BASE = frozenset({5.0, 10.0, 20.0, 50.0, 100.0})


def _precios_de_pricing() -> set[tuple[float, str]]:
    """Todos los precios de `pricing.json` (14 que no están en SERVICES: el acompañante, la nocturna, la inmersión extra…)."""
    import json as _json

    datos = _json.loads((v1.RAIZ / "data" / "knowledge_base" / "pricing.json").read_text(encoding="utf-8-sig"))
    salen: set[tuple[float, str]] = set()

    def recorre(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool) and re.match(r"(usd|cop)_", k):
                    salen.add((round(float(v), 2), "USD" if k.startswith("usd") else "COP"))
                else:
                    recorre(v)
        elif isinstance(x, list):
            for v in x:
                recorre(v)
    recorre(datos)
    return salen


# El servicio de cada tipo del reparto (el de las islas, `<id>_already_on_island`). El acompañante no tiene precio propio.
_SERVICIO_DEL_TIPO = {"certified_diving": "2_dives_1_day", "minicourse": "minicourse", "bubble_makers": "bubble_makers",
                      "snorkel": "snorkeling", "padi_open_water": "open_water", "padi_open_water_referral": "referral",
                      "padi_advanced": "advanced", "padi_rescue": "rescue", "padi_divemaster": "divemaster",
                      "specialty_nitrox": "nitrox_specialty", "specialty_buoyancy": "buoyancy_specialty",
                      "specialty_naturalist": "naturalist_specialty", "specialty_fish_identification": "fish_identification_specialty",
                      "specialty_mindful_diving": "mindful_diving"}


def _del_origen(ids: list[str], origen: str | None) -> list[str]:
    """Los de su origen si se sabe (el de las islas, si existe); los dos si no."""
    servicios, salen = _servicios(), []
    for sid in ids:
        base = sid.removesuffix("_already_on_island")
        isla = f"{base}_already_on_island" if f"{base}_already_on_island" in servicios else None
        salen += [isla or base] if origen == "islas" else [base] if origen == "cartagena" else [base, *([isla] if isla else [])]
    return [s for s in dict.fromkeys(salen) if s in servicios]


def precios_permitidos(ent: dict) -> set[tuple[float, str]]:
    """Los precios del catálogo que puede dar, en la moneda que toca y de su origen: del plan si es uno solo; si el reparto tiene
    varios tipos (el grupo que bucea, hace el minicurso y snorkel), los de cada uno; si no se sabe, los de todos. Como los escribe el
    bot, también redondeados («204 USD» por 204,3)."""
    servicios, reparto = _servicios(), [t for t in (ent.get("reparto") or {}) if t in _SERVICIO_DEL_TIPO]
    buceo = [s for s in servicios if "dive" in s and "bubble" not in s]  # el buzo certificado tiene varios planes (2, 3, 4, 5, 7, 9)
    por_tipo = [x for t in reparto for x in (buceo if t == "certified_diving" else [_SERVICIO_DEL_TIPO[t]])]
    if ent.get("plan") in servicios and len(reparto) <= 1:
        ids = _del_origen([ent["plan"]], ent.get("origen"))
    elif por_tipo:
        ids = _del_origen(por_tipo, ent.get("origen"))
    else:
        ids = _del_origen(list(servicios), ent.get("origen"))
    nac = ent.get("nacionalidad")
    monedas = {"COP"} if nac in ("colombiana", "residente") else {"USD"} if nac in ("extranjera", "mixta") else {"USD", "COP"}
    import math

    precios = {(float(s[c]), m) for sid in ids for s in [servicios.get(sid) or {}]
               for c, m in (("price_usd", "USD"), ("price_usd_normal", "USD"), ("price_cop", "COP"), ("price_cop_normal", "COP"))
               if s.get(c) is not None}
    # Los de pricing.json que no son de ningún servicio (el acompañante, la nocturna…), siempre; los de los servicios siguen la regla
    # del plan y del origen (si no, «124,20 USD» de las islas pasaría a un cliente de Cartagena).
    de_servicios = {(float(s[c]), m) for s in servicios.values()
                    for c, m in (("price_usd", "USD"), ("price_usd_normal", "USD"), ("price_cop", "COP"), ("price_cop_normal", "COP"))
                    if s.get(c) is not None}
    precios |= {(v, m) for v, m in _precios_de_pricing() if not any(abs(v - w) < 0.01 and m == n for w, n in de_servicios)}
    salen = set()
    for valor, moneda in precios:
        if moneda in monedas:  # como los escribe el bot: exacto, o redondeado hacia arriba o hacia abajo («204» por 204,3)
            salen |= {(round(valor, 2), moneda), (float(math.floor(valor)), moneda), (float(math.ceil(valor)), moneda)}
    return salen


def comprobar(ent: dict, pasar: dict | None, pregunta: dict | None, texto: str, veces: dict, p1b_usado: bool) -> dict:
    """Los fallos de esta salida de Luna, por comprobación (vacío si cumple) y lo que el código tiene que poner aunque cumpla."""
    from src.domain.lugares import recogida_conocida  # lazy

    forma, motivo_asesor = decision(ent)
    fallos: dict[str, str] = {}
    pasar = pasar or {}
    quiere = bool(ent.get("quiere_reservar"))
    # C1, el pase
    if pasar.get("si"):
        motivo, tema = pasar.get("motivo"), pasar.get("tema") or ""
        acepta = {
            "reservar_con_asesor": forma == ASESOR and quiere,
            "ya_reservo": bool(ent.get("ya_reservo")),
            "salud": True, "clima_del_dia": True, "pide_persona": True, "horario": True,
            "recogida_fuera": ent.get("origen") == "islas" and bool(hotel_dicho(ent)) and not recogida_conocida(hotel_dicho(ent)),
            "origen_sin_saber": quiere and forma == ORIGEN_PRIMERO and p1b_usado,
            "la_base_no_lo_tiene": not _LA_BASE_CONTESTA.search(tema),
        }.get(motivo, False)
        if not acepta:
            fallos["C1"] = ("no lo pases: " + ("aún no quiere reservar; dile una vez, sin preguntar, que lo reserva un asesor"
                            if motivo == "reservar_con_asesor" and forma == ASESOR else
                            "eso lo contesta la base" if motivo == "la_base_no_lo_tiene" else
                            "primero el hotel (sale desde las islas)" if forma == HOTEL_PRIMERO else
                            "primero el origen" if forma == ORIGEN_PRIMERO else "no es un motivo para pasar"))
    pase_que_falta = not pasar.get("si") and quiere and (forma == ASESOR or (forma == ORIGEN_PRIMERO and p1b_usado))
    # C2, los importes
    permitidos = precios_permitidos(ent)
    malos = [(f"{v:,.0f} COP".replace(",", ".") if m == "COP" else f"{v:g} USD") for v, m in importes(texto) if (v, m) not in permitidos]
    malos += [f"{p} %" for p in _PORCENTAJE.findall(texto) if float(p.replace(",", ".")) not in _PORCENTAJES_DE_LA_BASE]
    if malos:
        fallos["C2"] = ("solo el precio por persona del catálogo, en su moneda y de su origen, sin aplicar descuentos ni sumar: "
                        + ", ".join(malos[:4]))
    # C3, el enlace
    enlaces, toca = _RESERVA.findall(texto or ""), enlace_que_toca(ent)
    sin_idioma = lambda u: re.sub(r"[?&]language=\w+", "", u or "")  # noqa: E731 — la base solo tiene los de «language=es»
    if enlaces and (forma != ENLACE or any(sin_idioma(e) != sin_idioma(toca) for e in enlaces)):
        fallos["C3"] = ("ningún enlace de reserva todavía (" + {HOTEL_PRIMERO: "primero el hotel", ORIGEN_PRIMERO: "primero el origen",
                        ASESOR: f"lo reserva un asesor: {motivo_asesor}", POSVENTA: "ya reservó"}.get(forma, "") + ")"
                        if forma != ENLACE else f"el enlace de su plan y de su origen es {toca}" if toca
                        else "ningún enlace de reserva: este plan no se reserva por la web desde su origen")
    enlace_que_falta = toca if (quiere and forma == ENLACE and toca and not enlaces) else None
    # C4, la pregunta
    n, tema_p = preguntas(texto), (pregunta or {}).get("tema")
    if n > 1:
        fallos["C4"] = "una pregunta como mucho"
    elif n == 1:
        falta = {"origen": not ent.get("origen"), "hotel": ent.get("origen") == "islas" and not hotel_dicho(ent),
                 "nacionalidad": not ent.get("nacionalidad"), "personas": not ent.get("personas"), "fecha": not ent.get("fecha"),
                 "certificado": ent.get("certificado") is None, "edades": not ent.get("edades"),
                 "refresher": ent.get("refresher") is None, "plan": not ent.get("plan")}.get(tema_p, False)
        de_la_reserva = quiere or tema_p in ("origen", "certificado", "plan")  # origen-y-precio; o pregunta precio o plan (diseño C4)
        p1b = tema_p == "origen" and quiere and veces.get("origen", 0) >= 2 and not p1b_usado
        if not (falta and de_la_reserva and (veces.get(tema_p, 0) < 2 or p1b)):
            fallos["C4"] = "contesta sin preguntar (no hace falta ningún dato para reservar ahora)"
    return {"fallos": fallos, "forma": forma, "motivo_asesor": motivo_asesor, "pase_que_falta": pase_que_falta,
            "enlace_que_falta": enlace_que_falta}


# ── 5. Lo que pone el código ──────────────────────────────────────────────────────────────────────────────────────────────────────
_TE_PASO = {"es": "Te paso con un asesor del equipo; enseguida te escribe por aquí. 🌊",
            "en": "I'm passing you to an advisor from the team; they'll write to you here shortly. 🌊"}
_PARA_RESERVAR = {"es": "👉 Para reservar: {url}", "en": "👉 To book: {url}"}
_SI_ERES_COLOMBIANO = {"es": "Si eres de nacionalidad colombiana o tienes cédula de extranjería, dímelo antes de pagar: el pago en pesos "
                             "lo coordina un asesor.",
                       "en": "If you're Colombian or hold a Colombian foreigner ID, let me know before paying: an advisor arranges "
                             "payment in pesos."}
_POR_EL_ASESOR = {"es": "Este plan lo reserva un asesor ({motivo}). Cuando quieras reservar, dímelo.",
                  "en": "An advisor books this plan for you ({motivo}). Whenever you want to book, just let me know."}
_MOTIVO_EN = {"pago en pesos": "payment in pesos", "recogida por confirmar": "the pick-up needs confirming",
              "grupo de 5 o más": "groups of 5 or more get a group discount", "una parte del plan sin enlace":
              "part of the plan can't be booked online", "el plan no tiene enlace": "it can't be booked online",
              "equipo propio": "the own-gear discount", "a nombre de otro": "it's booked in someone else's name"}


def _por_el_asesor(motivo: str | None, lang: str) -> str:
    return _POR_EL_ASESOR[lang].format(motivo=_MOTIVO_EN.get(motivo, motivo) if lang == "en" else motivo)
_SIN_ORIGEN = {"es": "Para darte el enlace necesito saber desde dónde sales: ¿desde Cartagena o ya estás en las Islas del Rosario?",
               "en": "To give you the link I need to know where you're leaving from: Cartagena, or are you already on the Rosario Islands?"}
_HOTEL = {"es": "Para reservar desde las islas necesito el nombre de tu hotel: cuando lo tengas, escríbeme y seguimos.",
          "en": "To book from the islands I need your hotel's name: once you have it, message me and we'll carry on."}


def plantilla(ent: dict, lang: str) -> str:
    """C2/C3 tras rehacer: lo del código, sin el texto de Luna (la pieza de precios del plan y la línea de la entrega). Vacío si no
    tiene nada seguro que poner: entonces se queda el texto de Luna y se cuenta (revisión del paso 5, nº 3 y nº 11)."""
    forma, motivo = decision(ent)
    servicios, lineas = _servicios(), []
    reparto = [t for t in (ent.get("reparto") or {}) if t in _SERVICIO_DEL_TIPO]
    if ent.get("plan") in servicios and len(reparto) <= 1:
        tipos = [ent["plan"]]
    else:  # el buzo certificado sin plan dicho tiene varios (2, 3, 4… inmersiones): no se adivina cuál
        tipos = [_SERVICIO_DEL_TIPO[t] for t in reparto if t != "certified_diving"]
    pesos = ent.get("nacionalidad") in ("colombiana", "residente")
    for sid in _del_origen(tipos, ent.get("origen")):
        s = servicios[sid]
        if s.get("price_usd") is None:
            continue
        nombre = s.get("name_es" if lang == "es" else "name_en") or sid
        if not ent.get("origen"):  # origen-y-precio: cada salida con su rótulo
            nombre += (" (ya en las islas)" if lang == "es" else " (already on the islands)") if sid.endswith("_already_on_island") \
                else (" (desde Cartagena)" if lang == "es" else " (from Cartagena)")
        precio = f"{s['price_cop']:,.0f} COP".replace(",", ".") if pesos else f"{round(s['price_usd'])} USD"
        lineas.append(f"• *{nombre}*: {precio} por persona (online)" if lang == "es" else f"• *{nombre}*: {precio} per person (online)")
    lineas = ["\n".join(lineas)] if lineas else []
    if not lineas:
        return ""
    if forma == ENLACE and (url := enlace_que_toca(ent)):
        lineas.append(_PARA_RESERVAR[lang].format(url=url) + ("" if ent.get("nacionalidad") else f"\n{_SI_ERES_COLOMBIANO[lang]}"))
    elif forma == ASESOR:
        lineas.append(_por_el_asesor(motivo, lang))
    elif forma == ORIGEN_PRIMERO:
        lineas.append(_SIN_ORIGEN[lang])
    elif forma == HOTEL_PRIMERO:
        lineas.append(_HOTEL[lang])
    return "\n\n".join(lineas)


# ── 6. Un cliente, turno a turno ──────────────────────────────────────────────────────────────────────────────────────────────────
# V2m (#3773, #3774): solo lo exacto rehace (C2, importes; C3, enlace). El pase (C1) y la pregunta (C4) los llevan las reglas del
# esquema y aquí solo se cuentan. V1R: el mismo esquema y las mismas reglas, sin puerta (para atribuir lo que hace cada cosa).
REHACEN = frozenset({"C2", "C3"})
_DICE_EL_PASE = re.compile(r"asesor|advisor|equipo|team|persona|person", re.I)


def _limpio(datos: dict) -> dict:
    """Lo que devuelve Luna, con los tipos que espera la puerta: una salida rara no tumba la medida (revisión del paso 5, nº 6)."""
    ent = datos.get("entendido") if isinstance(datos.get("entendido"), dict) else {}
    ent = {k: v for k, v in ent.items() if k in ENTENDIDO_VACIO}
    if not isinstance(ent.get("reparto"), dict):
        ent.pop("reparto", None)
    else:
        ent["reparto"] = {a: int(n) for a, n in ent["reparto"].items() if str(n).isdigit() and int(n) > 0}
    if "personas" in ent:
        ent["personas"] = int(ent["personas"]) if str(ent["personas"]).isdigit() else None
    if "hotel" in ent and not isinstance(ent["hotel"], str):
        ent["hotel"] = None
    pasar = datos.get("pasar") if isinstance(datos.get("pasar"), dict) else {"si": bool(datos.get("pasar"))}
    pregunta = datos.get("pregunta") if isinstance(datos.get("pregunta"), dict) else None
    # Un null nuevo no borra lo que ya entendió del origen, el hotel, la nacionalidad o el plan (revisión nº 13).
    ent = {k: v for k, v in ent.items() if v is not None or k not in ("origen", "hotel", "nacionalidad", "plan")}
    return {"entendido": ent, "pasar": pasar, "pregunta": pregunta,
            "texto": datos.get("texto") if isinstance(datos.get("texto"), str) else ""}


def _salida(clave: str, mensajes: list[dict]) -> tuple[dict | None, str, dict, str | None]:
    salida, m = v1.llamar(clave, mensajes)
    datos, fallo = v1.leer(salida)
    return (_limpio(datos) if datos is not None else None), salida, m, fallo


def cliente(clave: str, base: str, d: dict, reloj: str | None, puerta_activa: bool = True) -> list[dict]:
    sistema = v1.sistema_para(base, reloj).replace(v1.INSTRUCCIONES.replace("{base}", base), INSTRUCCIONES_V2.replace("{base}", base))
    if sistema == v1.sistema_para(base, reloj):
        raise RuntimeError("el esquema de V2 no se sustituyó: se mediría V1")
    historial = [{"role": "system", "content": sistema}]
    entendido, filas, veces = dict(ENTENDIDO_VACIO), [], {}
    p1b_usado, pasado, enlaces_dados = False, False, set()
    for i, msg in enumerate(d["turnos"], 1):
        mensajes = [*historial, {"role": "system", "content": "Lo que ya entendiste del cliente: "
                                 + json.dumps(entendido, ensure_ascii=False)}, {"role": "user", "content": msg}]
        t0, llamadas, errores, puerta, pasar, fallo = time.time(), [], 0, {}, None, None
        try:
            datos, salida, m, fallo = _salida(clave, mensajes)
            llamadas.append(m)
            if datos is None:
                texto, errores = salida, 1
            else:
                ent = {**entendido, **datos["entendido"]}
                hecho = comprobar(ent, datos["pasar"], datos["pregunta"], datos["texto"], veces, p1b_usado)
                puerta["fallos_1"] = hecho["fallos"]
                if puerta_activa and REHACEN & set(hecho["fallos"]):
                    motivo = "Corrige tu respuesta (mismo formato JSON): " + "; ".join(
                        v for k, v in hecho["fallos"].items() if k in REHACEN)
                    try:
                        datos2, salida2, m2, _ = _salida(clave, [*mensajes, {"role": "assistant", "content": salida},
                                                                  {"role": "user", "content": motivo}])
                        llamadas.append(m2)
                        puerta["rehecho"] = True
                        if datos2 is not None:
                            ent2 = {**entendido, **datos2["entendido"]}
                            hecho2 = comprobar(ent2, datos2["pasar"], datos2["pregunta"], datos2["texto"], veces, p1b_usado)
                            datos, ent, hecho = datos2, ent2, hecho2
                            puerta["fallos_2"] = hecho["fallos"]
                    except RuntimeError as exc:  # la segunda llamada falla: se queda la primera (revisión nº 12)
                        puerta["rehacer_fallo"] = str(exc)[:120]
                entendido = ent
                texto, pasar = datos["texto"], dict(datos["pasar"])
                lang = "en" if entendido.get("idioma") == "en" else "es"
                if puerta_activa:
                    if REHACEN & set(hecho["fallos"]) and (tpl := plantilla(entendido, lang)):
                        texto = tpl  # norma 5: lo del código, sin recortar el de Luna; el pase que ya era bueno se queda
                        puerta["plantilla"] = True
                        if "C1" in hecho["fallos"]:
                            pasar = {"si": False}
                    if hecho["pase_que_falta"] and not pasado:
                        pasar = {"si": True, "motivo": "reservar_con_asesor" if hecho["forma"] == ASESOR else "origen_sin_saber"}
                        if not _DICE_EL_PASE.search(texto):
                            texto = f"{texto}\n\n{_TE_PASO[lang]}"
                        puerta["pase_del_codigo"] = True
                    elif (url := hecho["enlace_que_falta"]) and url not in enlaces_dados and not pasar.get("si") \
                            and not _RESERVA.search(texto):
                        texto = f"{texto}\n\n{_PARA_RESERVAR[lang].format(url=url)}"
                        if not entendido.get("nacionalidad"):
                            texto = f"{texto}\n{_SI_ERES_COLOMBIANO[lang]}"
                        puerta["enlace_del_codigo"] = True
                enlaces_dados |= set(_RESERVA.findall(texto))
                pasado = pasado or bool(pasar.get("si"))
                tema = (datos.get("pregunta") or {}).get("tema")
                if preguntas(texto) == 1 and tema and not puerta.get("plantilla"):
                    veces[tema] = veces.get(tema, 0) + 1
                    p1b_usado = p1b_usado or (tema == "origen" and veces[tema] > 2)
        except RuntimeError as exc:
            texto, errores, fallo = f"ERROR {exc}", 1, str(exc)
            llamadas.append({"s": 0, "u": {"in": 0, "ca": 0, "out": 0}})
        except Exception as exc:  # noqa: BLE001 — un turno raro no tumba la tirada entera (revisión nº 6)
            texto, errores, fallo = f"ERROR {type(exc).__name__}: {exc}", 1, f"{type(exc).__name__}: {exc}"
            llamadas = llamadas or [{"s": 0, "u": {"in": 0, "ca": 0, "out": 0}}]
        historial += [{"role": "user", "content": msg}, {"role": "assistant", "content": texto}]
        filas.append({"dialogo": d["id"], "rep": 0, "turn": i, "msg": msg, "reply": texto, "rag": [], "juicios": [],
                      "segundos": round(time.time() - t0, 2), "estado": {"entendido": dict(entendido), "pasar": pasar,
                                                                         "puerta": puerta, "veces": dict(veces)},
                      "traza": [f"[SIMPLE] {fallo}"] if errores else [], "reloj": reloj,
                      "metricas": [{"turn_type": "simple-v2m" if puerta_activa else "simple-v1r", "llm_errores": errores,
                                    "llamadas": [{"p": "simple-v2", "m": v1.MODELO, **x} for x in llamadas]}]})
    return filas


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--banco", default="docs/robustness/caln/panel-vara.json")
    ap.add_argument("--reloj", default="alterno", help="como en reproducir_juez_pre; alterno por defecto")
    ap.add_argument("--ids", help="solo estos diálogos, separados por comas (para probar)")
    ap.add_argument("--modo", choices=("v2m", "v1r"), default="v2m",
                    help="v2m: con la puerta de lo exacto; v1r: el mismo esquema y reglas, sin puerta (#3773)")
    args = ap.parse_args(argv)
    from scripts.reproducir_juez_pre import relojes_de

    dialogos = json.loads(Path(args.banco).read_text(encoding="utf-8"))["dialogos"]
    if args.ids:
        dialogos = [d for d in dialogos if d["id"] in args.ids.split(",")]
    relojes = relojes_de([d["id"] for d in dialogos], args.reloj)
    base, clave = v1.base_del_bot(), v1._clave()
    filas: list[dict] = []
    with cf.ThreadPoolExecutor(4) as ex:
        for hecho in ex.map(lambda d: cliente(clave, base, d, relojes.get(d["id"]), args.modo == "v2m"), dialogos):
            filas += hecho
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8", newline="\n")
    puertas = [f["estado"]["puerta"] for f in filas]
    rehechos, plantillas = sum(bool(p.get("rehecho")) for p in puertas), sum(bool(p.get("plantilla")) for p in puertas)
    errores = sum(f["metricas"][0]["llm_errores"] for f in filas)
    print(f"{len(filas)} turnos de {len(dialogos)} clientes → {args.out}; rehechos {rehechos} ({100 * rehechos / max(len(filas), 1):.0f} %), "
          f"plantilla {plantillas} ({100 * plantillas / max(len(filas), 1):.1f} %); turnos con fallo {errores}")
    return 3 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
