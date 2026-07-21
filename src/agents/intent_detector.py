import re
from dataclasses import dataclass, field

from openai import OpenAI

from src.flows.decision_tree import ConversationState


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
    confidence: float = 0.0
    detected_fields: list = field(default_factory=list)


# Explicit certified dive-count: "2 inmersiones", "paquete de 5 buceos",
# "7 buceos en 3 dias", "2-dive package". The number must sit right before a
# dive noun so "hace 2 años sin bucear" (a timeframe, not a count) never matches.
_CERT_DIVE_COUNT_RE = re.compile(
    r"\b(\d+|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|"
    r"one|two|three|four|five|six|seven|eight|nine)"
    r"[\s\-]+(?:inmersi\w+|buceos?|dives?|immersions?)\b",
    re.IGNORECASE,
)
_DIVE_WORD_TO_NUM = {
    "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

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
_BARE_PACKAGE_DIVE_RE = re.compile(
    r"\b(?:paquete|pack|plan)\s+de\s+(5|7|9|cinco|siete|nueve)\b(?!\s*d[ií]as?)"
    r"|\b(?:package|pack|plan)\s+of\s+(5|7|9|five|seven|nine)\b(?!\s*days?)",
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
_CERT_DAY_COUNT_RE = re.compile(
    r"\b(?:paquete|pack|plan)\s+de\s+(\d+|un[oa]?|dos|tres|cuatro)\s*d[ií]as?\b"
    r"|\b(\d+|un[oa]?|dos|tres|cuatro)[\s\-]+d[ií]as?\s+(?:de\s+)?buce\w*\b"
    r"|\b(\d+|one|two|three|four)[\s\-]?days?\s+(?:of\s+)?(?:dive\s+|diving\s+)?package\b"
    r"|\b(\d+|one|two|three|four)[\s\-]?days?\s+(?:of\s+)?div(?:e|ing)\b",
    re.IGNORECASE,
)


def detect_cert_dive_count(message: str) -> int | None:
    """Requested certified dive-count as a real package size (2/3/4/5/7/9), or None.
    Shared by the intent detector and the cart's cert-plan step so a natural-language
    "2 buceos" is understood in both places."""
    message = message or ""
    match = _CERT_DIVE_COUNT_RE.search(message)
    if match:
        token = match.group(1).lower()
        n = int(token) if token.isdigit() else _DIVE_WORD_TO_NUM.get(token)
        return n if n in (2, 3, 4, 5, 7, 9) else None
    match = _BARE_PACKAGE_DIVE_RE.search(message)
    if match:
        token = next(g for g in match.groups() if g is not None).lower()
        n = int(token) if token.isdigit() else _DIVE_WORD_TO_NUM.get(token)
        return n if n in (5, 7, 9) else None
    return None


def detect_cert_day_count(message: str) -> int | None:
    """Requested certified package duration in days (1/2/3/4), inferred from
    explicit day-count phrasing rather than a dive count. None if absent/
    unrecognized. Shared by the intent detector and the cart's cert-plan step."""
    match = _CERT_DAY_COUNT_RE.search(message or "")
    if not match:
        return None
    token = next(g for g in match.groups() if g is not None).lower()
    n = int(token) if token.isdigit() else _DIVE_WORD_TO_NUM.get(token)
    return n if n in (1, 2, 3, 4) else None


class IntentDetector:

    def __init__(self, openai_client: OpenAI | None = None):
        self.openai_client = openai_client

    def detect(self, message: str, state: ConversationState) -> DetectedIntent:
        intent = DetectedIntent()
        message_lower = message.lower().strip()

        self._detect_language(message_lower, intent)
        self._detect_activity(message_lower, intent, state)
        # Explicit dive-count ("2 inmersiones", "paquete de 5 buceos"). Computed
        # regardless of the detected activity because the certified flow is often
        # entered via is_certified alone; only consumed at the cert entry point.
        intent.cert_dives = self._detect_cert_dive_count(message_lower)
        # Day-count phrasing ("paquete de 3 dias") as a fallback when no explicit
        # dive-count was given — dive-count wins when both are somehow present.
        if intent.cert_dives is None:
            intent.cert_days = detect_cert_day_count(message_lower)
        self._detect_certification(message_lower, intent)
        self._detect_group_info(message_lower, intent)
        self._detect_ages(message_lower, intent)
        self._detect_last_dive(message_lower, intent)
        self._detect_duration(message_lower, intent)
        self._detect_location(message_lower, intent)
        self._detect_nationality(message_lower, intent)

        # Certification ("certificado"/"no certificado") is a diving-only
        # concept in this business — if the message mentions it but never
        # says "buceo"/"dive" explicitly (e.g. "somos 2 y uno no esta
        # certificado"), infer the activity instead of leaving it ambiguous,
        # so the booking flow still asks for what's missing (location, etc.)
        # instead of falling through to a generic LLM answer.
        if intent.activity is None and intent.is_certified is not None:
            intent.activity = "certified_diving"
            intent.detected_fields.append("activity")

        self._split_out_uncertifiable_kids(intent)

        self._calculate_confidence(intent)

        return intent

    # PADI Open Water (the entry certification) has a minimum age of 10, so a
    # child under 10 can NEVER be a certified diver. This is a hard, unambiguous
    # rule (no false positives) — unlike guessing whether a teenager is certified.
    _MIN_CERTIFIED_AGE = 10

    def _split_out_uncertifiable_kids(self, intent: "DetectedIntent") -> None:
        """When a group is tagged certified but includes kids too young to hold a
        certification (detected age < 10), split those kids out as non-certified
        so the flow handles them by age (snorkel / Bubble Makers) instead of
        counting them as certified divers.

        E.g. "familia de 5: papá y mamá certificados, 3 niños de 6, 9 y 13" — the
        6- and 9-year-olds cannot be certified, so it becomes 3 certified + 2
        beginners (the flow then adapts each kid by age). Only the under-10 kids
        are moved; a 13-year-old CAN be certified, so it's left in the cert count.
        """
        if intent.is_certified is not True:
            return
        if intent.group_allocation is not None:
            return  # respect an explicit split already parsed
        if not intent.group_size or not intent.ages:
            return
        young = [a for a in intent.ages if a < self._MIN_CERTIFIED_AGE]
        if not young or intent.group_size <= len(young):
            return
        cert_qty = intent.group_size - len(young)
        intent.group_allocation = {"certified_diving": cert_qty, "minicourse": len(young)}
        if "group_allocation" not in intent.detected_fields:
            intent.detected_fields.append("group_allocation")

    def _detect_language(self, message: str, intent: DetectedIntent) -> None:
        spanish_keywords = {
            'hola', 'quiero', 'buceo', 'snorkel', 'curso', 'minicurso',
            'certificado', 'somos', 'personas', 'día', 'días', 'inmersión',
            'buzo', 'bautismo', 'precio', 'información', 'reservar',
            # common function words / verbs that disambiguate ES vs EN
            'estoy', 'recogen', 'puedo', 'gracias', 'cuánto', 'dónde', 'está',
            # unambiguously-Spanish function words: keep a Spanish question with an
            # English activity name ("¿qué es el Mindful Diving?") from being
            # flagged as English just because it contains "diving".
            'qué', 'que', 'es', 'el', 'la', 'los', 'las', 'del', 'para', 'con',
            'cómo', 'como', 'cuál', 'cual', 'una', 'más', 'sí', 'tú', 'y', 'o',
        }

        english_keywords = {
            'hello', 'hi', 'want', 'diving', 'dive', 'snorkel', 'course',
            'certified', 'people', 'day', 'days', 'price', 'information',
            'book', 'booking', 'diver', 'beginner',
            'can', 'you', 'the', 'my', 'how', 'where', 'much', 'pick',
        }

        # Match whole words only. Substring matching wrongly flags e.g. "ahi"
        # (Spanish) as English because it contains "hi".
        words = set(re.findall(r"[a-zá-úñü]+", message.lower()))
        spanish_count = len(words & spanish_keywords)
        english_count = len(words & english_keywords)

        if spanish_count > english_count and spanish_count > 0:
            intent.language = "es"
            intent.detected_fields.append("language")
        elif english_count > spanish_count and english_count > 0:
            intent.language = "en"
            intent.detected_fields.append("language")

    def _detect_activity(self, message: str, intent: DetectedIntent, state: ConversationState) -> None:
        # "solo snorkel" / "no quiero bucear, solo snorkel" must resolve to snorkel,
        # not diving — the bare verb "bucear" would otherwise win the diving branch.
        if re.search(r'e?snork\w*', message) and (
            re.search(r'\b(?:solo|solamente|s[oó]lo|only|just)\s+(?:quiero\s+|want\s+(?:to\s+)?|hacer\s+|do\s+)?e?snork', message)
            or re.search(r'\bno\s+(?:quiero\s+)?buce\w*', message)
            or re.search(r"\bdon'?t\s+want\s+to\s+dive\b", message)
        ):
            intent.activity = "snorkel"
            intent.service_id = "snorkeling"
            intent.detected_fields.append("activity")
            return

        certified_diving_patterns = [
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

        minicourse_patterns = [
            r'\bmini[\s\-]?curso\b',       # minicurso, mini curso, mini-curso
            r'\bbubble\s?makers?\b',       # Bubble Makers = kids intro dive (beginner, not certified)
            r'\bbautizo\s+de\s+buceo\b',
            r'\bbauti[sz]\w{0,3}\b',       # bautismo, bautizo, bautismos, bautizos
            r'\bprimera\s+vez\b',
            r'\bnunca\s+(?:\w+\s+){0,3}buce\w*\b',  # nunca he/ha/hemos/han (hecho) bucea(do)/buceo
            r'\bnever\s+(?:tried|dived|done\s+it|been\s+diving)\b',
            r'\bno\s+experience\b',
            r'\bsin\s+experiencia\b',
            r'\bdiscover\s+scuba\b',
            r'\bbeginner\s+dive\b',
            r'\bfirst\s+time\s+diving\b',
            r'\btry\s+dive',
            r'\bno\s+s[eé]\s+bucear\b',   # "no sé bucear"
        ]

        snorkel_patterns = [
            r'\be?snork\w{1,6}\b',         # snorkel, snorkeling, snorkle, esnorkel, esnorkeling
            r'\be?snorqu\w{0,6}\b',        # snorquel, snorqueling, esnorquel, esnorqueling
            r'\bcarete[ao]\w{0,3}\b',      # careteo, caretear
        ]

        padi_course_patterns = [
            r'\bcurso\s+padi\b',
            r'\bpadi\s+course\b',
            r'\bopen\s+water\b',
            r'\badvanced\b',
            r'\brescue\b',
            r'\bdivemaster\b',
            r'\bcertificarme\b',
            r'\bget\s+certified\b',
        ]

        specialty_patterns = [
            r'\bnitrox\b',
            r'\bbuoyancy\b',
            r'\bflotabilidad\b',
            r'\bnaturalista\b',
            r'\bfish\s+identification\b',
            r'\bidentificación\s+de\s+peces\b',
            r'\bmindful\s+diving\b',
        ]

        if any(re.search(pattern, message) for pattern in minicourse_patterns):
            intent.activity = "minicourse"
            intent.service_id = "minicourse"
            intent.is_certified = False
            intent.detected_fields.extend(["activity", "is_certified"])
        elif any(re.search(pattern, message) for pattern in certified_diving_patterns):
            intent.activity = "certified_diving"
            intent.service_id = "2_dives_1_day"
            intent.detected_fields.append("activity")
        elif any(re.search(pattern, message) for pattern in snorkel_patterns):
            intent.activity = "snorkel"
            intent.service_id = "snorkeling"
            intent.detected_fields.append("activity")
        elif any(re.search(pattern, message) for pattern in padi_course_patterns) and not self._holds_padi_cert(message):
            # Only a COURSE if they want to take it — "soy open water" (holds it)
            # is a certified diver, handled via is_certified + the activity fallback.
            if 'open water' in message or 'open-water' in message:
                intent.activity = "padi_open_water"
                intent.service_id = "open_water"
            elif 'advanced' in message:
                intent.activity = "padi_advanced"
                intent.service_id = "advanced"
            elif 'rescue' in message:
                intent.activity = "padi_rescue"
                intent.service_id = "rescue"
            elif 'divemaster' in message or 'dive master' in message:
                intent.activity = "padi_divemaster"
                intent.service_id = "divemaster"
            else:
                intent.activity = "padi_course"
            intent.detected_fields.append("activity")
        elif any(re.search(pattern, message) for pattern in specialty_patterns):
            intent.activity = "padi_specialty"
            if 'nitrox' in message:
                intent.service_id = "nitrox"
            elif 'buoyancy' in message or 'flotabilidad' in message:
                intent.service_id = "buoyancy"
            elif 'naturalist' in message or 'naturalista' in message:
                intent.service_id = "naturalist"
            elif 'fish' in message or 'peces' in message:
                intent.service_id = "fish_identification"
            elif 'mindful' in message:
                intent.service_id = "mindful_diving"
            intent.detected_fields.append("activity")

    def _detect_cert_dive_count(self, message: str) -> int | None:
        return detect_cert_dive_count(message)

    # A named PADI certification level. Holding ANY of these means you're a
    # certified diver (Open Water is the entry level; the rest are above it).
    _CERT_LEVEL = (
        r"(?:open[\s-]*water|advanced|rescue|dive\s*master|divemaster|"
        r"aguas\s+abiertas|nitrox)"
    )
    # "I HAVE / I AM this cert" — status, not a course to take.
    _HOLDS_CERT_RE = re.compile(
        r"\b(?:soy|somos|estoy|estamos)\s+(?:un[ao]?\s+|buz[oa]s?\s+)?"
        r"(?:certificad[oa]s?\s+(?:en|como)\s+)?" + _CERT_LEVEL + r"\b"
        r"|\b(?:tengo|tenemos)\s+(?:el\s+|la\s+|mi\s+|un[ao]?\s+)?" + _CERT_LEVEL + r"\b"
        r"|\bi(?:'?m|\s+am)\s+(?:an?\s+)?" + _CERT_LEVEL + r"\b"
        r"|\bi\s+have\s+(?:my\s+|an?\s+)?" + _CERT_LEVEL + r"\b"
        r"|\b" + _CERT_LEVEL + r"\s+(?:diver|certified)\b"
        r"|\bbuz[oa]\s+avanzad[oa]\b",
        re.IGNORECASE,
    )
    # "I WANT / I'm doing the <level> COURSE" — wants the certification, so NOT
    # certified yet. Requires the want-verb to be followed by the cert level so
    # "quiero 2 inmersiones" (wanting dives) never counts as wanting a course.
    _WANTS_CERT_RE = re.compile(
        r"\b(?:quiero|queremos|quisiera|me\s+gustar[ií]a|hacer(?:me)?|sacar(?:me)?|"
        r"obtener|tomar)\s+(?:el\s+|la\s+|mi\s+|un\s+|hacer\s+|the\s+)*"
        r"(?:curso\s+)?(?:padi\s+)?(?:de\s+)?" + _CERT_LEVEL
        + r"|\bcurso\s+(?:de\s+)?(?:padi\s+)?" + _CERT_LEVEL
        + r"|\bcertificar(?:me|nos)\b|\bget\s+certified\b"
        + r"|\bwant\s+to\s+(?:do|take|get)\s+(?:the\s+)?(?:padi\s+)?" + _CERT_LEVEL,
        re.IGNORECASE,
    )

    def _holds_padi_cert(self, message: str) -> bool:
        """True if the message says the person HOLDS a PADI cert level (certified
        diver), as opposed to wanting to take that course."""
        if self._WANTS_CERT_RE.search(message):
            return False
        return bool(self._HOLDS_CERT_RE.search(message))

    def _detect_certification(self, message: str, intent: DetectedIntent) -> None:
        if intent.is_certified is not None:
            return

        certified_patterns = [
            r'\bcertificado\b',
            r'\bcertificados\b',
            r'\bcertified\b',
            r'\bcertificaci[oó]n\b',
            r'\bestamos\s+certificados\b',
            r'\bsomos\s+certificados\b',
            r'\btengo\s+licencia\b',
            r'\btenemos\s+licencia\b',
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
            # Typo-tolerant fallback: matches "certficado", "certifcado",
            # "certificacion", "certified"... anything starting with "cert".
            # Checked LAST so the more specific not_certified_patterns below
            # (which also start with "cert") always get first chance.
            r'\bcert\w*\b',
        ]

        not_certified_patterns = [
            r'\bno\s+(?:esta\s+|estoy\s+|estamos\s+|est[aá]n\s+|soy\s+|somos\s+|es\s+|son\s+|eres\s+|fui\s+)?cert\w*\b',
            r'\bno\s+(?:soy|somos|son|es)\s+buz',   # "no somos buzos" = not certified
            r'\b(?:ser|hacerme|hacernos|convertirme|convertirnos)\s+(?:en\s+)?buz',  # wants to BECOME a diver
            r'\bsin\s+cert\w*\b',
            # Reflexive "certificarme/certificarnos/certificarte/certificarse" =
            # wants to GET certified (Open Water course), so NOT yet certified.
            # Must be listed here (checked before the generic \bcert\w*\b catch-all).
            r'\bcertificar(?:me|nos|te|se)\b',
            r'\bquiero\s+(?:sacar|obtener|hacer)\s+(?:el\s+|la\s+|mi\s+)?(?:open\s+water|certificaci|licencia)\w*\b',
            r'\bget\s+certified\b',
            r'\bnunca\s+(?:\w+\s+){0,3}buce\w*\b',  # nunca he/ha/hemos/han (hecho) bucea(do)/buceo
            r'\bprimera\s+vez\b',
            # Typo-tolerant (real bug live 2026-07-21: "not certfied" matched
            # neither this pattern nor the exact positive "certified_patterns"
            # entry, and fell through to that list's own typo-tolerant
            # \bcert\w*\b catch-all, wrongly resolving to is_certified=True).
            r'\bnot\s+cert\w*\b',
            r'\bnever\s+dived\b',
            r'\bfirst\s+time\b',
            r'\bbeginner\b',
            r'\bprincipiante\b',
        ]

        if any(re.search(pattern, message) for pattern in not_certified_patterns):
            intent.is_certified = False
            intent.detected_fields.append("is_certified")
        elif any(re.search(pattern, message) for pattern in certified_patterns) or self._holds_padi_cert(message):
            # Holding a PADI level (Open Water / Advanced / Rescue / Divemaster /
            # Nitrox) means the person is a certified diver.
            intent.is_certified = True
            intent.detected_fields.append("is_certified")

    def _detect_group_info(self, message: str, intent: DetectedIntent) -> None:
        # Fixed 2026-07-08: the verb-split patterns below (pat_numeric_fwd/rev,
        # "N bucean y M hacen snorkel") used to require the activity keyword to
        # sit right next to the split clause. Inserting an explicit dive/day
        # count in between broke the match — e.g. "somos 5, 3 buceamos
        # certificados 5 inmersiones y 2 hacen snorkel" produced no
        # group_allocation at all (falling through to supervisor.py's
        # _should_skip_to_certified_flow, which then silently treated the
        # WHOLE group as certified divers, dropping the 2 snorkelers). Now an
        # optional trailing count phrase ("5 inmersiones", "2 dias", "3 dives")
        # is allowed between the first activity clause and the "y/and" split —
        # see `_split_infix` below.
        #
        # "3 buceadoras y 2 buceadores" / "2 buzas y 1 buzo" — gendered variants
        # of the SAME noun (no certification/activity split implied). Must run
        # BEFORE the generic "somos N" pattern below, which would otherwise
        # match only the first number and stop (T165 in
        # docs/test-battery-edge-cases.md: summed to 3 instead of 5).
        _gendered_diver_noun = r'(?:buceador[ae]s?|buz[oa]s?|buseador[ae]s?)'
        m_gendered_sum = re.search(
            rf'\b(\d+)\s+{_gendered_diver_noun}\s+y\s+(\d+)\s+{_gendered_diver_noun}\b',
            message, re.IGNORECASE,
        )
        if m_gendered_sum:
            intent.group_size = int(m_gendered_sum.group(1)) + int(m_gendered_sum.group(2))
            intent.detected_fields.append("group_size")

        # Word-form numbers used to stop at "ocho"/"eight" (8) in these
        # patterns while every other number-word map in this file already
        # goes to "diez"/"ten" — "somos nueve"/"somos diez" silently resolved
        # to no group size at all (digits like "9"/"10" still worked).
        _es_word_nums = {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10}
        _en_word_nums = {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
        _es_word_alt = r'dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez'
        _en_word_alt = r'two|three|four|five|six|seven|eight|nine|ten'
        group_size_patterns = [
            (rf'\bsomos\s+(\d+|{_es_word_alt})\b', _es_word_nums),
            (rf'\bvenimos\s+(\d+|{_es_word_alt})\b', _es_word_nums),
            (rf'\bvamos\s+(\d+|{_es_word_alt})\b', _es_word_nums),
            (rf'\bwe\s+are\s+(\d+|{_en_word_alt})\b', _en_word_nums),
            (r'\b(\d+)\s+of\s+us\b', {}),
            (rf'\bgroup\s+of\s+(\d+|{_en_word_alt})\b', _en_word_nums),
            (r'\b(\d+)\s+(personas?|people|person|friends|amig[oa]s|friend|compañer[oa]s|companer[oa]s|acompañantes|acompanantes|divers?|buzos?|buceador[ae]s?)\b', {}),
            # "2 certified divers" / "3 certified" — a count directly before a
            # certification word (EN+ES) is a group size.
            (r'\b(\d+)\s+(?:certified|certificad[oa]s)\b', {}),
            # "una pareja" / "somos pareja" → 2 (capturing group required by loop)
            (r'\b(?:somos\s+)?(?:una?\s+)?(pareja)\b', {'pareja': 2}),
            # "familia de N" → N personas
            (rf'\bfamilia\s+de\s+(\d+|{_es_word_alt})\b', _es_word_nums),
            (rf'\bfamily\s+of\s+(\d+|{_en_word_alt})\b', _en_word_nums),
        ]

        if not m_gendered_sum:
            for pattern, word_map in group_size_patterns:
                match = re.search(pattern, message)
                if match:
                    size_str = match.group(1)
                    if size_str.isdigit():
                        intent.group_size = int(size_str)
                    elif size_str in word_map:
                        intent.group_size = word_map[size_str]

                    if intent.group_size:
                        intent.detected_fields.append("group_size")
                        break

        # Singular first-person self-reference → 1 person, but ONLY when the message
        # names no companion, no other headcount number, and no plural/collective
        # marker. A wrong 1 would undercount the booking, so every "more than one"
        # hint keeps us conservative and lets the flow ask.
        if intent.group_size is None:
            solo_self = re.search(
                r'\b(?:para\s+m[ií]|s[oó]lo\s+yo|solo\s+yo|solamente\s+yo|just\s+me|only\s+me|for\s+me)\b',
                message,
            )
            # A SINGULAR declaration of being a diver ("soy Sofia, ya soy certificada",
            # "soy buzo", "estoy certificado", "i am a certified diver") is a strong
            # 1-person signal — it was the reported miss: the bot asked "¿cuántas
            # personas?" to someone who clearly spoke for herself alone.
            singular_diver = re.search(
                r'\b(?:soy|estoy|i\s*am|i\'m)\s+(?:un[ao]?\s+|a\s+|buz[oa]s?\s+)?'
                r'(?:buz[oa]|certificad[oa]|certified|open\s*water|advanced|rescue|'
                r'divemaster|nitrox|diver)\b',
                message, re.IGNORECASE,
            )
            companion = re.search(
                r'\b(?:y\s+mi\b|and\s+my\b|con\s+mi\b|junto\s+a|'
                r'mi\s+(?:novi[oa]|espos[oa]|pareja|hij[oa]s?|amig[oa]s?|herman[oa]s?|mam[aá]|pap[aá]|familia)|'
                r'my\s+(?:girlfriend|boyfriend|wife|husband|partner|kids?|son|daughter|friend|brother|sister|family|mom|dad))\b',
                message,
            )
            other_num = re.search(
                r'\b([2-9]|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|'
                r'two|three|four|five|six|seven|eight|nine)\b',
                message,
            )
            # Any plural first-person or collective noun means "not just me".
            plural_self = re.search(
                r'\b(?:somos|estamos|queremos|venimos|vamos|seremos|iremos|'
                r'nuestr[oa]s?|nos\s+gustar[ií]a|we\s+are|we\'re|we\s+want)\b',
                message, re.IGNORECASE,
            )
            collective = re.search(
                r'\b(?:familia|grupo|pareja|gente|personas?|amig[oa]s|compa[nñ]er\w*|'
                r'todos|equipo|family|group|friends|couple|people)\b',
                message, re.IGNORECASE,
            )
            if (solo_self or singular_diver) and not companion and not other_num \
                    and not plural_self and not collective:
                intent.group_size = 1
                intent.detected_fields.append("group_size")

        # ── Numeric split: "3 de buceo y 2 de snorkel", "5 snorkel y 2 buceo" ──
        activity_kw = r'(buce\w*|buse\w*|snorkel|snorkeling|esnorkel|careteo|caretear|minicurso|mini\s?curso|bautismo|bautizo|diving|scuba|submarinismo)'
        num_pat = r'(\d+|dos|tres|cuatro|cinco|seis|two|three|four|five|six)'
        _word_num_map: dict[str, int] = {
            'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
        }

        def _parse_num(s: str) -> int:
            return int(s) if s.isdigit() else _word_num_map.get(s, 1)

        def _activity_key(text: str) -> str | None:
            if any(k in text for k in ('minicurso', 'mini curso', 'bautismo', 'bautizo', 'discover', 'principiante')):
                return 'minicourse'
            if any(k in text for k in ('snorkel', 'esnorkel', 'careteo', 'snorkeling')):
                return 'snorkel'
            if any(k in text for k in ('buce', 'buse', 'dive', 'diving', 'certificado', 'certified', 'scuba', 'submarinismo')):
                return 'certified_diving'
            return None

        # Pattern A: "3 de buceo y 2 de snorkel" / "3 buceos y 2 snorkel"
        # También cubre "buceo 3 y snorkel 2" (número después del keyword)
        # y "3 for diving and 2 for snorkel" (inglés)
        # y "2 queremos hacer buceo y 1 snorkel" / "2 hacen snorkel y 3 buceo"
        sep_pat = r'\s+(?:y|and|,)\s+'
        # Optional count phrase that may sit between the first activity clause
        # and the "y/and" split ("...certificados 5 inmersiones y 2 hacen
        # snorkel", "...diving 3 dives and 2 snorkel").
        _split_infix = r'(?:\s+\d+\s+(?:inmersi\w*|buceos?|d[ií]as?|dives?|days?))?'
        # Verb fillers: "hacen", "harán", "quieren hacer", "queremos hacer", "vamos a hacer", etc.
        verb_filler = (
            r'(?:'
            r'(?:queremos?|quieren?|hacemos?|hacen?|hago|hace|haremos?|har[aá]n?)\s+(?:hacer\s+)?'
            r'|vamos?\s+a\s+(?:hacer\s+)?'
            r')?'
        )
        # Prefix: "N de", "N para", "N personas", "N hacen", or bare "N "
        quant_prefix = rf'{num_pat}\s+(?:de\s+|para\s+|for\s+|personas?\s+(?:de\s+|para\s+|for\s+)?|{verb_filler})'
        pat_numeric_fwd = (
            rf'{quant_prefix}{activity_kw}(?:\s+certificad[ao]s?)?'
            rf'{_split_infix}'
            rf'{sep_pat}'
            rf'{quant_prefix}{activity_kw}(?:\s+certificad[ao]s?)?'
        )
        pat_numeric_rev = (
            rf'{activity_kw}(?:\s+certificad[ao]s?)?\w*\s+{num_pat}'
            rf'{_split_infix}'
            rf'{sep_pat}'
            rf'{activity_kw}(?:\s+certificad[ao]s?)?\w*\s+{num_pat}'
        )
        # ── Pattern B (priority): cert/no-cert splits — BEFORE numeric split ──
        # "2 buceadores (1 certificado y otro no)" / "N cert y M principiante"
        word_num = r'(\d+|un[ao]?|dos|tres|cuatro|cinco|seis|one|two|three|four|five|six)'
        cert_split_patterns = [
            # "2 buceadores (1 certificado y otro/s no)" / "4 buceadores (2 cert y 2 no)"
            rf'(\d+)\s+buceador[aes]*[^,\(]*[\(,]\s*{word_num}\s+certificad[ao]s?\s+y\s+(?:{word_num}\s+)?(?:el\s+)?otr[ao]s?\s+no',
            # "4 buceadores (2 certificados y 2 no)" — with explicit "2 no"
            rf'(\d+)\s+buceador[aes]*[^,\(]*[\(,]\s*{word_num}\s+certificad[ao]s?\s+y\s+{word_num}\s+no\b',
            # "N certificados y M no certificados/principiantes"
            r'(\d+)\s+certificad[ao]s?\s+y\s+(\d+)\s+(?:no\s+certificad[ao]s?|principiantes?|sin\s+certificar)',
            # "uno certificado y dos minicurso" (palabras)
            rf'{word_num}\s+certificad[ao]s?\s+y\s+{word_num}\s+(?:minicurso|bautismo|no\s+certificad[ao]|principiante)',
            # "N buceo certificado y M minicurso/no certificado"
            r'(\d+)\s+(?:de\s+)?buceo\s+certificado\s+y\s+(\d+)\s+(?:minicurso|no\s+certificad[ao]|principiante|bautismo)',
            # "somos N, M certificados y el/los otro/s no"
            r'(\d+)\s+certificad[ao]s?\s+y\s+(?:el\s+)?otr[ao]s?\s+(?:\d+\s+)?(?:no|sin\s+certific)',
            # English: "N certified and M not certified/beginners"
            r'(\d+)\s+certified\s+and\s+(\d+)\s+(?:not\s+certified|beginners?|uncertified)',
            # "dos tenemos (el) open water y una no / sin certificar" / "2 con open water y 1 no"
            rf'{word_num}\s+(?:tenemos|tienen|tiene|tengo|con|somos)\s+'
            rf'(?:el\s+|la\s+|los\s+|las\s+|nuestro\s+)?'
            rf'(?:open\s*water|advanced|rescue|divemaster|licencia|certificad[ao]s?|padi|ssi|cmas|naui)\b'
            rf'[^,.;]*?\s+y\s+{word_num}\s+(?:no\b|sin\s+certific|no\s+certific)',
            # English: "two have (their) open water and one doesn't/does not/not"
            rf'{word_num}\s+(?:have|with|are)\s+(?:their\s+|the\s+)?'
            rf'(?:open\s*water|advanced|rescue|certified|padi|ssi)\b'
            rf'[^,.;]*?\s+and\s+{word_num}\s+(?:no|not|doesn\'?t|does\s+not|don\'?t|do\s+not)\b',
        ]
        for pat_idx, pat in enumerate(cert_split_patterns):
            m_split = re.search(pat, message, re.IGNORECASE)
            if m_split:
                g = m_split.groups()
                n1_raw = g[0]
                # Para pat 0: g = (total, cert, maybe_beg_qty)
                # Para pat 2 (palabras): g = (cert_word, beg_word) — sin grupo total
                n2_raw = g[1] if len(g) > 1 else None
                n1 = _parse_num(n1_raw) if n1_raw else 1
                n2 = _parse_num(n2_raw) if n2_raw else 1

                if pat_idx in (0, 1):
                    # "N buceadores (M cert y [K] otros/K no)" — n1=total, n2=cert
                    total = n1
                    cert_n = n2
                    # si hay tercer grupo (K no cert), usarlo; si no, resto
                    n3_raw = g[2] if len(g) > 2 else None
                    if n3_raw and re.match(r'\d+|dos|tres|cuatro|cinco|seis', n3_raw, re.IGNORECASE):
                        beg_n = _parse_num(n3_raw)
                        total = cert_n + beg_n
                    else:
                        beg_n = total - cert_n
                elif pat_idx == 3:
                    # "uno certificado y dos minicurso" — n1=cert_word, n2=beg_word
                    cert_n = n1
                    beg_n = n2
                    total = cert_n + beg_n
                else:
                    cert_n = n1
                    beg_n = n2 if n2 > 0 else (intent.group_size - cert_n if intent.group_size else 1)
                    total = cert_n + beg_n

                if cert_n > 0 and beg_n > 0:
                    intent.group_allocation = {'certified_diving': cert_n, 'minicourse': beg_n}
                    intent.group_size = total
                    intent.detected_fields.append("group_allocation")
                break

        # "Somos 2 ... y uno no esta certificado" — only the NOT-certified count
        # is stated explicitly; the certified count is the complement against
        # the already-known group_size (typo-tolerant: "certficado" matches
        # cert\w*). Without this, a message that only describes who is NOT
        # certified (instead of spelling out "N certified and M not") never
        # resolves to a group_allocation and falls through to a generic answer.
        if not intent.group_allocation and intent.group_size:
            m_not_cert_only = re.search(
                rf'{word_num}\s+no\s+(?:esta[nb]?\s+|son\s+)?cert\w*\b'
                rf'|\b(?:y\s+)?(?:el\s+|la\s+)?otr[ao]s?\s+no\s+(?:esta[nb]?\s+)?cert\w*\b'
                rf'|{word_num}\s+(?:is|are)\s+not\s+cert\w*\b',
                message, re.IGNORECASE,
            )
            if m_not_cert_only:
                groups = m_not_cert_only.groups()
                beg_n = _parse_num(groups[0]) if groups and groups[0] else 1
                if 0 < beg_n < intent.group_size:
                    cert_n = intent.group_size - beg_n
                    intent.group_allocation = {'certified_diving': cert_n, 'minicourse': beg_n}
                    intent.detected_fields.append("group_allocation")

        # ── Pattern A: "3 de buceo y 2 de snorkel" / "buceo 3 y snorkel 2" ──
        if not intent.group_allocation:
            m_num = re.search(pat_numeric_fwd, message, re.IGNORECASE)
            m_num_r = re.search(pat_numeric_rev, message, re.IGNORECASE) if not m_num else None
            if m_num:
                qty1 = _parse_num(m_num.group(1))
                act1 = _activity_key(m_num.group(2).lower())
                qty2 = _parse_num(m_num.group(3))
                act2 = _activity_key(m_num.group(4).lower())
                if act1 and act2 and act1 != act2:
                    allocation: dict[str, int] = {}
                    allocation[act1] = allocation.get(act1, 0) + qty1
                    allocation[act2] = allocation.get(act2, 0) + qty2
                    intent.group_allocation = allocation
                    intent.group_size = sum(allocation.values())
                    intent.detected_fields.append("group_allocation")
            elif m_num_r:
                act1 = _activity_key(m_num_r.group(1).lower())
                qty1 = _parse_num(m_num_r.group(2))
                act2 = _activity_key(m_num_r.group(3).lower())
                qty2 = _parse_num(m_num_r.group(4))
                if act1 and act2 and act1 != act2:
                    allocation = {}
                    allocation[act1] = allocation.get(act1, 0) + qty1
                    allocation[act2] = allocation.get(act2, 0) + qty2
                    intent.group_allocation = allocation
                    intent.group_size = sum(allocation.values())
                    intent.detected_fields.append("group_allocation")

        # Pattern C: "somos N personas, M de buceo y el resto snorkel/minicurso"
        pat_rest = (
            r'somos\s+(\d+)\s*(?:personas?)?\s*[,;]?\s*'
            r'(\d+)\s+(?:de\s+)?(\w+(?:\s+\w+)?)\s+y\s+(?:el\s+)?rest[oa]s?\s+(?:de\s+)?(\w+)'
        )
        m_rest = re.search(pat_rest, message, re.IGNORECASE)
        if m_rest and not intent.group_allocation:
            total = int(m_rest.group(1))
            n1 = int(m_rest.group(2))
            act1 = _activity_key(m_rest.group(3).lower())
            act2 = _activity_key(m_rest.group(4).lower())
            n2 = total - n1
            if act1 and act2 and act1 != act2 and n1 > 0 and n2 > 0:
                intent.group_allocation = {act1: n1, act2: n2}
                intent.group_size = total
                intent.detected_fields.append("group_allocation")

        mixed_group_patterns = [
            # "yo quiero buceo certificado y mi novia snorkel" - captura hasta 3 palabras
            (r'\byo\s+(?:quiero|hago|haría|haré)\s+(?:el\s+)?(\w+(?:\s+\w+){0,2}?)\s+y\s+(?:mi\s+)?(?:novia|novio|amigo|amiga|pareja|compañero|compañera|él|ella)\s+(?:quiere|hace|haría|hará)?\s*(?:el\s+)?(\w+(?:\s+\w+){0,2})', 'es'),
            # "uno quiere buceo y el otro snorkel"
            (r'\b(?:uno|una)\s+(?:quiere|hace)\s+(?:el\s+)?(\w+(?:\s+\w+)?)\s+y\s+(?:el\s+otro|la\s+otra|otro|otra)\s+(?:el\s+)?(\w+(?:\s+\w+)?)', 'es'),
            # "yo buceo y mi novia snorkel" (sin verbo querer)
            (r'\byo\s+(?:buceo|snorkel|minicurso)\s+y\s+(?:mi\s+)?(?:novia|novio|amigo|amiga|pareja|compañero|compañera|él|ella)\s+(\w+)', 'es'),
            # English patterns
            (r'\bi\s+(?:want|do)\s+(\w+(?:\s+\w+)?)\s+and\s+(?:my\s+)?(?:girlfriend|boyfriend|friend|partner|he|she)\s+(?:wants|does)?\s*(\w+(?:\s+\w+)?)', 'en'),
            (r'\bone\s+(?:wants|does)\s+(\w+(?:\s+\w+)?)\s+and\s+(?:the\s+)?other\s+(\w+(?:\s+\w+)?)', 'en'),
        ]

        for pattern, lang in mixed_group_patterns:
            if intent.group_allocation:
                break  # Ya detectado por los patrones numéricos anteriores
            match = re.search(pattern, message)
            if match:
                activity1 = match.group(1).lower()
                try:
                    activity2 = match.group(2).lower()
                except IndexError:
                    activity2 = ""

                allocation = {}

                for activity_text in [activity1, activity2]:
                    # Primero verificar minicurso (tiene prioridad sobre buceo genérico)
                    if any(kw in activity_text for kw in ['minicurso', 'bautismo', 'discover', 'principiante']):
                        allocation['minicourse'] = allocation.get('minicourse', 0) + 1
                    # Luego snorkel
                    elif any(kw in activity_text for kw in ['snorkel', 'careteo']):
                        allocation['snorkel'] = allocation.get('snorkel', 0) + 1
                    # Finalmente buceo (certificado o genérico)
                    elif any(kw in activity_text for kw in ['buceo', 'dive', 'diving', 'certificado', 'certified']):
                        allocation['certified_diving'] = allocation.get('certified_diving', 0) + 1

                if allocation:
                    intent.group_allocation = allocation
                    if not intent.group_size:
                        intent.group_size = sum(allocation.values())
                    intent.detected_fields.append("group_allocation")
                    break

    def _detect_ages(self, message: str, intent: DetectedIntent) -> None:
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
            preceding = message[max(0, m.start() - 8):m.start()]
            if re.search(r'\b(hace|ultimo|ultima|last)\b', preceding):
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
        for m in re.finditer(
            r'\b(?:aged|ages|edad(?:es)?(?:\s+de)?)\s+((?:\d{1,2}\s*(?:,|y|e|and|&)\s*)*\d{1,2})',
            message,
        ):
            _add(m.group(1))
        # 5) English kid-noun + "are/is N and M": "our kids are 7 and 11".
        for m in re.finditer(
            r'\b(?:kids?|children|sons?|daughters?)\s+(?:are|is)\s+'
            r'((?:\d{1,2}\s*(?:,|and|&)\s*)*\d{1,2})',
            message,
        ):
            _add(m.group(1))

        if ages:
            intent.ages = sorted(set(ages))
            intent.detected_fields.append("ages")

    _LASTDIVE_NUM = {
        "un": 1, "uno": 1, "una": 1, "unos": 2, "unas": 2, "dos": 2, "tres": 3,
        "cuatro": 4, "cinco": 5, "seis": 6, "a": 1, "an": 1, "one": 1, "two": 2,
        "three": 3, "four": 4, "five": 5, "six": 6, "couple": 2, "few": 3,
    }

    def _last_dive_num(self, token: str) -> int:
        token = token.lower()
        return int(token) if token.isdigit() else self._LASTDIVE_NUM.get(token, 1)

    def _detect_last_dive(self, message: str, intent: DetectedIntent) -> None:
        """Capture whether the last dive was over 2 years ago (drives the refresher
        question). Only fires in a diving context so an unrelated "hace un mes"
        doesn't set it; harmless anyway since it's only used in the certified flow.
        """
        if intent.last_dive_over_2_years is not None:
            return
        # Must be talking about diving for this to be a last-dive statement.
        if not re.search(r"\b(buce\w*|inmersi\w+|dive\w*|dived|sin\s+bucear)\b", message):
            return

        num = r"(\d+|un[oa]?|unos|unas|dos|tres|cuatro|cinco|seis|a|an|one|two|three|four|five|six|couple|few)"

        # Explicitly recent -> NOT over 2 years.
        if re.search(
            r"\b(hace\s+poco|recientemente|el\s+mes\s+pasado|la\s+semana\s+pasada|"
            r"este\s+(?:mes|ano|año)|recently|last\s+month|last\s+week|just\s+dived|"
            r"a\s+few\s+months\s+ago|this\s+(?:month|year))\b",
            message,
        ):
            intent.last_dive_over_2_years = False
            intent.detected_fields.append("last_dive_over_2_years")
            return
        # "no hace más de N años" / "hace menos de N años" / "less than N years" -> NOT over.
        if re.search(
            r"\bno\s+(?:hace|llevo|llevamos|ha\s+pasado)\b.{0,20}\bm[aá]s\s+de\b"
            r"|\bhace\s+menos\s+de\b|\bmenos\s+de\s+\d+\s+a[nñ]os"
            r"|\bless\s+than\s+\d+\s+years?\b",
            message,
        ):
            intent.last_dive_over_2_years = False
            intent.detected_fields.append("last_dive_over_2_years")
            return
        # "más de N años" / "N años sin bucear" / "haven't dived in N years" -> over if N>=2.
        m_over = (
            re.search(rf"\bhace\s+m[aá]s\s+de\s+{num}\s+a[nñ]os", message)
            or re.search(rf"\b{num}\s+a[nñ]os\s+sin\s+bucear", message)
            or re.search(rf"\bllev\w+\s+{num}\s+a[nñ]os\s+sin\s+bucear", message)
            or re.search(rf"\bhaven'?t\s+dived\s+(?:in\s+)?{num}\s+years?", message)
            or re.search(rf"\bmore\s+than\s+{num}\s+years?\b", message)
        )
        if m_over:
            intent.last_dive_over_2_years = self._last_dive_num(m_over.group(1)) >= 2
            intent.detected_fields.append("last_dive_over_2_years")
            return
        # Generic "hace N año(s)/mes(es)" (digit or word), verb optional either side.
        m2 = (
            re.search(rf"\bhace\s+{num}\s+(a[nñ]os?|mes(?:es)?)", message)
            or re.search(rf"\b[uú]ltima\s+inmersi[oó]n\s+(?:fue\s+)?hace\s+{num}\s+(a[nñ]os?|mes(?:es)?)", message)
            or re.search(rf"\bdived\s+{num}\s+(years?|months?)\s+ago", message)
            or re.search(rf"\blast\s+dive\s+(?:was\s+)?{num}\s+(years?|months?)\s+ago", message)
        )
        if m2:
            n = self._last_dive_num(m2.group(1))
            unit = m2.group(2)
            if unit.startswith("a") or unit.startswith("y"):   # año(s) / year(s)
                intent.last_dive_over_2_years = n >= 2
            else:                                                # mes(es) / month(s)
                intent.last_dive_over_2_years = n >= 24
            intent.detected_fields.append("last_dive_over_2_years")

    def _detect_nationality(self, message: str, intent: DetectedIntent) -> None:
        """Capture nationality stated in the message (drives COP vs USD) so the
        checkout doesn't re-ask "¿eres colombiano?" when they already said it.
        Negation is checked first so "no soy colombiano" reads as NOT Colombian."""
        if intent.is_colombian is not None:
            return
        if re.search(
            r"\bextranjer[oa]s?\b|\bforeigners?\b|\bwe\s+are\s+foreign\b"
            r"|\bno\s+(?:soy|somos)\s+colombian[oa]s?\b|\bnot\s+colombian\b",
            message,
        ):
            intent.is_colombian = False
            intent.detected_fields.append("is_colombian")
            return
        if re.search(
            r"\bcolombian[oa]s?\b|\bcolombian\b"
            r"|\b(?:soy|somos|vivo|vivimos|residente|resido)\b[^.]{0,20}\bcolombia\b"
            r"|\bfrom\s+colombia\b|\bresident\s+in\s+colombia\b"
            # A common way to self-identify as Colombian is naming a Colombian
            # city ("soy de Medellín") instead of the country. Requires the
            # explicit "soy/somos DE" origin claim (not "estoy en", which
            # would just mean their current location, e.g. a foreign tourist
            # in Cartagena) so it never misreads current whereabouts as origin.
            r"|\b(?:soy|somos)\s+de\s+(?:bogot[aá]|medell[ií]n|cali|cartagena|barranquilla|"
            r"bucaramanga|pereira|manizales|c[uú]cuta|santa\s+marta|monter[ií]a|ibagu[eé]|"
            r"villavicencio|neiva|pasto|armenia|popay[aá]n)\b",
            message,
        ):
            intent.is_colombian = True
            intent.detected_fields.append("is_colombian")

    def _detect_duration(self, message: str, intent: DetectedIntent) -> None:
        # "d[ií]a(s)" tolerates the very common typed-without-accent "dias"/"dia"
        # (phones/autocorrect often drop it) alongside the correct "días"/"día".
        single_day_patterns = [
            r'\bun\s+d[ií]a\b',
            r'\bone\s+day\b',
            r'\bsolo\s+hoy\b',
            r'\bjust\s+today\b',
            r'\bun\s+solo\s+d[ií]a\b',
        ]

        multi_day_patterns = [
            r'\bvarios\s+d[ií]as\b',
            r'\bmulti[- ]?day\b',
            r'\b\d+\s+d[ií]as\b',
            r'\b\d+\s+days\b',
            r'\bestoy\s+en\s+las\s+islas\s+\d+\s+d[ií]as\b',
            r'\bstaying\s+\d+\s+days\b',
            r'\bpaquete\b',
            r'\bpackage\b',
        ]

        if any(re.search(pattern, message) for pattern in multi_day_patterns):
            intent.duration = "multi_day"
            intent.detected_fields.append("duration")
        elif any(re.search(pattern, message) for pattern in single_day_patterns):
            intent.duration = "single_day"
            intent.detected_fields.append("duration")

    def _detect_location(self, message: str, intent: DetectedIntent) -> None:
        msg_lower = message.lower()

        # Detectar Cartagena — incluye apodos históricos reales de la ciudad,
        # ES y EN ("la heroica"/"the heroic city": Simón Bolívar tras el Sitio
        # de Morillo de 1815; "corralito de piedra": sus murallas coloniales;
        # "ciudad redentora": otro título del propio Bolívar; "la ciudad
        # amurallada"/"the walled city": el centro histórico amurallado, muy
        # usado por locales y turistas hispanohablantes; "queen of the
        # caribbean": apodo turístico en inglés).
        # Encontrado 2026-07-09 que ninguno se reconocía — solo "cartagena"/"ctg".
        if (
            'cartagena' in msg_lower
            or 'ctg' in msg_lower
            or re.search(r'\bla\s+heroica\b', msg_lower)
            or re.search(r'\bcorralito\s+de\s+piedra\b', msg_lower)
            or re.search(r'\bciudad\s+redentora\b', msg_lower)
            or re.search(r'\b(?:la\s+)?ciudad\s+amurallada\b', msg_lower)
            or re.search(r'\bcentro\s+amurallado\b', msg_lower)
            or re.search(r'\b(?:the\s+)?heroic\s+city\b', msg_lower)
            or re.search(r'\b(?:the\s+)?walled\s+city\b', msg_lower)
            or re.search(r'\bqueen\s+of\s+the\s+caribbean\b', msg_lower)
        ):
            intent.location = "cartagena"
            intent.detected_fields.append("location")

        # Mapeo de hoteles a islas
        hotel_to_island = {
            # Isla Grande
            'san_pedro_majagua': 'isla_grande',
            'bora_bora': 'isla_grande',
            'cocoliso': 'isla_grande',
            'pao_pao': 'isla_grande',
            'fragata': 'isla_grande',
            'secreto': 'isla_grande',
            'gente_de_mar': 'isla_grande',
            'luxury_beach': 'isla_grande',
            'ecohotel_flores': 'isla_grande',
            'playa_libre': 'isla_grande',
            # Isla Marina
            'islabela': 'isla_marina',
            'hamaquero': 'isla_marina',
            'ubuntu': 'isla_marina',
            # Isla del Pirata
            'isla_del_pirata_hotel': 'isla_del_pirata',
            # Isla del Sol
            'isla_del_sol_hotel': 'isla_del_sol',
            # Isleta
            'coralina': 'isleta',
            'isleta_beach': 'isleta',
            # Isla Arena
            'isla_arena_resort': 'isla_arena',
            # Isla Pavitos
            'isla_pavitos_hotel': 'isla_pavitos',
            # Isla Lizamar
            'lizamar': 'isla_lizamar',
            # Isla Gigi
            'gigi': 'isla_gigi',
            # Isla Rosa
            'isla_rosa_hotel': 'isla_rosa',
            # Isla Pelícano
            'isla_pelicano_hotel': 'isla_pelicano',
            # Isla Rosario
            'rosario_ecohotel': 'isla_rosario',
            'san_tropel': 'isla_rosario',
        }

        # Patrones de islas (con variantes)
        island_patterns = {
            'isla_grande': [r'\bisla\s+grande\b', r'\bgrande\b'],
            'isla_marina': [r'\bisla\s+marina\b', r'\bmarina\b'],
            'isla_del_pirata': [r'\bisla\s+del\s+pirata\b', r'\bpirata\b'],
            'isla_del_sol': [r'\bisla\s+del\s+sol\b'],
            'isleta': [r'\bisleta\b', r'\bisla\s+isleta\b'],
            'isla_arena': [r'\bisla\s+arena\b', r'\barena\b'],
            'isla_pavitos': [r'\bisla\s+pavitos\b', r'\bpavitos\b'],
            'isla_lizamar': [r'\bisla\s+lizamar\b'],
            'isla_gigi': [r'\bisla\s+gigi\b'],
            'isla_rosa': [r'\bisla\s+rosa\b'],
            'isla_pelicano': [r'\bisla\s+pelicano\b', r'\bisla\s+pelícano\b', r'\bpelicano\b', r'\bpelícano\b'],
            'isla_rosario': [r'\bisla\s+rosario\b', r'\bislas\s+del\s+rosario\b'],
        }

        # Detectar isla primero
        for island_id, patterns in island_patterns.items():
            if any(re.search(pattern, msg_lower) for pattern in patterns):
                intent.island = island_id
                intent.location = "island"
                intent.detected_fields.extend(["island", "location"])
                break

        # Bare "rosario" also means the island (e.g. "corales del rosario"),
        # but checked separately from the loop above and guarded against
        # "rezar el rosario" — the Catholic prayer, a common phrase in
        # Colombia. Pre-existing false positive (bare \brosario\b in the loop
        # above matched it too) found 2026-07-09 while auditing nicknames.
        if not intent.island and re.search(r'\brosario\b', msg_lower) and not re.search(r'\brezar\b', msg_lower):
            intent.island = "isla_rosario"
            intent.location = "island"
            intent.detected_fields.extend(["island", "location"])

        # Patrones de hoteles (con muchas más variantes)
        hotel_patterns = {
            # Isla Grande
            'san_pedro_majagua': [
                r'\bsan\s+pedro\s+de\s+majagua\b',
                r'\bsan\s+pedro\b',
                r'\bmajagua\b',
                r'\bhotel\s+majagua\b',
            ],
            'bora_bora': [
                r'\bbora\s+bora\b',
                r'\bbora\b',
                r'\bhotel\s+bora\b',
            ],
            'cocoliso': [
                r'\bcocoliso\b',
                r'\bhotel\s+cocoliso\b',
                r'\bcocoliso\s+island\b',
                r'\bcocoliso\s+resort\b',
            ],
            'pao_pao': [
                r'\bpao\s+pao\b',
                r'\bpaopao\b',
                r'\bhotel\s+pao\b',
            ],
            'fragata': [
                r'\bfragata\b',
                r'\bhotel\s+fragata\b',
                r'\bfragata\s+island\b',
            ],
            'secreto': [
                r'\bsecreto\b',
                r'\bhotel\s+secreto\b',
                r'\bhostel\s+secreto\b',
            ],
            'gente_de_mar': [
                r'\bgente\s+de\s+mar\b',
                r'\bhotel\s+gente\b',
            ],
            'luxury_beach': [
                r'\bluxury\s+beach\b',
                r'\bluxury\b',
            ],
            'ecohotel_flores': [
                r'\becohotel\s+las\s+flores\b',
                r'\blas\s+flores\b',
                r'\bflores\b',
            ],
            'playa_libre': [
                r'\bplaya\s+libre\b',
                r'\becohostal\s+playa\b',
            ],
            # Isla Marina
            'islabela': [
                r'\bislabela\b',
                r'\bisla\s+bella\b',
                r'\bhotel\s+islabela\b',
            ],
            'hamaquero': [
                r'\bhamaquero\b',
                r'\bel\s+hamaquero\b',
                r'\bhotel\s+hamaquero\b',
            ],
            'ubuntu': [
                r'\bubuntu\b',
                r'\bcentro\s+ubuntu\b',
            ],
            # Isla del Pirata
            'isla_del_pirata_hotel': [
                r'\bhotel\s+isla\s+del\s+pirata\b',
                r'\bisla\s+del\s+pirata\b',
            ],
            # Isla del Sol
            'isla_del_sol_hotel': [
                r'\bhotel\s+isla\s+del\s+sol\b',
                r'\bisla\s+del\s+sol\b',
            ],
            # Isleta
            'coralina': [
                r'\bcoralina\b',
                r'\bhotel\s+coralina\b',
                r'\bcoralina\s+island\b',
            ],
            'isleta_beach': [
                r'\bisleta\s+beach\b',
            ],
            # Isla Arena
            'isla_arena_resort': [
                r'\bisla\s+arena\s+eco\s+resort\b',
                r'\bisla\s+arena\s+resort\b',
                r'\bisla\s+arena\b',
            ],
            # Isla Pavitos
            'isla_pavitos_hotel': [
                r'\bisla\s+pavitos\b',
                r'\bpavitos\b',
            ],
            # Isla Lizamar
            'lizamar': [
                r'\blizamar\b',
                r'\bhotel\s+lizamar\b',
            ],
            # Isla Gigi
            'gigi': [
                r'\bcasa\s+de\s+isla\s+gigi\b',
                r'\bisla\s+gigi\b',
                r'\bgigi\b',
            ],
            # Isla Rosa
            'isla_rosa_hotel': [
                r'\bisla\s+rosa\b',
            ],
            # Isla Pelícano
            'isla_pelicano_hotel': [
                r'\bisla\s+pelicano\b',
                r'\bisla\s+pelícano\b',
                r'\bpelicano\b',
                r'\bpelícano\b',
            ],
            # Isla Rosario
            'rosario_ecohotel': [
                r'\brosario\s+ecohotel\b',
                r'\becohotel\s+rosario\b',
            ],
            'san_tropel': [
                r'\bsan\s+tropel\b',
                r'\btropel\b',
            ],
        }

        # Detectar hotel
        for hotel_id, patterns in hotel_patterns.items():
            if any(re.search(pattern, msg_lower) for pattern in patterns):
                intent.hotel = hotel_id
                # Detectar isla automáticamente desde el hotel
                if hotel_id in hotel_to_island and not intent.island:
                    intent.island = hotel_to_island[hotel_id]
                    intent.detected_fields.append("island")
                if not intent.location:
                    intent.location = "island"
                intent.detected_fields.append("hotel")
                break

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

    def _calculate_confidence(self, intent: DetectedIntent) -> None:
        field_weights = {
            'language': 0.1,
            'activity': 0.25,
            'is_certified': 0.2,
            'group_size': 0.15,
            'group_allocation': 0.2,
            'last_dive_over_2_years': 0.15,
            'duration': 0.1,
            'location': 0.1,
            'island': 0.1,
            'hotel': 0.1,
        }

        total_confidence = sum(field_weights.get(field, 0.1) for field in intent.detected_fields)
        intent.confidence = min(total_confidence, 1.0)
