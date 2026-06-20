import re
from dataclasses import dataclass, field
from typing import Optional, Dict
from openai import OpenAI

from src.flows.decision_tree import ConversationState


@dataclass
class DetectedIntent:
    language: Optional[str] = None
    activity: Optional[str] = None
    service_id: Optional[str] = None
    is_certified: Optional[bool] = None
    group_size: Optional[int] = None
    group_allocation: Optional[Dict[str, int]] = None
    last_dive_over_2_years: Optional[bool] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    island: Optional[str] = None
    hotel: Optional[str] = None
    confidence: float = 0.0
    detected_fields: list = field(default_factory=list)


class IntentDetector:
    
    def __init__(self, openai_client: Optional[OpenAI] = None):
        self.openai_client = openai_client
        
    def detect(self, message: str, state: ConversationState) -> DetectedIntent:
        intent = DetectedIntent()
        message_lower = message.lower().strip()
        
        self._detect_language(message_lower, intent)
        self._detect_activity(message_lower, intent, state)
        self._detect_certification(message_lower, intent)
        self._detect_group_info(message_lower, intent)
        self._detect_last_dive(message_lower, intent)
        self._detect_duration(message_lower, intent)
        self._detect_location(message_lower, intent)
        
        self._calculate_confidence(intent)
        
        return intent
    
    def _detect_language(self, message: str, intent: DetectedIntent) -> None:
        spanish_keywords = [
            'hola', 'quiero', 'buceo', 'snorkel', 'curso', 'minicurso',
            'certificado', 'somos', 'personas', 'día', 'días', 'inmersión',
            'buzo', 'bautismo', 'precio', 'información', 'reservar'
        ]
        
        english_keywords = [
            'hello', 'hi', 'want', 'diving', 'dive', 'snorkel', 'course',
            'certified', 'people', 'day', 'days', 'price', 'information',
            'book', 'booking', 'diver', 'beginner'
        ]
        
        spanish_count = sum(1 for kw in spanish_keywords if kw in message)
        english_count = sum(1 for kw in english_keywords if kw in message)
        
        if spanish_count > english_count and spanish_count > 0:
            intent.language = "es"
            intent.detected_fields.append("language")
        elif english_count > spanish_count and english_count > 0:
            intent.language = "en"
            intent.detected_fields.append("language")
    
    def _detect_activity(self, message: str, intent: DetectedIntent, state: ConversationState) -> None:
        certified_diving_patterns = [
            r'\bbuceo\b(?!\s+(bautismo|principiante|primera\s+vez|minicurso))',
            r'\bdive\b(?!\s+(baptism|beginner|first\s+time))',
            r'\bdiving\b(?!\s+(first|beginner|class|course|lesson|trip\s+first))',
            r'\bscuba\b(?!\s+(class|course|lesson))',
            r'\bbucear\b',
            r'\bbuzo\s+certificado\b',
            r'\bbuzos\s+certificados\b',
            r'\bcertified\s+diver',
            r'\bdos\s+inmersiones\b',
            r'\btwo\s+dives\b',
            r'\bfun\s+dive',
            r'\bwant\s+(?:to\s+)?(?:go\s+)?diving\b',
            r'\binterested\s+in\s+diving\b',
            r'\bdiving\s+trip\b',
        ]

        minicourse_patterns = [
            r'\bminicurso\b',
            r'\bbautismo\b',
            r'\bprimera\s+vez\b',
            r'\bnunca\s+he\s+buceado\b',
            r'\bnever\s+(?:tried|dived|done\s+it|been\s+diving)\b',
            r'\bno\s+experience\b',
            r'\bsin\s+experiencia\b',
            r'\bdiscover\s+scuba\b',
            r'\bbeginner\s+dive\b',
            r'\bfirst\s+time\s+diving\b',
            r'\btry\s+dive',
        ]
        
        snorkel_patterns = [
            r'\bsnorkel\b',
            r'\bsnorkeling\b',
            r'\bcareteo\b',
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
        elif any(re.search(pattern, message) for pattern in padi_course_patterns):
            intent.activity = "padi_course"
            if 'open water' in message or 'open-water' in message:
                intent.service_id = "open_water"
            elif 'advanced' in message:
                intent.service_id = "advanced"
            elif 'rescue' in message:
                intent.service_id = "rescue"
            elif 'divemaster' in message or 'dive master' in message:
                intent.service_id = "divemaster"
            intent.detected_fields.append("activity")
        elif any(re.search(pattern, message) for pattern in specialty_patterns):
            intent.activity = "specialty"
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
        ]
        
        not_certified_patterns = [
            r'\bno\s+(certificado|certified)\b',
            r'\bsin\s+certificado\b',
            r'\bnunca\s+he\s+buceado\b',
            r'\bprimera\s+vez\b',
            r'\bnot\s+certified\b',
            r'\bnever\s+dived\b',
            r'\bfirst\s+time\b',
            r'\bbeginner\b',
            r'\bprincipiante\b',
        ]
        
        if any(re.search(pattern, message) for pattern in not_certified_patterns):
            intent.is_certified = False
            intent.detected_fields.append("is_certified")
        elif any(re.search(pattern, message) for pattern in certified_patterns):
            intent.is_certified = True
            intent.detected_fields.append("is_certified")
    
    def _detect_group_info(self, message: str, intent: DetectedIntent) -> None:
        group_size_patterns = [
            (r'\bsomos\s+(\d+|dos|tres|cuatro|cinco|seis|siete|ocho)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8}),
            (r'\bvenimos\s+(\d+|dos|tres|cuatro|cinco|seis|siete|ocho)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8}),
            (r'\bvamos\s+(\d+|dos|tres|cuatro|cinco|seis|siete|ocho)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8}),
            (r'\bwe\s+are\s+(\d+|two|three|four|five|six|seven|eight)\b', {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8}),
            (r'\b(\d+)\s+of\s+us\b', {}),
            (r'\bgroup\s+of\s+(\d+|two|three|four|five|six|seven|eight)\b', {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8}),
            (r'\b(\d+)\s+(personas|people|friends|amigos|friend)\b', {}),
            # "una pareja" / "somos pareja" → 2 (capturing group required by loop)
            (r'\b(?:somos\s+)?(?:una?\s+)?(pareja)\b', {'pareja': 2}),
            # "familia de N" → N personas
            (r'\bfamilia\s+de\s+(\d+|dos|tres|cuatro|cinco|seis|siete|ocho)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8}),
        ]
        
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
        
        # ── Numeric split: "3 de buceo y 2 de snorkel", "5 snorkel y 2 buceo" ──
        _ACTIVITY_KW = r'(buceo|bucear|buceando|snorkel|snorkeling|careteo|caretear|minicurso|bautismo|bautizo|diving|scuba)'
        _NUM = r'(\d+|dos|tres|cuatro|cinco|seis|two|three|four|five|six)'
        _word_num_map: dict[str, int] = {
            'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
        }

        def _parse_num(s: str) -> int:
            return int(s) if s.isdigit() else _word_num_map.get(s, 1)

        def _activity_key(text: str) -> str | None:
            if any(k in text for k in ('minicurso', 'bautismo', 'bautizo', 'discover', 'principiante')):
                return 'minicourse'
            if any(k in text for k in ('snorkel', 'careteo', 'snorkeling')):
                return 'snorkel'
            if any(k in text for k in ('buceo', 'bucear', 'dive', 'diving', 'certificado', 'certified', 'scuba')):
                return 'certified_diving'
            return None

        # Pattern A: "3 de buceo y 2 de snorkel" / "3 buceos y 2 snorkel"
        # También cubre "buceo 3 y snorkel 2" (número después del keyword)
        # y "3 for diving and 2 for snorkel" (inglés)
        # y "2 queremos hacer buceo y 1 snorkel" / "2 hacen snorkel y 3 buceo"
        _SEP = r'\s+(?:y|and|,)\s+'
        # Verb fillers: "hacen", "harán", "quieren hacer", "queremos hacer", "vamos a hacer", etc.
        _VERB_FILLER = (
            r'(?:'
            r'(?:queremos?|quieren?|hacemos?|hacen?|hago|hace|haremos?|har[aá]n?)\s+(?:hacer\s+)?'
            r'|vamos?\s+a\s+(?:hacer\s+)?'
            r')?'
        )
        # Prefix: "N de", "N para", "N personas", "N hacen", or bare "N "
        _QUANT_PREFIX = rf'{_NUM}\s+(?:de\s+|para\s+|for\s+|personas?\s+(?:de\s+|para\s+|for\s+)?|{_VERB_FILLER})'
        pat_numeric_fwd = (
            rf'{_QUANT_PREFIX}{_ACTIVITY_KW}(?:\s+certificad[ao])?'
            rf'{_SEP}'
            rf'{_QUANT_PREFIX}{_ACTIVITY_KW}(?:\s+certificad[ao])?'
        )
        pat_numeric_rev = (
            rf'{_ACTIVITY_KW}(?:\s+certificad[ao])?\w*\s+{_NUM}'
            rf'{_SEP}'
            rf'{_ACTIVITY_KW}(?:\s+certificad[ao])?\w*\s+{_NUM}'
        )
        # ── Pattern B (priority): cert/no-cert splits — BEFORE numeric split ──
        # "2 buceadores (1 certificado y otro no)" / "N cert y M principiante"
        _WORD_NUM = r'(\d+|un[ao]?|dos|tres|cuatro|cinco|seis|one|two|three|four|five|six)'
        cert_split_patterns = [
            # "2 buceadores (1 certificado y otro/s no)" / "4 buceadores (2 cert y 2 no)"
            rf'(\d+)\s+buceador[aes]*[^,\(]*[\(,]\s*{_WORD_NUM}\s+certificad[ao]s?\s+y\s+(?:{_WORD_NUM}\s+)?(?:el\s+)?otr[ao]s?\s+no',
            # "4 buceadores (2 certificados y 2 no)" — with explicit "2 no"
            rf'(\d+)\s+buceador[aes]*[^,\(]*[\(,]\s*{_WORD_NUM}\s+certificad[ao]s?\s+y\s+{_WORD_NUM}\s+no\b',
            # "N certificados y M no certificados/principiantes"
            r'(\d+)\s+certificad[ao]s?\s+y\s+(\d+)\s+(?:no\s+certificad[ao]s?|principiantes?|sin\s+certificar)',
            # "uno certificado y dos minicurso" (palabras)
            rf'{_WORD_NUM}\s+certificad[ao]s?\s+y\s+{_WORD_NUM}\s+(?:minicurso|bautismo|no\s+certificad[ao]|principiante)',
            # "N buceo certificado y M minicurso/no certificado"
            r'(\d+)\s+(?:de\s+)?buceo\s+certificado\s+y\s+(\d+)\s+(?:minicurso|no\s+certificad[ao]|principiante|bautismo)',
            # "somos N, M certificados y el/los otro/s no"
            r'(\d+)\s+certificad[ao]s?\s+y\s+(?:el\s+)?otr[ao]s?\s+(?:\d+\s+)?(?:no|sin\s+certific)',
            # English: "N certified and M not certified/beginners"
            r'(\d+)\s+certified\s+and\s+(\d+)\s+(?:not\s+certified|beginners?|uncertified)',
            # "dos tenemos (el) open water y una no" / "2 con open water y 1 no"
            rf'{_WORD_NUM}\s+(?:tenemos|tienen|tiene|tengo|con|somos)\s+'
            rf'(?:el\s+|la\s+|los\s+|las\s+|nuestro\s+)?'
            rf'(?:open\s*water|advanced|rescue|divemaster|licencia|certificad[ao]s?|padi|ssi|cmas|naui)\b'
            rf'[^,.;]*?\s+y\s+{_WORD_NUM}\s+no\b',
            # English: "two have (their) open water and one doesn't/does not/not"
            rf'{_WORD_NUM}\s+(?:have|with|are)\s+(?:their\s+|the\s+)?'
            rf'(?:open\s*water|advanced|rescue|certified|padi|ssi)\b'
            rf'[^,.;]*?\s+and\s+{_WORD_NUM}\s+(?:no|not|doesn\'?t|does\s+not|don\'?t|do\s+not)\b',
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
    
    def _detect_last_dive(self, message: str, intent: DetectedIntent) -> None:
        last_dive_patterns = [
            (r'\búltima\s+inmersión\s+(?:fue\s+)?hace\s+(\d+)\s+(año|años|mes|meses)', 'es'),
            (r'\blast\s+dive\s+(?:was\s+)?(\d+)\s+(year|years|month|months)\s+ago', 'en'),
            (r'\bhace\s+(\d+)\s+(año|años|mes|meses)\s+(?:que\s+)?(?:buceo|buceé|bucee)', 'es'),
            (r'\bdived\s+(\d+)\s+(year|years|month|months)\s+ago', 'en'),
            (r'\bmi\s+última\s+inmersión\s+fue\s+hace\s+(\d+)\s+(año|años|mes|meses)', 'es'),
            (r'\bmy\s+last\s+dive\s+was\s+(\d+)\s+(year|years|month|months)\s+ago', 'en'),
        ]
        
        for pattern, lang in last_dive_patterns:
            match = re.search(pattern, message)
            if match:
                number = int(match.group(1))
                unit = match.group(2)
                
                if 'año' in unit or 'year' in unit:
                    intent.last_dive_over_2_years = number >= 2
                elif 'mes' in unit or 'month' in unit:
                    intent.last_dive_over_2_years = number >= 24
                
                intent.detected_fields.append("last_dive_over_2_years")
                break
    
    def _detect_duration(self, message: str, intent: DetectedIntent) -> None:
        single_day_patterns = [
            r'\bun\s+día\b',
            r'\bone\s+day\b',
            r'\bsolo\s+hoy\b',
            r'\bjust\s+today\b',
            r'\bun\s+solo\s+día\b',
        ]
        
        multi_day_patterns = [
            r'\bvarios\s+días\b',
            r'\bmulti[- ]?day\b',
            r'\b\d+\s+días\b',
            r'\b\d+\s+days\b',
            r'\bestoy\s+en\s+las\s+islas\s+\d+\s+días\b',
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
        
        # Detectar Cartagena
        if 'cartagena' in msg_lower or 'ctg' in msg_lower:
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
            'isla_rosario': [r'\bisla\s+rosario\b', r'\bislas\s+del\s+rosario\b', r'\brosario\b'],
        }
        
        # Detectar isla primero
        for island_id, patterns in island_patterns.items():
            if any(re.search(pattern, msg_lower) for pattern in patterns):
                intent.island = island_id
                intent.location = "island"
                intent.detected_fields.extend(["island", "location"])
                break
        
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
