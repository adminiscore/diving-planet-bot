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
            r'\bbucear\b',
            r'\bbuzo\s+certificado\b',
            r'\bbuzos\s+certificados\b',
            r'\bcertified\s+diver',
            r'\bdos\s+inmersiones\b',
            r'\btwo\s+dives\b',
            r'\bfun\s+dive',
        ]
        
        minicourse_patterns = [
            r'\bminicurso\b',
            r'\bbautismo\b',
            r'\bprimera\s+vez\b',
            r'\bnunca\s+he\s+buceado\b',
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
            r'\bestamos\s+certificados\b',
            r'\bsomos\s+certificados\b',
            r'\btengo\s+licencia\b',
            r'\bhave\s+license\b',
            r'\bpadi\s+(certified|card|license)\b',
            r'\bssi\s+(certified|card|license)\b',
            r'\bbuzo\s+certificado\b',
            r'\bbuzos\s+certificados\b',
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
            (r'\bsomos\s+(\d+|dos|tres|cuatro|cinco|seis)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6}),
            (r'\bvenimos\s+(\d+|dos|tres|cuatro|cinco|seis)\b', {'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6}),
            (r'\bwe\s+are\s+(\d+|two|three|four|five|six)\b', {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}),
            (r'\bgroup\s+of\s+(\d+|two|three|four|five|six)\b', {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}),
            (r'\b(\d+)\s+(personas|people)\b', {}),
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
        
        mixed_group_patterns = [
            (r'\byo\s+(?:quiero|hago|haría|haré)\s+(?:el\s+)?(\w+)\s+y\s+(?:mi\s+)?(?:novia|novio|amigo|amiga|pareja|compañero|compañera|él|ella)\s+(?:quiere|hace|haría|hará)?\s*(?:el\s+)?(\w+)', 'es'),
            (r'\b(?:uno|una)\s+(?:quiere|hace)\s+(?:el\s+)?(\w+)\s+y\s+(?:el\s+otro|la\s+otra|otro|otra)\s+(?:el\s+)?(\w+)', 'es'),
            (r'\byo\s+(?:buceo|snorkel|minicurso)\s+y\s+(?:mi\s+)?(?:novia|novio|amigo|amiga|pareja|compañero|compañera|él|ella)\s+(\w+)', 'es'),
            (r'\bi\s+(?:want|do)\s+(\w+)\s+and\s+(?:my\s+)?(?:girlfriend|boyfriend|friend|partner|he|she)\s+(?:wants|does)?\s*(\w+)', 'en'),
            (r'\bone\s+(?:wants|does)\s+(\w+)\s+and\s+(?:the\s+)?other\s+(\w+)', 'en'),
        ]
        
        for pattern, lang in mixed_group_patterns:
            match = re.search(pattern, message)
            if match:
                activity1 = match.group(1).lower()
                activity2 = match.group(2).lower()
                
                allocation = {}
                
                for activity_text in [activity1, activity2]:
                    if any(kw in activity_text for kw in ['buceo', 'dive', 'diving']):
                        allocation['certified_diving'] = allocation.get('certified_diving', 0) + 1
                    elif any(kw in activity_text for kw in ['snorkel', 'careteo']):
                        allocation['snorkel'] = allocation.get('snorkel', 0) + 1
                    elif any(kw in activity_text for kw in ['minicurso', 'bautismo', 'discover']):
                        allocation['minicourse'] = allocation.get('minicourse', 0) + 1
                
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
        if 'cartagena' in message:
            intent.location = "cartagena"
            intent.detected_fields.append("location")
        
        island_patterns = {
            'isla_grande': [r'\bisla\s+grande\b'],
            'isla_marina': [r'\bisla\s+marina\b'],
            'isla_del_pirata': [r'\bisla\s+del\s+pirata\b'],
            'isla_del_sol': [r'\bisla\s+del\s+sol\b'],
            'isleta': [r'\bisleta\b'],
            'isla_arena': [r'\bisla\s+arena\b'],
            'isla_pavitos': [r'\bisla\s+pavitos\b'],
            'isla_lizamar': [r'\bisla\s+lizamar\b'],
            'isla_gigi': [r'\bisla\s+gigi\b'],
            'isla_rosa': [r'\bisla\s+rosa\b'],
            'isla_pelicano': [r'\bisla\s+pelicano\b', r'\bisla\s+pelícano\b'],
            'isla_rosario': [r'\bisla\s+rosario\b', r'\bislas\s+del\s+rosario\b'],
        }
        
        for island_id, patterns in island_patterns.items():
            if any(re.search(pattern, message) for pattern in patterns):
                intent.island = island_id
                intent.location = "island"
                intent.detected_fields.extend(["island", "location"])
                break
        
        hotel_patterns = {
            'pao_pao': [r'\bpao\s+pao\b'],
            'san_pedro_majagua': [r'\bsan\s+pedro\s+de\s+majagua\b', r'\bmajagua\b'],
            'bora_bora': [r'\bbora\s+bora\b'],
            'cocoliso': [r'\bcocoliso\b'],
            'fragata': [r'\bfragata\b'],
            'secreto': [r'\bsecreto\b'],
            'gente_de_mar': [r'\bgente\s+de\s+mar\b'],
            'luxury_beach': [r'\bluxury\s+beach\b'],
            'ecohotel_flores': [r'\becohotel\s+las\s+flores\b', r'\blas\s+flores\b'],
            'playa_libre': [r'\bplaya\s+libre\b'],
            'islabela': [r'\bislabela\b'],
            'hamaquero': [r'\bhamaquero\b'],
            'ubuntu': [r'\bubuntu\b'],
            'isla_del_pirata_hotel': [r'\bhotel\s+isla\s+del\s+pirata\b'],
            'isla_del_sol_hotel': [r'\bhotel\s+isla\s+del\s+sol\b'],
            'coralina': [r'\bcoralina\b'],
            'isleta_beach': [r'\bisleta\s+beach\b'],
            'isla_arena_resort': [r'\bisla\s+arena\s+eco\s+resort\b'],
            'lizamar': [r'\blizamar\b'],
            'gigi': [r'\bcasa\s+de\s+isla\s+gigi\b'],
            'rosario_ecohotel': [r'\brosario\s+ecohotel\b'],
            'san_tropel': [r'\bsan\s+tropel\b'],
        }
        
        for hotel_id, patterns in hotel_patterns.items():
            if any(re.search(pattern, message) for pattern in patterns):
                intent.hotel = hotel_id
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
