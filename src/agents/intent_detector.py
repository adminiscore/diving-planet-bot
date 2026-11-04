import re
from dataclasses import dataclass, field
from functools import lru_cache

from src.domain import activities as dom
from src.domain.lugares import hotel_nombrado, isla_nombrada
from src.utils.number_words import number_alt, number_words
from src.utils.text import strip_accents


@dataclass
class DetectedIntent:
    language: str | None = None
    activity: str | None = None
    service_id: str | None = None
    is_certified: bool | None = None
    group_size: int | None = None
    group_allocation: dict[str, int] | None = None
    last_dive_over_2_years: bool | None = None
    duration: str | None = None
    location: str | None = None
    island: str | None = None
    hotel: str | None = None
    ages: list = field(default_factory=list)   # person ages mentioned in the message
    cert_dives: int | None = None              # explicit dive-count requested for certified diving ("2 inmersiones", "paquete de 5 buceos")
    cert_days: int | None = None               # explicit day-count requested instead ("paquete de 3 dias")
    is_colombian: bool | None = None           # nationality stated in the message (COP vs USD)
    # True ONLY from the narrow, strictly-guarded "solo yo"/"just me"/singular
    # self-identification match below (never from a plain numeric "1" answer
    # or a companion-quantity chain resolving to 1) — see hallazgo en vivo,
    # batería de grupos mixtos contra PRE, 2026-09-01, lote 8, en
    # conversational_core.py donde se consume.
    solo_confirmed: bool = False
    # Campos que este turno puede SOBRESCRIBIR aunque el estado ya los tenga: una
    # correccion aceptada (con cue explicito o confirmada por el cliente). Lo decide
    # `conversational_core._route_contradictions` (tarea 7b, 2026-09-15).
    overwrite: list = field(default_factory=list)   # lista, no set: el estado se guarda en JSON
    confidence: float = 0.0
    detected_fields: list = field(default_factory=list)


# Explicit certified dive-count: "2 inmersiones", "paquete de 5 buceos",
# "7 buceos en 3 dias", "2-dive package". The number must sit right before a
# dive noun so "hace 2 años sin bucear" (a timeframe, not a count) never matches.
_DIVE_NUMBER = r"(\d+|" + number_alt(1, 9) + r"|un)"
# "4 o 5 inmersiones" nombra dos paquetes: la cifra coordinada tambien se captura para
# no quedarse con una sola y dar por elegido lo que el cliente aun duda (2026-09-15).
_CERT_DIVE_COUNT_RE = re.compile(
    r"\b" + _DIVE_NUMBER + r"(?:\s*(?:,|o|u|y|or|and)\s*" + _DIVE_NUMBER + r")?"
    r"[\s\-]+(?:inmersi\w+|buceos?|dives?|immersions?)\b",
    re.IGNORECASE,
)
_DIVE_WORD_TO_NUM = {**number_words(1, 9), "un": 1}

# Bare "paquete/pack/plan de N" with NO unit word at all ("el pack de 5") —
# found live on PRE 2026-07-09: a customer who'd already said "queremos
# bucear" and named a bare package number got asked "¿qué idea tienes?" again,
# forgetting the 5 they'd just given. Only resolved as a DIVE count for
# 5/7/9 — those numbers are never valid as a day-count (max day package is 4
# days), so they're unambiguous even without "inmersiones"/"buceos". 2/3/4 are
# deliberately excluded: those ARE valid as either a dive count or a day
# count ("el pack de 3" could mean 3 dives or 3 days = 7 dives), so guessing
# would risk booking the wrong plan — falls through to the normal "which
# idea" question instead. Excludes a trailing "día(s)" so "paquete de 3 dias"
# still resolves as a DAY count via _CERT_DAY_COUNT_RE, not hijacked here.
#
# Los tamanos ya no se escriben aqui (2026-09-15): cualquier cifra casa y
# `dive_counts_in` se queda solo con los paquetes del catalogo que no pueden ser un
# numero de dias (hoy 5/7/9). Un paquete nuevo del catalogo se lee sin tocar el regex.
_BARE_PACKAGE_DIVE_RE = re.compile(
    r"\b(?:paquete|pack|plan)\s+de\s+" + _DIVE_NUMBER + r"\b(?!\s*d[ií]as?)"
    r"|\b(?:package|pack|plan)\s+of\s+" + _DIVE_NUMBER + r"\b(?!\s*days?)",
    re.IGNORECASE,
)

# Explicit day-count for a multi-day certified package: "paquete de 3 dias",
# "3 dias de buceo", "3-day package", EN "a two-day package"/"3 days diving".
# Unlike dive-count, a bare "3 dias"/"3 days" is too generic to trust on its
# own (it also means "in 3 days" / "3 days ago"), so this only matches next to
# a diving/package qualifier. Word-form numbers cover both languages (ES "un"/
# "dos"/"tres"/"cuatro", EN "one"/"two"/"three"/"four") so "a two-day package"
# resolves the same as "2-day package" — found missing (ES-only) 2026-07-09.
# "pack" added to the qualifier list 2026-07-09 (was missing entirely —
# "el pack de 3 dias" didn't match "paquete"/"plan").
# Dias en palabra hasta el paquete mas largo del catalogo (hoy 4).
_MAX_PACKAGE_DAYS = max(days for days, _ in dom.dive_packages().values())
_CERT_DAY_COUNT_RE = re.compile(
    r"\b(?:paquete|pack|plan)\s+de\s+(\d+|" + number_alt(1, _MAX_PACKAGE_DAYS, "es") + r"|un)\s*d[ií]as?\b"
    r"|\b(\d+|" + number_alt(1, _MAX_PACKAGE_DAYS, "es") + r"|un)[\s\-]+d[ií]as?\s+(?:de\s+)?buce\w*\b"
    r"|\b(\d+|" + number_alt(1, _MAX_PACKAGE_DAYS, "en") + r")[\s\-]?days?\s+(?:of\s+)?(?:dive\s+|diving\s+)?package\b"
    r"|\b(\d+|" + number_alt(1, _MAX_PACKAGE_DAYS, "en") + r")[\s\-]?days?\s+(?:of\s+)?div(?:e|ing)\b",
    re.IGNORECASE,
)


# ── Cuanto dura la estancia ────────────────────────────────────────────────
# Hueco 2 (2026-09-16): eran dos listas de fraseos ("un dia", "varios dias", "\d+ days",
# "staying \d+ days"...), asi que "estaremos toda la semana en las islas", "tres dias" o
# "just here for the day" no se leian y el bot volvia a preguntar. Ahora se compone con las
# piezas que ya hay: la CANTIDAD multiplica los dias de la UNIDAD y el total decide (1 dia
# -> single_day, mas -> multi_day). Las noches se quedan fuera a proposito: "una noche" no
# dice cuantos dias se bucea, y suponerlo seria dar por hecho lo que el cliente no dijo.
# "d[ií]a(s)" tolera el "dias"/"dia" sin tilde, muy comun al escribir desde el movil.
_DURATION_UNITS = (
    (r"d[ií]as?", 1), (r"days?", 1),
    (r"fin(?:es)?\s+de\s+semana", 2), (r"weekends?", 2),
    (r"semanas?", 7), (r"weeks?", 7),
    (r"mes(?:es)?", 30), (r"months?", 30),
)
_DURATION_QTY_WORDS = {
    **number_words(1, 19), "un": 1, "unos": 3, "unas": 3, "par": 2, "couple": 2,
    "varios": 3, "varias": 3, "several": 3, "few": 3, "a": 1, "an": 1,
}
_DURATION_QTY = r"\d+|" + "|".join(sorted(_DURATION_QTY_WORDS, key=len, reverse=True))
# Palabras que pueden ir entre la cantidad y la unidad sin cambiarla: "un SOLO dia",
# "un par DE dias", "a couple OF days", "a FULL day".
_DURATION_FILLER = r"(?:\s+(?:de|of|solo|s[oó]lo|solamente|only|just|full))*"
_DURATION_RES = tuple(
    (
        re.compile(
            r"\b(?:"
            # La unidad entera, sin cantidad: "toda la semana", "the whole weekend". El
            # articulo va delante en ingles y detras en espanol.
            r"(?:(?:el|la|the)\s+)?(?:tod[oa]|all|whole|entire)(?:\s+(?:el|la|the))?\s+"
            # "por el dia", "for the day": el articulo vale por la unidad entera solo tras
            # una preposicion de duracion, para que un "el dia" suelto (una fecha, "que dia
            # salen") no cuente.
            r"|(?:por|durante|for|in)\s+(?:el|la|the)\s+"
            r"|(?P<qty>" + _DURATION_QTY + r")" + _DURATION_FILLER + r"\s+"
            r")(?:" + unit + r")\b",
            re.IGNORECASE,
        ),
        unit_days,
    )
    for unit, unit_days in _DURATION_UNITS
)
# Tiempo transcurrido, no estancia: "hace 3 dias que llegamos", "3 days ago". Marcadores
# de clase cerrada, a los dos lados de la cantidad.
_ELAPSED_BEFORE_RE = re.compile(r"\bhace(?:\s+(?:como|casi|ya|m[aá]s|menos|de))*\s+$", re.IGNORECASE)
_ELAPSED_AFTER_RE = re.compile(r"^\s*(?:ago|atr[aá]s|antes)\b", re.IGNORECASE)
# Un paquete es multi-dia por definicion: cuenta como el mas largo del catalogo.
_MULTI_DAY_PRODUCT_RE = re.compile(r"\b(?:paquete|package|multi[-\s]?day)\b", re.IGNORECASE)
_TODAY_ONLY_RE = re.compile(r"\b(?:solo|s[oó]lo|solamente)\s+hoy\b|\bjust\s+today\b", re.IGNORECASE)


def _duration_span(match: re.Match, unit_days: int) -> int:
    """Dias que ocupa la duracion leida. Sin cantidad ("toda la semana", "for the day")
    la unidad va entera; con cantidad, la multiplica."""
    qty = match.group("qty")
    if not qty:
        return unit_days
    return (int(qty) if qty.isdigit() else _DURATION_QTY_WORDS[qty.lower()]) * unit_days


def _is_elapsed_time(message: str, match: re.Match) -> bool:
    """¿La duracion cuenta tiempo transcurrido en vez de la estancia? "hace 3 dias que
    llegamos" o "3 days ago" no dicen cuanto se quedan."""
    return bool(
        _ELAPSED_BEFORE_RE.search(message[:match.start()])
        or _ELAPSED_AFTER_RE.search(message[match.end():])
    )


# ── Gate de TEMA del detector de última inmersión ──────────────────────────
# Aquí vivían también los gates de tema de certificación y nacionalidad que
# usaba el núcleo para aceptar o no un booleano del LLM. Se retiraron el
# 2026-09-14: descartaban el valor correcto en todo lo que su vocabulario no
# conocía ("soy paisa", "tengo el AOWD"). Los decidió después la estructura
# del turno (`_boolean_patch_is_anchored`, borrada en ex-9b: hoy los decide el
# extractor del turno).


def detect_cert_dive_count(message: str) -> int | None:
    """Requested certified dive-count as a real package size (2/3/4/5/7/9), or None.
    Shared by the intent detector and the cart's cert-plan step so a natural-language
    "2 buceos" is understood in both places."""
    counts = dive_counts_in(message)
    return counts[0] if len(counts) == 1 else None


def _dive_number(token: str) -> int | None:
    token = token.lower()
    return int(token) if token.isdigit() else _DIVE_WORD_TO_NUM.get(token)


def dive_counts_in(message: str, tamanos=None) -> list[int]:
    """Tamanos de paquete reales que nombra el texto, en orden y sin repetir. Unica
    lectura de "N inmersiones" para el detector, el nucleo (paquete que describio el
    bot) y el RAG (precio). Los tamanos salen del catalogo (`dom.dive_packages`). Un
    "paquete de N" sin unidad solo cuenta si N no puede ser un numero de dias.
    `tamanos` (ex-9b paso 4): los que valen, si no son los paquetes (el plan nombrado del
    RAG usa los planes del origen del cliente, con la inmersion suelta de las islas)."""
    packages = dom.dive_packages()
    day_counts = {days for days, _ in packages.values()}
    validos = set(packages) if tamanos is None else set(tamanos)
    counts = [
        _dive_number(token)
        for match in _CERT_DIVE_COUNT_RE.finditer(message or "")
        for token in match.groups() if token
    ]
    counts += [
        n for match in _BARE_PACKAGE_DIVE_RE.finditer(message or "")
        for n in (_dive_number(token) for token in match.groups() if token)
        if n not in day_counts
    ]
    return list(dict.fromkeys(n for n in counts if n in validos))


def detect_cert_day_count(message: str) -> int | None:
    """Requested certified package duration in days (1/2/3/4), inferred from
    explicit day-count phrasing rather than a dive count. None if absent/
    unrecognized. Shared by the intent detector and the cart's cert-plan step."""
    match = _CERT_DAY_COUNT_RE.search(message or "")
    if not match:
        return None
    n = _dive_number(next(g for g in match.groups() if g is not None))
    return n if n in {days for days, _ in dom.dive_packages().values()} else None


# Edades en PALABRA (2026-07-24, opción A del análisis del gate age-eligibility).
# Mapa 2-19 (edades de menores relevantes para buceo/snorkel); 1 se excluye a
# propósito ("una niña" es artículo, no edad, y nadie de 1 año bucea). Canónico
# aquí (módulo de más bajo nivel); `conversational_core` lo importa para su
# propio parseo de SLOT_AGES, sin duplicar. Cierre DETERMINISTA — nunca adivina
# una edad (a diferencia del cutover LLM que H4 difirió: en una decisión de
# seguridad, adivinar "es adolescente"->15 es peor que no responder).
AGE_WORDS = number_words(2, 19)
# Alternación ordenada por longitud desc (así "dieciseis" gana a "diez" en el
# motor regex antes de que un prefijo corte el match).
_AGE_WORD_ALT = number_alt(2, 19)


# Listas de patrones por categoria de actividad — elevadas de variables locales
# de `_detect_activity` a constantes de modulo (2026-09-03, hallazgo en vivo
# conversacion real "purple-sun-590", docs/multi-agent-refactor-plan.md) para
# que `matched_activity_categories()` pueda reusarlas SIN duplicar ningun
# regex ni cambiar su contenido/orden. `_detect_activity` sigue resolviendo
# con la misma cadena if/elif de siempre (primera categoria que matchea
# gana) -- esto no toca esa logica, solo la hace visible desde fuera para
# detectar cuando un mensaje dispara 2+ categorias a la vez (ambiguedad
# real, candidata a veto LLM en supervisor.py).
_CERTIFIED_DIVING_PATTERNS = [
    r'\bbuce\w{0,5}\b(?!\s+(bautismo|principiante|primera\s+vez|minicurso))',  # buceo, bucear, bucereo, buceando
    r'\bbuse[ao]\w{0,2}\b',        # buseo (common u/c swap typo)
    # vuce* (common b/v swap typo — real bug live 2026-07-21: "ella no
    # vucea" wasn't recognized as diving at all, fell through to RAG,
    # which rejected it as a hallucination and gave the advisor
    # fallback instead of entering the booking flow).
    r'\bvuce\w{0,5}\b(?!\s+(bautismo|principiante|primera\s+vez|minicurso))',
    r'\bdive\b(?!\s+(baptism|beginner|first\s+time))',
    r'\bdiving\b(?!\s+(first|beginner|class|course|lesson|trip\s+first))',
    r'\bscuba\b(?!\s+(class|course|lesson))',
    r'\bbuzo\s+certificado\b',
    r'\bbuzos\s+certificados\b',
    r'\bbuzos\b',                  # bare "buzos" (los dos buzos, 3 buzos) = divers
    r'\bsoy\s+buz[oa]\b',
    r'\bcertified\s+diver',
    r'\bdos\s+inmersiones\b',
    r'\btwo\s+dives\b',
    r'\bfun\s+dive',
    r'\bwant\s+(?:to\s+)?(?:go\s+)?diving\b',
    r'\binterested\s+in\s+diving\b',
    r'\bdiving\s+trip\b',
    r'\bsubmarinismo\b',           # synonym
]

# "Nunca se ha sumergido": una sola fuente para sus dos usos (hueco 3, 2026-09-16). Estaba
# escrito dos veces y divergia: la lista del minicurso admitia en espanol hasta tres
# palabras por medio ("nunca he/ha/hemos hecho bucea(do)") y en ingles cuatro frases
# cerradas, de las que la lista de certificacion solo tenia una ("never dived"). Asi,
# "never been underwater before, wanna give it a try" no salia como no certificado. Ahora
# la regla es la misma en los dos idiomas: nunca + auxiliares + el tema de sumergirse; el
# ingles ademas elide el objeto ("never tried", "never done it").
# Entre "nunca" y el tema solo caben auxiliares, participios y cliticos ("nunca HE HECHO
# buceo", "never HAVE BEEN diving", "nunca NOS HEMOS sumergido"). Con tres palabras
# cualesquiera, "i will never stop diving" salia como que nunca ha buceado.
_NEVER_AUX = (
    # `\w+[ai]do` es el participio regular ("practicado", "estado", "sumergido"); "hecho"
    # es el irregular que aparece de verdad ("nunca he HECHO buceo").
    r"(?:\s+(?:he|ha|hemos|han|hab\w+|me|nos|se|te|lo|hecho|\w+[ai]do|"
    r"have|has|had|been|done|tried|really|actually|even))*"
)
# El ingles elide el objeto: "never tried, wanna give it a try", "never done it before".
# Con otro objeto nombrado ("never tried nitrox") habla de ese producto, no de sumergirse.
_NEVER_TRIED_IT = (
    r"\bnever\s+(?:tried|done)(?:\s+(?:it|this|that|scuba|before|yet|ever))*"
    r"(?=\s*(?:[,.;!?]|$)|\s+(?:but|and|so|though)\b)"
)
_NEVER_DIVED = (
    r"\b(?:nunca|never)\b" + _NEVER_AUX + r"\s+"
    r"(?:buce\w*|inmersi\w+|div(?:e|ed|es|ing)|underwater|bajo\s+el\s+agua|sumerg\w*)\b"
    r"|" + _NEVER_TRIED_IT
)
# Nunca se ha certificado: mismo esqueleto, otro tema. Solo dice el estado, no la
# actividad, asi que no entra en la lista del minicurso.
_NEVER_CERTIFIED = r"\b(?:nunca|never)\b" + _NEVER_AUX + r"\s+(?:certific\w*|certified)\b"

_MINICOURSE_PATTERNS = [
    r'\bmini[\s\-]?curso\b',       # minicurso, mini curso, mini-curso
    r'\bbubble\s?makers?\b',       # Bubble Makers = kids intro dive (beginner, not certified)
    r'\bbautizo\s+de\s+buceo\b',
    r'\bbauti[sz]\w{0,3}\b',       # bautismo, bautizo, bautismos, bautizos
    r'\bprimera\s+vez\b',
    _NEVER_DIVED,
    r'\bno\s+experience\b',
    r'\bsin\s+experiencia\b',
    r'\bdiscover\s+scuba\b',
    r'\bbeginner\s+dive\b',
    r'\bfirst\s+time\s+diving\b',
    r'\btry\s+dive',
    r'\bno\s+s[eé]\s+bucear\b',   # "no sé bucear"
]

_SNORKEL_PATTERNS = [
    r'\be?snork\w{1,6}\b',         # snorkel, snorkeling, snorkle, esnorkel, esnorkeling
    r'\be?snorqu\w{0,6}\b',        # snorquel, snorqueling, esnorquel, esnorqueling
    r'\bcarete[ao]\w{0,3}\b',      # careteo, caretear
]

_PADI_COURSE_PATTERNS = [
    r'\bcurso\s+padi\b',
    r'\bpadi\s+course\b',
    r'\bopen\s+water\b',
    r'\badvanced\b',
    r'\brescue\b',
    r'\bdivemaster\b',
    r'\bcertificarme\b',
    r'\bget\s+certified\b',
    # "primer nivel"/"primer curso" (de buceo) -- gap real, hallazgo en vivo
    # (conversacion real 913, 2026-09-10): sin este patron, el mensaje solo
    # matcheaba el generico `_CERTIFIED_DIVING_PATTERNS` via "buceo", asi que
    # "quiero sacarme el primer nivel de buceo" resolvia mal a
    # certified_diving en vez de padi_open_water.
    r'\bprimer\s+(?:nivel|curso)\s*(?:de\s+buceo)?\b',
    r'\bfirst\s+(?:level|course)\s*(?:of\s+diving)?\b',
]

def _label_nouns(activities) -> frozenset[str]:
    """La palabra comun a todas las etiquetas de un grupo de actividades en cada idioma
    ("curso"/"course", "especialidad"/"specialty"), sin tildes."""
    nouns: set[str] = set()
    for lang in dom.LANGS:
        token_sets = [set(re.findall(r"\w+", strip_accents(a.label[lang].lower()))) for a in activities]
        if token_sets:
            nouns |= set.intersection(*token_sets)
    return frozenset(nouns)


def _specialty_name_patterns() -> tuple[tuple[str, str], ...]:
    """Especialidad concreta -> patron de su nombre, desde las etiquetas del registro
    (2026-09-15): la etiqueta sin el sustantivo de la familia ("Especialidad
    Flotabilidad" -> "flotabilidad", "Fish Identification specialty" -> "fish
    identification"), con y sin tildes. Antes el vocabulario estaba escrito tres veces
    (categoria, palabra -> id y tabla de cursos, que solo conocia nitrox)."""
    specialties = [a for a in dom.registry().activities if a.family == "specialty" and not a.generic]
    nouns = _label_nouns(specialties)
    table = []
    for activity in specialties:
        names = set()
        for lang in dom.LANGS:
            name = " ".join(w for w in re.findall(r"\w+", activity.label[lang].lower()) if strip_accents(w) not in nouns)
            names |= {name, strip_accents(name)}
        alternatives = "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in sorted(names, key=len, reverse=True))
        table.append((activity.id, rf"\b(?:{alternatives})\b"))
    return tuple(table)


_SPECIALTY_NAME_PATTERNS = _specialty_name_patterns()
_SPECIALTY_PATTERNS = [pattern for _, pattern in _SPECIALTY_NAME_PATTERNS]

# Nombres de curso que por si solos identifican un producto, en el orden del
# registro (nivel ascendente). Tabla UNICA (centralizacion 2026-09-15): antes el
# detector buscaba subcadenas ("open water", "advanced"...) y el nucleo tenia su
# propia `_COURSE_MENTION_RE` con variantes que el detector no conocia ("owd",
# "aowd", "avanzado", "rescate", "enriched air"). Las especialidades por palabra
# suelta ("peces", "fish") NO van aqui: solo cuentan con el contexto de
# "especialidad". Las especialidades salen de las etiquetas del registro
# (`_SPECIALTY_NAME_PATTERNS`); aqui solo quedan las variantes que ninguna etiqueta
# contiene ("owd", "rescate", "enriched air").
_COURSE_NAME_VARIANTS = {
    "padi_open_water": r"\bopen[\s-]*water\b|\bowd\b",
    "padi_advanced": r"\badvanced\b|\baowd\b|\bavanzad\w*\b",
    "padi_rescue": r"\brescue\b|\brescate\b",
    "padi_divemaster": r"\bdive\s*master\b",
    "specialty_nitrox": r"\benriched\s+air\b",
}
_COURSE_NAME_PATTERNS = tuple(
    (a.id, "|".join(p for p in (_COURSE_NAME_VARIANTS.get(a.id), dict(_SPECIALTY_NAME_PATTERNS).get(a.id)) if p))
    for a in dom.registry().activities
    if a.id in _COURSE_NAME_VARIANTS or a.id in dict(_SPECIALTY_NAME_PATTERNS)
)


def courses_mentioned(message: str) -> list[str]:
    """Ids de los cursos nombrados en el mensaje, en el orden del registro."""
    text = message or ""
    return [activity_id for activity_id, pattern in _COURSE_NAME_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)]


_ACTIVITY_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "certified_diving": _CERTIFIED_DIVING_PATTERNS,
    "minicourse": _MINICOURSE_PATTERNS,
    "snorkel": _SNORKEL_PATTERNS,
    "padi_course": _PADI_COURSE_PATTERNS,
    "specialty": _SPECIALTY_PATTERNS,
}


def matched_activity_categories(message: str) -> set[str]:
    """Categorias de actividad ({certified_diving, minicourse, snorkel,
    padi_course, specialty}) cuyos patrones matchean este mensaje — 0, 1 o
    varias. Funcion pura, sin llamadas ni estado; reusa EXACTAMENTE los
    mismos patrones que `_detect_activity` (nunca los duplica). 2+
    categorias a la vez es la senal barata de "mensaje ambiguo" (la usaba el
    veto LLM de actividad, borrado en MEJ-1; hoy la usan `_detect_activity`, el
    nucleo y `conversational_core`) — sin esto, un mensaje como "quiero el open water, nunca he buceado" (dispara
    minicourse Y padi_course) se resuelve solo por el ORDEN de la cadena
    if/elif, no por lo que el cliente realmente pidio (hallazgo en vivo,
    conversacion real "purple-sun-590", 2026-09-03)."""
    message_lower = message.lower()
    return {
        category for category, patterns in _ACTIVITY_CATEGORY_PATTERNS.items()
        if any(re.search(pattern, message_lower) for pattern in patterns)
    }


def course_level_is_ambiguous(message: str) -> bool:
    """Nivel PADI nombrado ("open water", "advanced"...) sin decir si la persona YA lo
    tiene o QUIERE sacarlo ("hola somos 4 open water", "2 advanced and 2 snorkel").

    Reusa los patrones del propio detector (`_CERT_LEVEL`, `_HOLDS_CERT_RE`,
    `_WANTS_CERT_RE`) y `certification_claim`, sin vocabulario nuevo. Decision del
    owner (2026-09-15): en ese caso el bot pregunta, no supone."""
    text = message or ""
    if not re.search(r"\b" + _CERT_LEVEL + r"\b", text, re.IGNORECASE):
        return False
    if _WANTS_CERT_RE.search(text) or _HOLDS_CERT_RE.search(text):
        return False
    # Nombra el PRODUCTO ("the advanced course", "curso de advanced", "la especialidad de
    # nitrox"): pide el curso o la especialidad, no dice que ya lo tenga.
    words = set(re.findall(r"\w+", strip_accents(text.lower())))
    if words & _product_family_nouns():
        return False
    return certification_claim(text) is None


@lru_cache(maxsize=1)
def _course_family_nouns() -> frozenset[str]:
    """El sustantivo con el que el catalogo nombra los cursos con nivel ("curso",
    "course"), derivado del registro: la palabra comun a todas sus etiquetas en cada
    idioma. Sin lista escrita a mano."""
    return _label_nouns([a for a in dom.registry().activities if a.family == "course" and a.course_level])


@lru_cache(maxsize=1)
def _product_family_nouns() -> frozenset[str]:
    """Los sustantivos con los que el catalogo nombra un producto que lleva nivel: el de
    los cursos y el de las especialidades ("especialidad"/"specialty"), del registro
    (hueco 1, 2026-09-16: "quiero la especialidad de nitrox" preguntaba si ya la tenia)."""
    specialties = [a for a in dom.registry().activities if a.family == "specialty" and not a.generic]
    return _course_family_nouns() | _label_nouns(specialties)


# Vocabulario de "¿el mensaje afirma/niega certificacion?" -- elevado de
# variables locales de `_detect_certification` a constantes de modulo
# (2026-09-03, inventario regex tras el hallazgo "purple-sun-590") para que
# `certification_claim()` sea la fuente unica que reusa `conversational_core.
# _activity_has_textual_backing` en vez de su propio par de regex
# (`_CERTIFICATION_CLAIM_RE`/`_CERTIFICATION_NEGATED_RE`, sin la prioridad de
# negacion ni la mayoria del vocabulario de aqui). No incluye la logica de
# "sostiene un nivel PADI" (`_HOLDS_CERT_RE`/`_WANTS_CERT_RE`, metodos de
# IntentDetector) -- eso es un chequeo aparte, con su propio caller.
_CERTIFIED_PATTERNS = [
    r'\bcertificado\b',
    r'\bcertificados\b',
    r'\bcertified\b',
    r'\bcertificaci[oó]n\b',
    r'\bestamos\s+certificados\b',
    r'\bsomos\s+certificados\b',
    # Quien escribe. "tiene/tienen licencia" habla de otra persona: ver
    # `_CERTIFIED_OTHER_PERSON_PATTERNS` (2026-09-15).
    r'\bt(?:engo|enemos)\s+(?:la\s+|su\s+)?licencia\b',
    r'\bhave\s+(?:a\s+)?(?:license|licence|card|certification)\b',
    r'\b(?:padi|ssi|cmas|naui|bsac)\s+(?:certified|card|license|licence|certification|open\s+water|advanced)\b',
    r'\blicencia\s+(?:padi|ssi|cmas|naui|bsac)\b',
    r'\b(?:padi|ssi|cmas|naui|bsac)\s+licencia\b',
    r'\bpadi\s+(certified|card|license)\b',
    r'\bssi\s+(certified|card|license)\b',
    r'\bbuzo\s+certificado\b',
    r'\bbuzos\s+certificados\b',
    r'\bwith\s+(?:open\s+water|advanced|rescue|divemaster|padi|ssi|cmas)\s+certification\b',
    r'\b(?:\d+\s+)?dives?\s+(?:each|of\s+experience)\b',
    # "buzos con open water" / "tenemos open water" / "open water divers"
    r'\bcon\s+open\s+water\b',
    r'\btenemos\s+open\s+water\b',
    r'\bopen\s+water\s+divers?\b',
    r'\bopen\s+water\s+certified\b',
    r'\bsomos\s+(?:buzos?|divers?)\b',  # "somos buzos" implica cert
    r'\bsoy\s+buz[oa]\b',               # "soy buzo/buza" = certified diver
    r'\bbuzos\b',                        # bare plural "buzos" = certified divers (group)
    r'\b(?:los|las|ambos|ambas)\s+(?:dos\s+)?buzos?\b',  # "los dos buzos"
    # "título de buceo" / "estoy titulad[oa]" (hallazgo en vivo, bateria
    # sintetica shadow-mode, 2026-09-10): sinonimo real de "certificado" que
    # ningun patron cubria -- "tengo el título de buceo"/"estoy titulada en
    # buceo" quedaban sin ninguna senal (is_certified=None), y el bot
    # volvia a preguntar algo que el cliente ya habia respondido.
    r'\bt[ií]tulo\s+de\s+buceo\b',
    r'\btengo\s+(?:el\s+)?t[ií]tulo\b',
    r'\btitulad[oa]s?\s+en\s+buceo\b',
    r'\bestoy\s+titulad[oa]\b',
    # Typo-tolerant fallback: matches "certficado", "certifcado",
    # "certificacion", "certified"... anything starting with "cert".
    # Checked LAST so the more specific _NOT_CERTIFIED_PATTERNS below
    # (which also start with "cert") always get first chance.
    r'\bcert\w*\b',
]

# Certificacion de OTRA persona (2026-09-15): "mi amigo tiene licencia", "dos no tienen
# licencia". Cuenta para repartir el grupo o respaldar la actividad de un acompanante,
# nunca para el estado de quien escribe: "mi amigo tiene licencia, yo no" marcaba al
# cliente como certificado.
_CERTIFIED_OTHER_PERSON_PATTERNS = [
    r'\bt(?:iene|ienen)\s+(?:la\s+|su\s+)?licencia\b',
]

# Deseo de certificarse: una sola fuente (2026-09-15). Antes vivia en tres listas que no
# coincidian: `_WANTS_CERT_RE` (solo niveles), un patron de
# `_NOT_CERTIFIED_PATTERNS` (solo "quiero ...") y `rag_agent._WANTS_CERT_EXCLUDE_RE`
# (cualquier "quiero hacer ...", incluido "quiero hacer buceo"). "quiere sacarse la
# certificacion" o "me quiero certificar" no casaban ninguna y salian certificados.
# Verbo de deseo: "quiero", "sacarse", "want to get", "me interesa". Solo este dice que aun
# no lo tiene; "hacer el open water" a secas tambien sale en dudas ("no se si hacer el open
# water o el advanced"), por eso el resto de verbos solo cuenta para `_WANTS_CERT_RE`.
# El interes es querer (hueco 1, 2026-09-16, reverso de F.1): "me interesa el rescue",
# "my son is interested in the open water". Misma clase cerrada que el deseo, en primera y
# tercera persona; sin esto el nivel quedaba sin decir si lo tienen o lo quieren y el bot
# preguntaba de mas ("¿ya la tienes o quieres sacarla?").
# El verbo lleva su propio sujeto: el clitico dativo ("me"/"le") y la persona del auxiliar
# dicen de quien se habla aunque el sujeto vaya detras ("le interesa el open water a mi
# hijo"), asi que `_about_other_person` lee la variante de tercera persona.
_INTEREST_VERB_WRITER = (
    r"(?:(?:me|nos)\s+interesa\w*|"
    r"est(?:oy|amos)\s+interesad[oa]s?\s+en|"
    r"(?:i'?m|i\s+am|we'?re|we\s+are)\s+interested\s+in)"
)
_INTEREST_VERB_OTHER = (
    r"(?:(?:le|les)\s+interesa\w*|"
    r"est[aá]n?\s+interesad[oa]s?\s+en|"
    r"(?:is|are)\s+interested\s+in)"
)
_INTEREST_VERB = r"(?:" + _INTEREST_VERB_WRITER + r"|" + _INTEREST_VERB_OTHER + r")"
_DESIRE_VERB = (
    r"(?:quier[eo]n?|queremos|quisiera|quisi[eé]ramos|me\s+gustar[ií]a|nos\s+gustar[ií]a|"
    r"sacar(?:me|te|se|nos)|want\s+to\s+(?:do|take|get|be|become)|" + _INTEREST_VERB + r")"
)
_WANT_VERB = r"(?:" + _DESIRE_VERB + r"|hacer(?:me|se|nos)?|sacar|obtener|tomar|get)"
# Llegar a serlo es querer el nivel ("quiero ser divemaster", "want to be a divemaster"):
# el camino al objeto admite el verbo copulativo, igual que admite "hacer" o "sacar".
_WANT_OBJECT_PREFIX = (
    r"\s+(?:el\s+|la\s+|mi\s+|un[ao]?\s+|nuestr[ao]\s+|hacer\s+|sacar\s+|obtener\s+|tomar\s+|"
    r"ser\s+|llegar\s+a\s+ser\s+|be\s+|become\s+|"
    r"the\s+|our\s+|my\s+|a\s+)*"
    r"(?:curso\s+)?(?:padi\s+)?(?:de\s+)?"
)
_CERT_NOUN = r"(?:certificaci\w*|licencia|certification|licen[cs]e)"
# Quiere el nivel de entrada o "la certificacion" en general: aun no esta certificado.
# Querer Advanced o Rescue no dice eso (exigen Open Water), por eso no entra aqui.
_WANTS_CERTIFICATION = (
    r"\b" + _DESIRE_VERB + _WANT_OBJECT_PREFIX + r"(?:open[\s-]*water|aguas\s+abiertas|" + _CERT_NOUN + r")"
    r"|\bcertificar(?:me|nos|te|se)?\b|\bget\s+certified\b"
)

_NOT_CERTIFIED_PATTERNS = [
    r'\bno\s+(?:esta\s+|estoy\s+|estamos\s+|est[aá]n\s+|soy\s+|somos\s+|es\s+|son\s+|eres\s+|fui\s+)?cert\w*\b',
    r'\bno\s+(?:soy|somos|son|es)\s+buz',   # "no somos buzos" = not certified
    r'\b(?:ser|hacerme|hacernos|convertirme|convertirnos)\s+(?:en\s+)?buz',  # wants to BECOME a diver
    r'\bsin\s+cert\w*\b',
    # Wants to GET certified, so NOT yet certified. Must be listed here (checked
    # before the generic \bcert\w*\b catch-all).
    _WANTS_CERTIFICATION,
    _NEVER_DIVED,
    # "nunca me he certificado" (hallazgo en vivo, bateria sintetica shadow-
    # mode is_certified, 2026-09-10): mismo hueco que el patron de arriba
    # pero para "certificado" en vez de "buce*" -- sin esto, caia al catch-all
    # generico \bcertificado\b de _CERTIFIED_PATTERNS y resolvia True cuando
    # el cliente dice justo lo contrario.
    _NEVER_CERTIFIED,
    r'\bprimera\s+vez\b',
    # Typo-tolerant (real bug live 2026-07-21: "not certfied" matched
    # neither this pattern nor the exact positive certified pattern, and
    # fell through to that list's own typo-tolerant \bcert\w*\b catch-all,
    # wrongly resolving to is_certified=True).
    r'\bnot\s+cert\w*\b',
    r'\bfirst\s+time\b',
    r'\bbeginner\b',
    r'\bprincipiante\b',
]


# Negacion que alcanza a lo que viene justo despues (hasta dos palabras por medio):
# "no tienen certificación", "aren't certified", "sin la licencia". Sin tildes.
_NEGATION_BEFORE_RE = re.compile(
    r"(?:\bno\b|\bnot\b|n't\b|\bnunca\b|\bnever\b|\bsin\b|\bwithout\b)(?:\s+\S+){0,2}\s*$"
)


def certification_claim(text: str, about_writer: bool = True) -> bool | None:
    """True si el texto AFIRMA certificacion, False si la NIEGA, None si no
    hay señal. Con `about_writer=False` cuenta tambien lo que se dice de otra
    persona ("mi amigo tiene licencia"). Negacion primero (misma prioridad que `_detect_certification`,
    que reusa esta funcion internamente). Funcion pura, sin estado ni
    llamadas -- fuente unica para "¿este texto dice que alguien esta/no esta
    certificado?" en mensajes CRUDOS del cliente (no en notas parafraseadas
    por LLM -- ver `supervisor._CERTIFIED_MENTION_RE`/`_UNCERTIFIED_
    COMPANION_NOTE_RE`, que operan sobre ese dominio distinto a proposito y
    NO reusan esta funcion)."""
    # Texto y patrones se comparan sin tildes (hallazgo 2026-09-14): el patron de
    # negacion escribia "esta" sin tilde, asi que "mi amigo no está certificado"
    # no casaba la negacion, caia en `\bcertificado\b` y resolvia True. Normalizar
    # una vez aqui cubre todas las variantes de tilde de las dos listas.
    text = strip_accents((text or "").lower())

    def _counts(match) -> bool:
        # Sujeto (2026-09-15): lo que se dice de otra persona en su propia frase ("mi
        # amigo no esta certificado", "my wife is certified") no es de quien escribe.
        return not about_writer or not _about_other_person(text, match.start())

    if any(_counts(m) for pattern in _NOT_CERTIFIED_PATTERNS for m in re.finditer(strip_accents(pattern), text)):
        return False
    patterns = _CERTIFIED_PATTERNS if about_writer else _CERTIFIED_PATTERNS + _CERTIFIED_OTHER_PERSON_PATTERNS
    positives = [m for pattern in patterns for m in re.finditer(strip_accents(pattern), text) if _counts(m)]
    if not positives:
        return None
    # Alcance de la negacion (2026-09-15): "2 no tienen certificación" o "two aren't
    # certified" casaban el positivo y daban True. En vez de anadir cada frase
    # negativa a la lista, una afirmacion precedida de cerca por una negacion no cuenta.
    if all(_is_negated(text[:m.start()]) for m in positives):
        return False
    return True


def _is_negated(prefix: str) -> bool:
    """Paridad de la cadena de negaciones pegadas al final de `prefix`: "no tienen" niega,
    "no es que no estemos" (doble negacion) no."""
    count = 0
    while (match := _NEGATION_BEFORE_RE.search(prefix)):
        count += 1
        prefix = prefix[:match.start()]
    return count % 2 == 1


# Vocabulario compartido de sustantivos de parentesco/compañía -- inventario
# regex 2026-09-03: antes había 8 listas independientes (5 en
# conversational_core.py, 2 en supervisor.py, 1 aquí) para "¿el mensaje
# menciona a otra persona?", mantenidas a mano por separado. Evidencia real
# de desincronización: un fix de plurales en inglés ("kids") se añadió a UNA
# de las 8 (auditoría 2026-07-23) sin confirmación de que se propagara a las
# demás -- y de hecho "boyfriend"/"girlfriend" faltaban en la lista EN más
# completa (`_MENTIONS_PERSON_RE`) pese a estar en otras 2.
#
# Tres fragmentos (no una sola lista mágica) porque cada estructura exige una
# FORMA gramatical distinta y el inglés tiene plurales irregulares (wife ->
# wives) que no se pueden derivar solo con un sufijo "s?":
# - `_PERSON_NOUN_MENTION_ES/EN`: forma libre con plural opcional ("s?"/
#   "es?" ya incorporado) -- para "¿el mensaje menciona ESTE tipo de
#   persona en general?" (_MENTIONS_PERSON_RE).
# - `_PERSON_NOUN_SINGULAR_ES/EN`: forma singular pelada, sin sufijo -- para
#   patrones que exigen un determinante singular antes ("mi hijo", "un
#   amigo") y de ahí infieren "exactamente 1 persona"
#   (_ADDED_PERSON_RE, _NOT_ALONE_RE, _SINGULAR_COMPANION_RE).
# - `_PERSON_NOUN_PLURAL_ES/EN`: forma plural obligatoria -- para patrones
#   que exigen plural explícito para NO asumir "1 persona"
#   (_PLURAL_COMPANION_RE).
# Añadir un sustantivo nuevo significa tocar 1-3 fragmentos aquí, no 8
# patrones repartidos en 3 archivos.
_PERSON_NOUN_MENTION_ES = (
    r"amig[oa]s?|prim[oa]s?|parej\w*|novi[oa]s?|espos[oa]s?|marido|mujer|"
    r"herman[oa]s?|hij[oa]s?|padre|madre|pap[aá]s?|mam[aá]s?|suegr[oa]s?|"
    r"cu[ñn]ad[oa]s?|sobrin[oa]s?|niet[oa]s?|abuel[oa]s?|familia\w*|"
    r"acompa[ñn]antes?|compa[ñn]er[oa]s?"
)
_PERSON_NOUN_MENTION_EN = (
    r"friends?|partners?|wife|wives|husbands?|boyfriends?|girlfriends?|"
    r"brothers?|sisters?|sons?|daughters?|moms?|dads?|mothers?|fathers?|"
    r"cousins?|companions?|kids?|child(?:ren)?"
)
_PERSON_NOUN_SINGULAR_ES = (
    r"amig[oa]|novi[oa]|espos[oa]|marido|mujer|pareja|compa[ñn]er[oa]|"
    r"acompa[ñn]ante|herman[oa]|hij[oa]|padre|madre|pap[aá]|mam[aá]|prim[oa]|"
    r"suegr[oa]|cu[ñn]ad[oa]|sobrin[oa]|niet[oa]|abuel[oa]"
)
_PERSON_NOUN_SINGULAR_EN = (
    r"friend|partner|wife|husband|boyfriend|girlfriend|brother|sister|son|"
    r"daughter|companion|cousin|kid|child"
)
_PERSON_NOUN_PLURAL_ES = (
    r"amig[oa]s|novi[oa]s|espos[oa]s|parejas|compa[ñn]er[oa]s|"
    r"acompa[ñn]antes|herman[oa]s|hij[oa]s|prim[oa]s|padres|mam[aá]s|"
    r"pap[aá]s|suegr[oa]s|cu[ñn]ad[oa]s|sobrin[oa]s|niet[oa]s|abuel[oa]s"
)
_PERSON_NOUN_PLURAL_EN = (
    r"friends|buddies|companions|partners|wives|brothers|sisters|sons|"
    r"daughters|cousins|kids|children"
)
# Una persona en singular con su determinante ("mi amigo", "un hijo", "my wife", "su
# hermano"). Pieza unica (2026-09-15) para el acompanante singular del nucleo y para
# contar personas nombradas en el reparto: antes cada uno tenia su lista de determinantes.
_SINGULAR_PERSON = (
    r"\b(?:mi|my|un[ao]?|an?|su|tu|his|her|el|la)\s+(?:"
    + _PERSON_NOUN_SINGULAR_ES + r"|" + _PERSON_NOUN_SINGULAR_EN + r")\b"
)
# Persona nombrada que no es quien escribe: singular con determinante o plural con
# posesivo ("mi amigo", "mis amigos", "my wife"). Pieza de los dos ordenes del sujeto.
_NAMED_OTHER_PERSON = (
    _SINGULAR_PERSON
    + r"|\b(?:mis|sus|tus|los|las|my|our|his|her|their)\s+(?:"
    + _PERSON_NOUN_PLURAL_ES + r"|" + _PERSON_NOUN_PLURAL_EN + r")\b"
)
_THIRD_PERSON_VERB = r"(?:es|son|esta|estan|tiene|tienen|ha|han|is|are|has|have)"
# Sujeto que es OTRA persona (2026-09-15), siempre seguido de su verbo en tercera persona:
# "mi amigo es", "mis amigos tienen", "él es", "uno no esta", "two aren't", "my wife is".
# Sin verbo detras es un complemento, no el sujeto: "i am a certified diver with a
# companion" sigue siendo de quien escribe. Sirve para saber de quien habla una frase de
# certificacion.
_OTHER_PERSON_SUBJECT = (
    r"(?:" + _NAMED_OTHER_PERSON
    + r"|\b(?:el|ella|ellos|ellas|he|she|they"
    # Una cantidad o "el otro" como sujeto: "uno no esta certificado", "dos no tienen
    # licencia", "two aren't certified" hablan de otros miembros del grupo.
    r"|\d+|" + number_alt(1, 9) + r"|otr[oa]s?|others?)\b"
    r")\s+(?:de\s+\w+\s+|que\s+|\w+\s+)?(?:no\s+|nunca\s+|never\s+)?"
    r"(?:es|son|esta|estan|tiene|tienen|ha|han|quiere|quieren|se\s+certific\w*"
    r"|is|are|isn'?t|aren'?t|has|have|hasn'?t|haven'?t|wants)\b"
)
_OTHER_PERSON_SUBJECT_RE = re.compile(strip_accents(_OTHER_PERSON_SUBJECT), re.IGNORECASE)


# Sujeto pospuesto (2026-09-15): "no es certificado mi acompañante", "está certificada mi
# novia". Verbo en tercera persona y, detras en la misma frase, una persona nombrada, sin
# una preposicion de compania o destino por medio: "quiero bucear con mi pareja" o "es para
# mi novia" son complementos, no el sujeto.
_POSTVERBAL_OTHER_SUBJECT_RE = re.compile(
    strip_accents(
        r"\b" + _THIRD_PERSON_VERB + r"\b(?:\s+(?!(?:con|para|a|al|with|for|to)\b)\w+){0,4}?\s+(?:"
        + _NAMED_OTHER_PERSON + r")"
    ),
    re.IGNORECASE,
)
# Una frase acaba en puntuacion o conjuncion: "mi amigo es buzo y yo no" son dos.
_CLAUSE_BOUNDARY_RE = re.compile(r"[,;.]|\b(?:y|e|pero|and|but)\b")
_OTHER_PERSON_EXPERIENCER_RE = re.compile(strip_accents(_INTEREST_VERB_OTHER), re.IGNORECASE)


def _about_other_person(text: str, start: int) -> bool:
    """¿La coincidencia que empieza en `start` va en una frase cuyo sujeto es otra persona?
    Se mira la frase entera, antes y despues: en "uno no esta certificado" el verbo del
    sujeto cae dentro de la coincidencia. `text` ya en minusculas y sin tildes."""
    clause = _CLAUSE_BOUNDARY_RE.split(text[:start])[-1] + _CLAUSE_BOUNDARY_RE.split(text[start:])[0]
    return bool(
        _OTHER_PERSON_SUBJECT_RE.search(clause)
        or _POSTVERBAL_OTHER_SUBJECT_RE.search(clause)
        # El verbo de interes en tercera persona lleva el sujeto dentro (2026-09-16):
        # "le interesa el open water a mi hijo" no dice nada de quien escribe.
        or _OTHER_PERSON_EXPERIENCER_RE.search(clause)
    )


# Palabras de lugar con una sola fuente (hallazgo C, 2026-09-15). Antes el nucleo tenia su
# propio `_CARTAGENA_RE`/`_ISLAND_RE`: no conocia los apodos de la ciudad ni los hoteles, y
# leia isla en "rezar el rosario".
# Cartagena por su nombre o sus apodos historicos ("la heroica", "corralito de piedra",
# "the walled city"...). "cartagena"/"ctg" como subcadena: "cartagenaa" con errata cuenta.
_CARTAGENA_NAME_RE = re.compile(
    r"cartagena|ctg|\bla\s+heroica\b|\bcorralito\s+de\s+piedra\b|\bciudad\s+redentora\b"
    r"|\b(?:la\s+)?ciudad\s+amurallada\b|\bcentro\s+amurallado\b|\b(?:the\s+)?heroic\s+city\b"
    r"|\b(?:the\s+)?walled\s+city\b|\bqueen\s+of\s+the\s+caribbean\b",
    re.IGNORECASE,
)
# Isla sin nombre concreto ("isla", "las islas", "island", "Barú", "los rosarios"). Sola no
# dice si es el destino o donde se aloja: el detector no la usa para fijar la ubicacion,
# pero si para saber que el mensaje nombra una isla, y el nucleo la acepta como respuesta a
# "¿desde donde saldrias?".
_GENERIC_ISLAND_RE = re.compile(r"\b(?:isla\w*|island\w*|bar[uú]|(?:los|the)\s+rosarios)\b", re.IGNORECASE)

# Palabras que abren una pregunta subordinada ("no se SI...", "not sure WHETHER...", "duda
# ENTRE..."): clase cerrada, no vocabulario de dominio. Cortan el alcance de una negacion
# (hallazgo K) y el papel de un lugar (hallazgo C.2).
_EMBEDDED_QUESTION_WORDS = frozenset({"si", "if", "whether", "entre", "between"})
# Papel de un lugar por la preposicion que lleva delante (hallazgo C.2, 2026-09-16): clase cerrada.
_STAY_WORDS = frozenset({"en", "in", "on", "at"})
_ORIGIN_WORDS = frozenset({"desde", "de", "del", "from"})
_DESTINATION_WORDS = frozenset({"a", "al", "hacia", "hasta", "para", "to", "toward", "towards", "into"})
_ARTICLE_WORDS = frozenset({"el", "la", "los", "las", "the", "un", "una"})


def place_by_role(text: str, lodging_island: bool = False) -> str | None:
    """Ubicacion cuando el mensaje nombra Cartagena Y una isla (hallazgo C.2, 2026-09-16).

    Si es la salida o el alojamiento, o el destino de la excursion, lo dice la preposicion que
    lleva cada lugar: estancia ("estoy en", "staying on") > origen ("desde", "from") > sin
    preposicion > destino ("ir a las islas", "head to"). El destino no es la ubicacion. Una
    mencion negada ("no estamos en las islas") no cuenta, y un hotel de isla es alojamiento
    (`lodging_island`). Devuelve None si ninguna mencion lleva preposicion: decide la
    precedencia de siempre. Dejar estos mensajes al LLM se midio y fue peor (el LLM tambien
    toma el destino por la ubicacion). `text` en minusculas."""
    mentions = []
    for kind, regex in (("cartagena", _CARTAGENA_NAME_RE), ("island", _GENERIC_ISLAND_RE)):
        for match in regex.finditer(text):
            clause = _CLAUSE_BOUNDARY_RE.split(text[:match.start()])[-1]
            words = [w for w in re.findall(r"\w+", clause) if w not in _ARTICLE_WORDS]
            words = words[max((i + 1 for i, w in enumerate(words) if w in _EMBEDDED_QUESTION_WORDS), default=0):]
            last = words[-1] if words else ""
            role = ("stay" if last in _STAY_WORDS else "origin" if last in _ORIGIN_WORDS
                    else "destination" if last in _DESTINATION_WORDS else None)
            if not _is_negated(" ".join(words)):
                mentions.append((match.start(), kind, role))
    if lodging_island:
        mentions.append((len(text), "island", "stay"))
    mentions.sort()
    if not any(role for _, _, role in mentions):
        return None
    stays = [kind for _, kind, role in mentions if role == "stay"]
    if stays:
        return stays[-1]
    for wanted in ("origin", None):
        kinds = [kind for _, kind, role in mentions if role == wanted]
        if kinds:
            return kinds[0]
    return mentions[0][1]


def detect_ages(message: str, intent: DetectedIntent) -> None:
    """Extract person ages mentioned in the message ("mi hijo de 9 años",
    "uno tiene 14", "a 6 year old", "kids aged 8 and 10").

    Skips clear non-age numbers: 'hace N años' / 'N years ago' (last-dive
    context), and durations like 'N días/horas'. Ages are 1-99.
    """
    ages: list[int] = []

    def _add(group: str) -> None:
        for num in re.findall(r'\d{1,2}', group):
            a = int(num)
            if 1 <= a <= 99:
                ages.append(a)

    # 1) Numbers explicitly qualified by an age unit, including coordinated
    #    lists: "9 años", "8 y 10 años", "6 and 12 years old", "14yo".
    #    Skip "hace N años" / "N years ago" (last-dive context, not an age).
    for m in re.finditer(
        r'((?:\d{1,2}\s*(?:,|y|e|and|&)\s*)*\d{1,2})\s*(?:a[nñ]os?|year[s]?(?:\s*old)?|y(?:/|-)?o)\b',
        message,
    ):
        # Timeframes are NOT ages: "hace (como) 3 años", "llevo 4 años sin
        # bucear", "in like 4 years", "5 years ago". The old 8-char window
        # cut "hace" out of "hace como 3 años" (real bug: the years since
        # the last dive became a phantom kid's age and would poison the
        # checkout's kids split — Fase 7, docs/robustness/plan.md).
        preceding = message[max(0, m.start() - 20):m.start()]
        if re.search(r'\b(hace|ultimo|ultima|last|desde|llevo|llevamos|in|for|like|since)\b', preceding):
            continue
        if re.match(r'\s*(?:ago|sin\s+bucear|que\s+no\s+buce)', message[m.end():]):
            continue
        _add(m.group(1))
    # 2) Kid-noun context without the word "años", incl. coordinated ages:
    #    "niño de 8", "hijo de 9", "niños de 8 y 10".
    for m in re.finditer(
        r'\b(?:niñ[oa]|nin[oa]|hij[oa]|niet[oa]|beb[eé]|kid|child|son|daughter|grandchild)s?\s+de\s+'
        r'((?:\d{1,2}\s*(?:,|y|e|and|&)\s*)*\d{1,2})',
        message,
    ):
        _add(m.group(1))
    # 2b) Kid-noun + "tiene N" without an age unit: "mi hijo, tiene 7",
    #     "mi hija tiene 9". Common in incremental group building.
    for m in re.finditer(
        r'\b(?:niñ[oa]|nin[oa]|hij[oa]|niet[oa]|beb[eé])s?\b[^.;]{0,20}?\btiene\s+(\d{1,2})\b',
        message,
    ):
        _add(m.group(1))
    # 3) "uno/una/otro/otra de N" — a specific group member's age (NOT
    #    "familia de N" / "grupo de N", which are group sizes).
    for m in re.finditer(r'\b(?:uno|una|otr[oa]|el\s+otro|la\s+otra)\s+de\s+(\d{1,2})\b', message):
        _add(m.group(1))
    # 4) "aged 8 and 10", "ages 8 and 10", "edad 8 y 10".
    #    9-oct: también en singular, "1 youth (age 17)" (familia-mixta: se perdían 2 de
    #    6 edades); no "minimum age 10" / "edad mínima", que es una regla, no una persona.
    _edad_re = r'aged|ages?'
    for m in re.finditer(
        rf'\b(?:{_edad_re}|edad(?:es)?(?:\s+de)?)\s+((?:\d{{1,2}}\s*(?:,|y|e|and|&)\s*)*\d{{1,2}})',
        message,
    ):
        if re.search(r'm[ií]nim|\bmin\b', message[max(0, m.start() - 12):m.start()]):
            continue
        _add(m.group(1))
    # 5) English kid-noun + "are/is N and M": "our kids are 7 and 11".
    for m in re.finditer(
        r'\b(?:kids?|children|sons?|daughters?)\s+(?:are|is)\s+'
        r'((?:\d{1,2}\s*(?:,|and|&)\s*)*\d{1,2})',
        message,
    ):
        _add(m.group(1))

    def _add_words(group: str) -> None:
        for w in re.findall(_AGE_WORD_ALT, group, re.IGNORECASE):
            ages.append(AGE_WORDS[w.lower()])

    # 6) Edades en PALABRA (opción A): "nueve años", "cinco y siete años",
    #    "mi hija de nueve", "kids aged eight and eleven". Mismas guardas de
    #    plazo que el patrón 1 ("llevo nueve años sin bucear" NO es edad).
    for m in re.finditer(
        rf'\b((?:(?:{_AGE_WORD_ALT})\s*(?:,|y|e|and|&)\s*)*(?:{_AGE_WORD_ALT}))'
        r'\s*(?:a[nñ]os?|year[s]?(?:\s*old)?)\b',
        message, re.IGNORECASE,
    ):
        preceding = message[max(0, m.start() - 20):m.start()]
        if re.search(r'\b(hace|ultimo|ultima|last|desde|llevo|llevamos|in|for|like|since)\b',
                     preceding, re.IGNORECASE):
            continue
        if re.match(r'\s*(?:ago|sin\s+bucear|que\s+no\s+buce)', message[m.end():], re.IGNORECASE):
            continue
        _add_words(m.group(1))
    # 6b) kid-noun / "aged" + word-number sin la palabra "años":
    #     "mi hija de nueve", "un niño de doce", "aged eight and eleven".
    for m in re.finditer(
        r'\b(?:niñ[oa]|nin[oa]|hij[oa]|niet[oa]|beb[eé]|kid|child|son|daughter|grandchild'
        r'|aged?|ages|edad(?:es)?)s?\s+(?:de\s+)?'
        rf'((?:(?:{_AGE_WORD_ALT})\s*(?:,|y|e|and|&)\s*)*(?:{_AGE_WORD_ALT}))\b',
        message, re.IGNORECASE,
    ):
        _add_words(m.group(1))
    # 6c) kid-noun + "tiene N" en palabra: "mi hijo tiene ocho" (equivalente
    #     al patrón 2b de dígitos).
    for m in re.finditer(
        rf'\b(?:niñ[oa]|nin[oa]|hij[oa]|niet[oa]|beb[eé])s?\b[^.;]{{0,20}}?\btiene\s+({_AGE_WORD_ALT})\b',
        message, re.IGNORECASE,
    ):
        _add_words(m.group(1))

    if ages:
        intent.ages = sorted(set(ages))
        intent.detected_fields.append("ages")


def detect_duration(message: str, intent: DetectedIntent) -> None:
    spans = [
        _duration_span(m, unit_days)
        for pattern, unit_days in _DURATION_RES
        for m in pattern.finditer(message)
        if not _is_elapsed_time(message, m)
    ]
    # Lo que no es cantidad x unidad: un paquete dura varios dias por definicion
    # (lo dice el catalogo) y "solo hoy" es un dia.
    if _MULTI_DAY_PRODUCT_RE.search(message):
        spans.append(_MAX_PACKAGE_DAYS)
    if _TODAY_ONLY_RE.search(message):
        spans.append(1)
    if not spans:
        return
    # La estancia mas larga manda, como antes mandaba el patron de varios dias:
    # "un dia de buceo y 3 dias en las islas" es multi-dia.
    intent.duration = "multi_day" if max(spans) > 1 else "single_day"
    intent.detected_fields.append("duration")


def detect_location(message: str, intent: DetectedIntent, *, nombra_un_hotel: bool = False) -> None:
    """El lugar que nombra el mensaje: Cartagena, una isla o un hotel de `lugares.json` (con su isla) y el papel de cada
    uno. `nombra_un_hotel`: se sabe que el texto es el nombre de un hotel (la cita del extractor o la respuesta a la
    pregunta del hotel), así que cuentan también los alias de hotel que son palabras corrientes (lat-11 T6c)."""
    msg_lower = message.lower()

    # Detectar Cartagena — incluye apodos históricos reales de la ciudad,
    # ES y EN ("la heroica"/"the heroic city": Simón Bolívar tras el Sitio
    # de Morillo de 1815; "corralito de piedra": sus murallas coloniales;
    # "ciudad redentora": otro título del propio Bolívar; "la ciudad
    # amurallada"/"the walled city": el centro histórico amurallado, muy
    # usado por locales y turistas hispanohablantes; "queen of the
    # caribbean": apodo turístico en inglés).
    # Encontrado 2026-07-09 que ninguno se reconocía — solo "cartagena"/"ctg".
    if _CARTAGENA_NAME_RE.search(msg_lower):
        intent.location = "cartagena"
        intent.detected_fields.append("location")

    # Detectar isla primero (las islas y sus alias están en lugares.json, lat-11 T5). La forma corta de una isla que
    # se llama "Isla X" ("grande", "marina", "arena", "pirata") es tambien una palabra corriente: solo cuenta si el
    # mensaje nombra una isla (hallazgo C.3, 2026-09-16; "nos vemos en la marina" o "somos un
    # grupo grande" no son una isla). Los nombres de hotel son nombres propios y no cambian.
    names_an_island = bool(_GENERIC_ISLAND_RE.search(msg_lower))
    island_id = isla_nombrada(msg_lower, nombra_una_isla=names_an_island)
    if island_id:
        intent.island = island_id
        intent.location = "island"
        intent.detected_fields.extend(["island", "location"])

    # Bare "rosario" also means the islands (e.g. "corales del rosario"),
    # but checked separately from the loop above and guarded against
    # "rezar el rosario" — the Catholic prayer, a common phrase in
    # Colombia. Pre-existing false positive (bare \brosario\b in the loop
    # above matched it too) found 2026-07-09 while auditing nicknames.
    # lat-11 T6c (26-oct): es el archipiélago ("las Islas del Rosario", "Rosario Islands"), no Isla Rosario: dice
    # "en las islas" sin isla concreta (antes daba island=isla_rosario, que llegaba al lead y al RAG).
    names_the_archipelago = bool(re.search(r'\brosario\b', msg_lower)) and not re.search(r'\brezar\b', msg_lower)
    if not intent.island and names_the_archipelago:
        intent.location = "island"
        intent.detected_fields.append("location")

    # Detectar hotel (los hoteles, sus alias y su isla están en lugares.json, lat-11 T5)
    hotel = hotel_nombrado(msg_lower, nombra_un_hotel=nombra_un_hotel)
    if hotel:
        hotel_id, hotel_island = hotel
        intent.hotel = hotel_id
        # Detectar isla automáticamente desde el hotel
        if hotel_island and not intent.island:
            intent.island = hotel_island
            intent.detected_fields.append("island")
        if not intent.location:
            intent.location = "island"
            # s4-27 (8-oct): la ubicacion que se deduce del hotel se DECLARA, como
            # todas, para que pase por la puerta de Jev (u3-3/u3-4). Sin declararla se colaba siempre:
            # "¿me pasas el contacto del hotel Cocoliso?" (Jev: no afirma ubicacion) dejaba al cliente "ya en
            # las islas" (contacto-hoteles-cocoliso-san-pedro).
            intent.detected_fields.append("location")
        intent.detected_fields.append("hotel")

    # Fallback: "vamos desde las islas" / "ya estoy en la isla" / "estamos
    # en las islas" / EN "we are on the islands" / "from the islands" — no
    # specific island/hotel named, but a real bug seen live on PRE
    # (2026-07-09): with no generic pattern here, this message never set
    # location, so the bot kept re-asking "¿desde dónde sales?" even
    # though the customer had just answered it. Only checked when no
    # island/hotel/Cartagena match already fired above; leaves `island`
    # unset so the ISLAND_MENU step still asks which island (same as
    # clicking "🏝️ Ya estoy en las islas").
    # "los rosarios" / EN "the rosarios" — informal plural nickname for
    # the whole archipelago (found via web search 2026-07-09). Deliberately
    # NOT matching the singular "el rosario": in Colombia that phrase
    # overwhelmingly means the Catholic prayer ("rezar el rosario"), not
    # the islands — too risky to treat as a location signal. The plural
    # (ES and EN) is unambiguous.
    if not intent.location and (
        re.search(r'\b(?:desde|en)\s+las?\s+islas?\b', msg_lower)
        or re.search(r'\b(?:from|on|at)\s+the\s+islands?\b', msg_lower)
        or re.search(r'\blos\s+rosarios\b', msg_lower)
        or re.search(r'\bthe\s+rosarios\b', msg_lower)
    ):
        intent.location = "island"
        intent.detected_fields.append("location")
    # Cartagena Y una isla en el mismo mensaje: el papel de cada lugar (`place_by_role`).
    if _CARTAGENA_NAME_RE.search(msg_lower) and (intent.island or names_an_island or names_the_archipelago):
        place = place_by_role(msg_lower, lodging_island=bool(intent.hotel and intent.island))
        if place == "cartagena":
            intent.location, intent.island = "cartagena", None
            intent.detected_fields = [f for f in intent.detected_fields if f != "island"]
        elif place == "island":
            intent.location = "island"
        if place and "location" not in intent.detected_fields:
            intent.detected_fields.append("location")


def lectura_del_turno(message: str) -> DetectedIntent:
    """lat-11 T6a (26-oct): lo poco del regex que el turno sigue usando junto al extractor: la cifra de inmersiones o de
    días (`detect_cert_dive_count`/`detect_cert_day_count`), las edades y la duración (cuentan si el extractor falla)
    y el lugar (la pista de isla y hotel del catálogo, `lugares.json`). Lo demás que leía `IntentDetector.detect`
    (actividad, certificación, grupo, última inmersión, nacionalidad) lo decide el extractor y se quitaba con
    `_quitar_provisional`; el idioma lo fija la apertura (`idioma_de_apertura`)."""
    intent = DetectedIntent()
    message_lower = message.lower().strip()
    intent.cert_dives = detect_cert_dive_count(message_lower)
    if intent.cert_dives is None:
        intent.cert_days = detect_cert_day_count(message_lower)
    detect_ages(message_lower, intent)
    detect_duration(message_lower, intent)
    detect_location(message_lower, intent)
    return intent


# A named PADI certification level. Holding ANY of these means you're a
# certified diver (Open Water is the entry level; the rest are above it).
_CERT_LEVEL = (
    r"(?:open[\s-]*water|advanced|rescue|dive\s*master|divemaster|"
    r"aguas\s+abiertas|nitrox)"
)
# Verbos de tener un nivel (hallazgo F.1, 2026-09-15): la posesion (tener, llevar) y
# haberlo hecho (hacer, sacar, terminar, completar), en primera y tercera persona.
# Antes solo "tengo/tenemos/tiene(n)": "ya llevo el rescue" o "hice mi open water"
# se tomaban por un nivel sin decir si lo tienen y el bot preguntaba de mas. Querer
# sacarlo (`_WANTS_CERT_RE`) sigue ganando: "hice el open water y quiero el advanced".
_HOLD_VERB_WRITER_ES = r"(?:tengo|tenemos|llevo|llevamos|hice|hicimos|saqu[eé]|termin[eé]|complet[eé])"
_HOLD_VERB_OTHER_ES = (
    r"(?:tienen?|llevan?|hizo|hicieron|sac[oó]|sacaron|termin[oó]|terminaron|complet[oó]|completaron)"
)
_HOLD_VERB_EN = r"(?:have|has|got|did|completed|finished|took)\s+(?:got\s+|done\s+|completed\s+|finished\s+)?"
# "I HAVE / I AM this cert" — status, not a course to take.
_HOLDS_WRITER = (
    r"\b(?:soy|somos|estoy|estamos)\s+(?:un[ao]?\s+|buz[oa]s?\s+)?"
    r"(?:certificad[oa]s?\s+(?:en|como)\s+)?" + _CERT_LEVEL + r"\b"
    r"|\b" + _HOLD_VERB_WRITER_ES + r"\s+(?:el\s+|la\s+|mi\s+|nuestr[oa]\s+|un[ao]?\s+)?" + _CERT_LEVEL + r"\b"
    r"|\bi(?:'?m|\s+am)\s+(?:an?\s+)?" + _CERT_LEVEL + r"\b"
    # "i already have my open water card" — the adverb between "i/we" and
    # "have" used to break the match, so the message was classified as
    # WANTING the Open Water course instead of holding it (real bug from
    # the Fase 6 battery — Fase 7, docs/robustness/plan.md).
    r"|\b(?:i|we)\s+(?:already\s+|now\s+|both\s+)?" + _HOLD_VERB_EN + r"(?:my\s+|our\s+|an?\s+|the\s+)?" + _CERT_LEVEL + r"\b"
    r"|\b" + _CERT_LEVEL + r"\s+(?:diver|certified)\b"
    r"|\bbuz[oa]\s+avanzad[oa]\b"
)
# Tercera persona con la persona nombrada (2026-09-15): "mi pareja tiene el
# advanced" salia curso Advanced. Sin persona, "¿tienen el advanced?" es preguntar
# si el centro lo ofrece, asi que la persona sale de la lista compartida de
# sustantivos. Dice que NO pide el curso, pero nada del estado de quien escribe.
_HOLDS_OTHER_PERSON = (
    r"\b(?:" + _PERSON_NOUN_SINGULAR_ES + r"|" + _PERSON_NOUN_PLURAL_ES + r")\s+(?:\w+\s+){0,2}?"
    + _HOLD_VERB_OTHER_ES + r"\s+(?:el\s+|la\s+|su\s+|un[ao]?\s+)?" + _CERT_LEVEL + r"\b"
    r"|\b(?:" + _PERSON_NOUN_SINGULAR_EN + r"|" + _PERSON_NOUN_PLURAL_EN + r")\s+(?:\w+\s+){0,2}?"
    + _HOLD_VERB_EN + r"(?:her\s+|his\s+|their\s+|an?\s+|the\s+)?" + _CERT_LEVEL + r"\b"
)
_HOLDS_CERT_RE = re.compile(_HOLDS_WRITER + r"|" + _HOLDS_OTHER_PERSON, re.IGNORECASE)
# "I WANT / I'm doing the <level> COURSE" — wants the certification, so NOT
# certified yet. Requires the want-verb to be followed by the cert level so
# "quiero 2 inmersiones" (wanting dives) never counts as wanting a course.
_WANTS_CERT_RE = re.compile(
    r"\b" + _WANT_VERB + _WANT_OBJECT_PREFIX + r"(?:" + _CERT_LEVEL + r"|" + _CERT_NOUN + r")"
    + r"|\bcurso\s+(?:de\s+)?(?:padi\s+)?" + _CERT_LEVEL
    + r"|\bcertificar(?:me|nos|te|se)\b|\bget\s+certified\b",
    re.IGNORECASE,
)
