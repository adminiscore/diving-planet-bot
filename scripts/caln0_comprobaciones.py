"""CALN-0 (27-oct, Gadea #2110): comprobaciones por código, sin LLM, sobre las conversaciones guardadas de una ronda
(`docs/robustness/synthetic-runs/<ronda>.jsonl`: mensaje del cliente y respuesta del bot por turno). Solo miran el
texto; cada una saca sus casos para revisarlos a mano.

- repregunta: el bot repite una pregunta de la reserva (origen, grupo, nacionalidad, certificación, refresher,
  actividad) DESPUÉS de que el cliente diera algo que la contesta. Se cuenta aparte la que se repite sin que el cliente
  dijera nada que la conteste (eso puede ser correcto).
- grupo: la tarjeta cotiza «N × precio» con un N distinto del último número de personas que dijo el cliente.
- moneda: el cliente dijo que es colombiano (o residente) y la tarjeta va en USD, o que no lo es y va en COP.
- origen: la respuesta da un precio de UN solo origen (Cartagena o las islas) sin que el cliente haya dicho desde
  dónde sale.

CALN-6 paso 0 (27-oct, decisión de Gadea: un compositor al final del turno), la composición de cada respuesta:
- repite: dice lo mismo dos veces (la misma pregunta pegada dos veces, la misma nota con otras palabras). No cuentan
  las líneas de la tarjeta ni dos frases con cifras distintas.
- dos_preguntas: dos o más párrafos que acaban en pregunta.
- menu_con_plan: el menú genérico de actividades en una respuesta que ya da precios o un plan.
- frase_cortada: una línea larga que se queda sin acabar (el tope del escritor).

    python scripts/caln0_comprobaciones.py docs/robustness/synthetic-runs/2026-10-26-integra5-B.jsonl [otra.jsonl ...]
    python scripts/caln0_comprobaciones.py --casos grupo ronda.jsonl      # los casos de una comprobación

Sin red ni OpenAI. Las listas de palabras son de la MEDIDA, no del bot: si una falla, se ve en los casos.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("*", "")


# Las preguntas de la reserva tal como las escribe el bot (las más frecuentes de integra5-B), por dato.
PREGUNTAS = {
    "origen": r"desde donde saldria|saldria[ns]? desde cartagena|sales? desde cartagena|departing from|leave from cartagena",
    "grupo": r"para cuantas personas|how many people",
    "nacionalidad": r"nacionalidad colombiana|colombian nationals?\b.*cedula|cedula de extranjeria\?",
    "certificacion": r"eres buzo certificado|son buzos certificados|are you a certified diver|are you certified divers",
    "refresher": r"mas de 2 anos desde|more than 2 years since",
    "actividad": r"con cual te animas|which one are you leaning|que te gustaria vivir|what would you like to experience",
}
# Lo que el cliente dice que contesta cada pregunta (laxo a propósito: la repregunta «tras contestar» es la grave).
RESPUESTAS = {
    "origen": r"cartagena|isla|islands?|rosario|baru|hotel|hostal|hospedad|alojad|staying",
    "grupo": r"\b\d+\b|somos|seremos|vamos|solo yo|yo sol[oa]|just me|only me|myself|pareja|esposa|esposo|novi[oa]|"
             r"amig[oa]|familia|people|persons|we are|we're|couple|wife|husband|friend",
    "nacionalidad": r"colombian|extranjer|foreign|cedula|residente|resident|pasaporte|passport|nacionalidad|nationality|"
                    r"\bde (usa|estados unidos|mexico|espana|canada|argentina|chile|peru|francia|alemania)\b",
    "certificacion": r"certific|open water|advanced|padi|ssi|buzo|diver|carne|nunca|never|primera vez|first time",
    "refresher": r"\b\d+\s*(anos?|years?|meses|months?)\b|\bhace\b|\bago\b|recien|recently|ultima|\blast\b|\bno\b|\bsi\b|\byes\b",
    "actividad": r"buce|dive|diving|minicurso|mini.?course|snorkel|curso|course|open water|advanced|bautismo",
}
_NUMEROS = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
            "nueve": 9, "diez": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10}
_N = r"(\d{1,2}|" + "|".join(_NUMEROS) + r")"
_GRUPO_DICHO = [
    (re.compile(r"\b(?:somos|seremos|vamos|we are|we're)\s+(?:una pareja|a couple|pareja|couple)\b"), 2),
    (re.compile(rf"\b(?:somos|seremos|vamos|seriamos|we are|we're|there are|there will be)\s+{_N}\b"
                r"(?!\s+(?:pareja|couple|familia|family|grupo|group))"), None),
    (re.compile(rf"\b{_N}\s+(?:personas|persons|people|pax|adultos|adults)\b"), None),
    (re.compile(rf"\bpara\s+{_N}\b(?!\s*(?:de|dias|days|noches|nights|inmersiones|dives|buceos|am|pm|:))"), None),
    (re.compile(r"\b(?:solo yo|yo solo|yo sola|voy solo|voy sola|just me|only me|by myself|solo para mi)\b"), 1),
    (re.compile(r"\b(?:mi esposa y yo|mi esposo y yo|mi novia y yo|mi novio y yo|my wife and i|my husband and i|"
                r"mi pareja y yo|my partner and i)\b"), 2),
]
_TARJETA_N = re.compile(r"(\d{1,2})\s*[×x]\s*[\d.,]+\s*(cop|usd)", re.I)
_TARJETA_MONEDA = re.compile(r"=\s*\*?[\d.,]+\s*(cop|usd)\b|💰[^\n]*?\b(cop|usd)\b", re.I)
_COLOMBIANO_SI = re.compile(r"\b(?:soy|somos|son|es|i'?m|we'?re|we are)\s+(?:de nacionalidad\s+)?colombian[oa]s?\b|"
                            r"\bsomos de colombia\b|\btengo cedula\b|\btenemos cedula\b|\bcedula de extranjeria\b|"
                            r"\bsoy residente\b|\bsomos residentes\b")
_COLOMBIANO_NO = re.compile(r"\bno (?:soy|somos|son) colombian[oa]s?\b|\bnot colombian\b|\bextranjer[oa]s?\b|"
                            r"\bforeigners?\b|\bno tenemos cedula\b|\bno tengo cedula\b|\bnone of us (?:is|are) colombian\b")
# Un grupo con varias actividades («2 bucean certificados, 2 hacen minicurso y 2 snorkel»): la tarjeta va por actividad.
_REPARTO = re.compile(r"\b\d{1,2}\s+(?:bucea|hace|haran|van|quieren|snorkel|minicurso|certificad|buzos?|divers?|"
                      r"do|will|want|para\s+(?:buceo|snorkel|minicurso))")
_MIXTA = re.compile(r"\bunos\b.*\botros\b|\bmixt|\balgunos\b|\bsome of us\b|\bone of us\b|\buno de nosotros\b|"
                    r"\bmi (?:esposa|esposo|novia|novio|pareja) (?:es|no es)\b")
_PRECIO = re.compile(r"\b\d{1,3}(?:[.,]\d{3})+\s*(?:cop|pesos)\b|\b(?:usd|us\$|\$)\s*\d+|\b\d+\s*(?:usd|dolares|dollars)\b")
_ORIGEN_CARTAGENA = re.compile(r"desde (?:el muelle|cartagena)|from cartagena|saliendo de cartagena")
_ORIGEN_ISLAS = re.compile(r"desde las islas|ya en las islas|en las islas|ya estas en las islas del rosario|"
                           r"from the islands|already on the islands|already on the rosario islands|on the islands")
_ORIGEN_DICHO = re.compile(r"cartagena|isla|islands?|rosario|baru|hotel|hostal|hospedad|alojad|staying|bocagrande|"
                           r"getsemani|ciudad amurallada|walled city")


# CALN-6 paso 0 (27-oct, decisión de Gadea: un compositor al final del turno): la composición de cada respuesta.
_LINEA_DE_TARJETA = ("✅", "💰", "📍", "🤿", "👉", "🐠", "📅", "🎓", "•", "-", "_", "*")
_MENU_GENERICO = re.compile(r"con cual te animas\W+buceo|que te gustaria vivir con nosotros|which one are you leaning toward"
                            r"\W+diving|what would you like to experience with us")
_FIN_DE_LINEA = re.compile(r"[.!?…:)\]»\"][*_]*\s*$|[\U0001F000-\U0001FAFF☀-➿]\s*$")
_PREGUNTA_AL_FINAL = re.compile(r"\?[*_]*\s*[\U0001F000-\U0001FAFF☀-➿]?\s*$")
_SALTO = "\n"
_PARRAFO = "\n\n"
_BURBUJA = "\n---\n"


def _frases_de_texto(respuesta: str) -> list[str]:
    """Las frases largas del texto, sin las líneas de la tarjeta ni los enlaces."""
    frases = []
    for linea in respuesta.replace(_BURBUJA, _SALTO).split(_SALTO):
        if linea.strip().startswith(_LINEA_DE_TARJETA) or "http" in linea:
            continue
        frases += [f.strip() for f in re.split(r"(?<=[.!?])\s+", linea) if len(f.strip()) > 40]
    return frases


def _dice_lo_mismo(a: str, b: str) -> bool:
    """Dos frases con las mismas cifras y casi las mismas palabras."""
    if re.findall(r"\d[\d.,]*", a) != re.findall(r"\d[\d.,]*", b):
        return False
    pa, pb = (set(re.sub(r"[^a-z0-9 ]", " ", _plano(x)).split()) for x in (a, b))
    return len(pa & pb) / max(1, min(len(pa), len(pb))) >= 0.8


def composicion(respuesta: str) -> dict[str, str]:
    """Los fallos de composición de UNA respuesta: {comprobación: el trozo que lo muestra}."""
    fallos = {}
    frases = _frases_de_texto(respuesta)
    repetida = next((frases[i] for i in range(len(frases)) for j in range(i + 1, len(frases))
                     if _dice_lo_mismo(frases[i], frases[j])), None)
    if repetida:
        fallos["repite"] = repetida[:120]
    parrafos = [p.strip() for p in respuesta.replace(_BURBUJA, _PARRAFO).split(_PARRAFO) if p.strip()]
    preguntas = [p.split(_SALTO)[-1] for p in parrafos if _PREGUNTA_AL_FINAL.search(p.split(_SALTO)[-1])]
    if len(preguntas) >= 2:
        fallos["dos_preguntas"] = " || ".join(p[-70:] for p in preguntas)
    if _MENU_GENERICO.search(_plano(respuesta)) and _PRECIO.search(_plano(respuesta)):
        fallos["menu_con_plan"] = "menú genérico en una respuesta con precio"
    for p in parrafos:
        ultima = p.split(_SALTO)[-1].strip()
        if (len(ultima) > 60 and "http" not in ultima and not ultima.startswith(_LINEA_DE_TARJETA)
                and not _FIN_DE_LINEA.search(ultima)):
            fallos["frase_cortada"] = ultima[-80:]
            break
    return fallos


def _grupo_dicho(texto: str) -> int | None:
    t = _plano(texto)
    for patron, fijo in _GRUPO_DICHO:
        m = patron.search(t)
        if m:
            if fijo is not None:
                return fijo
            n = m.group(1)
            return int(n) if n.isdigit() else _NUMEROS.get(n)
    return None


def _contesta(dato: str, mensaje: str) -> bool:
    """¿El mensaje da algo que contesta la pregunta de `dato`? Lo que el cliente pregunta («¿qué hoteles
    recomiendan?») no contesta nada; el grupo, solo con un número de personas dicho."""
    if "?" in mensaje:
        return False
    if dato == "grupo":
        return _grupo_dicho(mensaje) is not None
    plano = _plano(mensaje)
    if dato == "refresher" and len(plano.split()) > 4:
        # Un «sí» o un «no» suelto contesta; dentro de una frase larga («no sé cómo se haga la reserva»), no.
        plano = re.sub(r"\b(?:no|si|yes)\b", " ", plano)
    return bool(re.search(RESPUESTAS[dato], plano))


def _preguntas(respuesta: str) -> set[str]:
    """Los datos que pregunta la respuesta, solo dentro de las frases que acaban en «?» («¡Perfecto, sales desde
    Cartagena!» no pregunta el origen)."""
    frases = " | ".join(re.findall(r"[^.!?\n|]*\?", _plano(respuesta)))
    return {dato for dato, patron in PREGUNTAS.items() if re.search(patron, frases)}


# CALN-3 paso 0 (27-oct): los importes de la respuesta, contra el catálogo. Cada importe se busca en las tarifas de los
# servicios (`RAW_SERVICES`, con su origen por la ruta de la tarifa); el formato es el del bot («630.000 COP», «655,000
# COP», «178 USD»). Lo que no está en el catálogo (descuentos calculados, el hotel) no se juzga.
_IMPORTE = re.compile(r"(\d{1,3}(?:[.,]\d{3})+|\d{2,4})\s*(cop|usd)\b", re.I)
_CLIENTE_ISLAS = re.compile(r"sin (?:ir|salir|pasar) (?:de|por) cartagena|en las islas|en la isla|isla grande|"
                            r"ya estamos? en|on the islands?|majagua|cocoliso|nos quedamos en el hotel|quedarnos en las islas")
_CLIENTE_CARTAGENA = re.compile(r"(?:desde|de) cartagena|en cartagena|from cartagena|in cartagena|el continente")
_CATALOGO: dict[tuple[str, int], set[str]] | None = None
_PLANES: dict[tuple[str, int], set[str]] = defaultdict(set)


def plan_de(servicio: str) -> str:
    """El plan sin el origen: «minicourse_already_on_island» → «minicourse»."""
    return servicio.removesuffix("_already_on_island")


def _catalogo() -> dict[tuple[str, int], set[str]]:
    """(moneda, importe) -> orígenes del catálogo con ese precio (online y normal). Los planes, en `_PLANES`."""
    global _CATALOGO
    if _CATALOGO is None:
        from src.flows.catalog import (  # lazy: el resto del script no lo necesita
            RAW_SERVICES,
            fila_de_la_tarifa,
        )

        _CATALOGO = defaultdict(set)
        for sid, servicio in RAW_SERVICES.items():
            ruta = servicio.get("tarifa")
            if not ruta:
                continue
            origen = "cartagena" if ruta.startswith("from_cartagena") else "islas"
            fila = fila_de_la_tarifa(ruta)
            for clave in ("cop_normal", "cop_online", "usd_normal", "usd_online"):
                valor = fila.get(clave)
                if not valor:
                    continue
                # Los USD con decimales (544,5) el bot los redondea a uno u otro lado.
                for entero in {int(valor), round(valor), -int(-valor // 1)}:
                    _CATALOGO[(clave[:3], entero)].add(origen)
                    _PLANES[(clave[:3], entero)].add(plan_de(sid))
    return _CATALOGO


def planes_y_origenes(respuesta: str) -> tuple[set[str], set[str], set[str]]:
    """(planes, orígenes, monedas) de los importes del catálogo que trae la respuesta."""
    catalogo = _catalogo()
    planes, origenes, monedas = set(), set(), set()
    for m, n, _ in _importes(respuesta):
        if (m, n) in catalogo:
            planes |= _PLANES[(m, n)]
            origenes |= catalogo[(m, n)]
            monedas.add(m)
    return planes, origenes, monedas


def _importes(texto: str) -> list[tuple[str, int, str]]:
    """(moneda, importe, línea) de cada importe del texto."""
    salida = []
    for linea in (texto or "").splitlines():
        for cifra, moneda in _IMPORTE.findall(linea):
            salida.append((moneda.lower(), int(re.sub(r"[.,]", "", cifra)), linea))
    return salida


def _precios(respuesta: str, origen: str | None, colombiano: bool | None, mixta: bool) -> dict[str, dict]:
    """Los fallos de precio de UNA respuesta: origen o moneda contrarios a lo dicho, total del grupo en el texto."""
    catalogo, fallos = _catalogo(), {}
    importes = _importes(respuesta)
    del_catalogo = [(m, n, catalogo[(m, n)]) for m, n, _ in importes if (m, n) in catalogo]
    if origen and del_catalogo and all(origen not in origenes for _, _, origenes in del_catalogo):
        fallos["precio_origen"] = {"dicho": origen, "importes": [f"{n} {m.upper()}" for m, n, _ in del_catalogo][:4]}
    monedas = {m for m, _, _ in del_catalogo}
    if colombiano is not None and not mixta and len(monedas) == 1:
        if monedas == ({"usd"} if colombiano else {"cop"}):
            fallos["precio_moneda"] = {"colombiano": colombiano, "moneda": monedas.pop()}
    for m, n, linea in importes:
        # Decisión A1 (Gadea, 9-oct): en el texto, precio por persona; solo la tarjeta multiplica («2 × 178 USD»).
        if "×" in linea or "x " in linea.lower() or (m, n) in catalogo:
            continue
        unidad = next((k for k in range(2, 21) if n % k == 0 and (m, n // k) in catalogo), None)
        if unidad:
            fallos["total_en_texto"] = {"importe": f"{n} {m.upper()}", "personas": unidad}
            break
    return fallos


def comprobar(conversacion: list[dict]) -> dict[str, list[dict]]:
    """Los fallos de UNA conversación (sus turnos en orden), por comprobación."""
    fallos: dict[str, list[dict]] = defaultdict(list)
    preguntado: dict[str, int] = {}  # dato -> turno en que el bot lo preguntó por última vez
    grupo, colombiano, mixta, origen_dicho = None, None, False, False
    origen_cliente = None  # el último origen que dijo el cliente, si dijo uno solo en su mensaje
    for i, turno in enumerate(conversacion):
        mensaje, respuesta = turno.get("msg") or "", turno.get("reply") or ""
        m = _plano(mensaje)
        # Lo que el cliente dice en ESTE mensaje cuenta para la respuesta de este turno.
        dicho = _grupo_dicho(mensaje)
        grupo = dicho if dicho is not None else grupo
        if _COLOMBIANO_NO.search(m):
            colombiano = False
        elif _COLOMBIANO_SI.search(m):
            colombiano = True
        mixta = mixta or bool(_MIXTA.search(m)) or len(_REPARTO.findall(m)) >= 2
        origen_dicho = origen_dicho or bool(_ORIGEN_DICHO.search(m))
        if "?" not in mensaje:  # lo que pregunta («¿y desde Cartagena?») no es su origen
            islas, cartagena = bool(_CLIENTE_ISLAS.search(m)), bool(_CLIENTE_CARTAGENA.search(m))
            if islas and m.count("cartagena") <= 1 and re.search(r"sin (?:ir|salir|pasar)", m):
                cartagena = False  # «sin ir de Cartagena» = las islas
            if islas != cartagena:
                origen_cliente = "islas" if islas else "cartagena"
        r = _plano(respuesta)
        caso = {"turno": turno.get("turn"), "msg": mensaje[:160], "reply": respuesta[:400]}
        # repregunta
        for dato in _preguntas(respuesta):
            if dato in preguntado:
                contestado = any(_contesta(dato, conversacion[j].get("msg") or "")
                                 for j in range(preguntado[dato] + 1, i + 1))
                fallos["repregunta" if contestado else "repite_sin_respuesta"].append({**caso, "dato": dato})
            preguntado[dato] = i
        # grupo
        for n in {int(x) for x, _ in _TARJETA_N.findall(respuesta)}:
            if grupo is not None and n != grupo and not mixta:
                fallos["grupo"].append({**caso, "dicho": grupo, "tarjeta": n})
        # moneda
        monedas = {(a or b).lower() for a, b in _TARJETA_MONEDA.findall(respuesta)}
        if colombiano is not None and not mixta and len(monedas) == 1:
            if (colombiano and monedas == {"usd"}) or (not colombiano and monedas == {"cop"}):
                fallos["moneda"].append({**caso, "colombiano": colombiano, "moneda": monedas.pop()})
        # origen
        if _PRECIO.search(r) and not origen_dicho:
            cartagena, islas = bool(_ORIGEN_CARTAGENA.search(r)), bool(_ORIGEN_ISLAS.search(r))
            if cartagena != islas:
                fallos["origen"].append({**caso, "origen": "cartagena" if cartagena else "islas"})
        # precios (CALN-3 paso 0)
        for comp, detalle in _precios(respuesta, origen_cliente, colombiano, mixta).items():
            fallos[comp].append({**caso, **detalle})
        # composición (CALN-6)
        for comp, muestra in composicion(respuesta).items():
            fallos[comp].append({**caso, "muestra": muestra})
    return fallos


COMPROBACIONES = ("repregunta", "repite_sin_respuesta", "grupo", "moneda", "origen",
                  "precio_origen", "precio_moneda", "total_en_texto",
                  "repite", "dos_preguntas", "menu_con_plan", "frase_cortada")


def conversaciones(ruta: Path) -> dict[str, list[dict]]:
    por_conv: dict[str, list[dict]] = defaultdict(list)
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            # Una ronda (tag/conv) o un banco de `reproducir_juez_pre` (dialogo/rep).
            nombre, conv = fila.get("tag") or fila.get("dialogo"), fila.get("conv", fila.get("rep"))
            por_conv[f"{nombre}#{conv}"].append(fila)
    return {k: sorted(v, key=lambda f: f.get("turn") or 0) for k, v in por_conv.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rondas", nargs="+", type=Path)
    parser.add_argument("--casos", choices=COMPROBACIONES, help="Lista los casos de esa comprobación.")
    args = parser.parse_args()
    print(f"{'ronda':34} {'convs':>5} {'turnos':>6}  " + "  ".join(f"{c:>20}" for c in COMPROBACIONES))
    for ruta in args.rondas:
        convs = conversaciones(ruta)
        total: dict[str, list] = defaultdict(list)
        for nombre, turnos in convs.items():
            for comp, casos in comprobar(turnos).items():
                total[comp].extend({"conv": nombre, **c} for c in casos)
        turnos = sum(len(t) for t in convs.values())
        celdas = [f"{len(total[c]):>4} en {len({x['conv'] for x in total[c]}):>3} conv" for c in COMPROBACIONES]
        print(f"{ruta.stem:34} {len(convs):>5} {turnos:>6}  " + "  ".join(f"{c:>20}" for c in celdas))
        if args.casos:
            for c in total[args.casos]:
                extra = {k: v for k, v in c.items() if k not in ("conv", "turno", "msg", "reply")}
                print(f"\n  {c['conv']} t{c['turno']} {extra}\n    cliente: {c['msg']!r}\n    bot: {c['reply']!r}")


if __name__ == "__main__":
    main()
