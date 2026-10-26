"""Los lectores del regex que siguen vivos: edades, duracion y lugar (`lectura_del_turno`), las categorias de actividad
y `certification_claim`.
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect (idioma, actividad, certificacion, grupo, ultima inmersion,
nacionalidad y confianza; la clase se quito y esos campos los decide el extractor).
"""
import pytest
from src.agents.intent_detector import (
    certification_claim,
    lectura_del_turno,
    matched_activity_categories,
)


class TestAgeDetection:

    def test_hace_como_n_anos_does_not_leak_into_ages(self):
        """Bug real hallado en la batería de la Fase 6 (docs/robustness/
        live-test-battery-fase6.md D5): 'hace como 3 años que no buceo' —
        la guarda que descarta 'hace N años' como edad solo miraba 8
        caracteres atrás, y 'como' entre 'hace' y el número empujaba 'hace'
        fuera de esa ventana, colando un niño fantasma de 3 años que
        contaminaría kids_under_8_count en el checkout."""
        intent = lectura_del_turno("hace como 3 años que no buceo, seré yo solo")
        assert intent.ages == []

    def test_hace_ya_n_anos_does_not_leak_into_ages_english(self):
        intent = lectura_del_turno("it's been like 4 years since i last dived")
        assert intent.ages == []

    # Edades en PALABRA (2026-07-24): _detect_ages era digit-only; "mi hija de
    # nueve años" no se capturaba y el gate de elegibilidad caía a RAG genérico.
    @pytest.mark.parametrize("message, expected", [
        ("mi hija de nueve años, ¿puede bucear?", [9]),
        ("tienen cinco y siete años", [5, 7]),
        ("un niño de doce", [12]),
        ("mi hijo tiene ocho", [8]),
        ("kids aged eight and eleven", [8, 11]),
        ("¿a partir de qué edad?", []),          # sin edad concreta
    ])
    def test_word_ages_detected(self, message, expected):
        assert lectura_del_turno(message).ages == expected

    def test_word_age_timeframe_not_leaked(self):
        """"llevo nueve años sin bucear" es un plazo, NO una edad."""
        intent = lectura_del_turno("llevo nueve años sin bucear, voy solo")
        assert intent.ages == []


class TestDurationDetection:
    
    def test_detect_single_day(self):
        intent = lectura_del_turno("estoy solo un día")
        assert intent.duration == "single_day"
        assert "duration" in intent.detected_fields
    
    def test_detect_multi_day(self):
        intent = lectura_del_turno("estoy varios días en las islas")
        assert intent.duration == "multi_day"
    
    def test_detect_multi_day_number(self):
        intent = lectura_del_turno("estoy 3 días")
        assert intent.duration == "multi_day"

    def test_detect_multi_day_without_accent_typo(self):
        """'dias'/'dia' without the accent (very common on phones) used to
        silently fail to match — real bug found 2026-07-16."""
        intent = lectura_del_turno("estamos 5 dias en la isla, que podemos hacer?")
        assert intent.duration == "multi_day"

    def test_detect_varios_dias_without_accent_typo(self):
        intent = lectura_del_turno("vamos varios dias a la isla")
        assert intent.duration == "multi_day"

    def test_detect_single_day_without_accent_typo(self):
        intent = lectura_del_turno("estoy solo un dia")
        assert intent.duration == "single_day"


class TestLocationDetection:
    
    def test_detect_cartagena(self):
        intent = lectura_del_turno("estoy en Cartagena")
        assert intent.location == "cartagena"
        assert "location" in intent.detected_fields
    
    def test_detect_isla_grande(self):
        intent = lectura_del_turno("estoy en Isla Grande")
        assert intent.island == "isla_grande"
        assert intent.location == "island"
    
    def test_detect_hotel_pao_pao(self):
        intent = lectura_del_turno("estoy en el hotel Pao Pao")
        assert intent.hotel == "pao_pao"
        assert "hotel" in intent.detected_fields
    
    def test_detect_hotel_cocoliso(self):
        intent = lectura_del_turno("me hospedo en Cocoliso")
        assert intent.hotel == "cocoliso"


class TestMatchedActivityCategories:
    """Hallazgo en vivo (conversacion real 'purple-sun-590', 2026-09-03): el
    regex de _detect_activity resuelve por la primera categoria que matchea
    (orden de codigo), no por lo que el cliente pidio. matched_activity_
    categories() es la senal barata (0/1/2+ categorias) de mensaje ambiguo
    (la usaba el veto LLM de actividad, borrado en MEJ-1)."""

    def test_real_bug_message_matches_multiple_categories(self):
        # El mensaje real que causo el bug: pide open water pero "nunca he
        # buceado" tambien dispara minicourse (y certified_diving via "buce*").
        cats = matched_activity_categories(
            "Me gustaria sacarme el open water, pero nunca he buceado"
        )
        assert "padi_course" in cats
        assert len(cats) >= 2

    def test_unambiguous_message_matches_single_category(self):
        assert matched_activity_categories("quiero hacer snorkel") == {"snorkel"}

    def test_unrelated_message_matches_no_category(self):
        assert matched_activity_categories("hola, cual es el horario") == set()

    def test_case_insensitive(self):
        cats = matched_activity_categories("QUIERO EL OPEN WATER, NUNCA HE BUCEADO")
        assert "padi_course" in cats
        assert len(cats) >= 2


class TestCertificationClaim:
    """Inventario regex 2026-09-03: certification_claim() es la fuente unica
    que _detect_certification usa internamente y que conversational_core.
    _activity_has_textual_backing reusa en vez de mantener su propio par de
    regex (_CERTIFICATION_CLAIM_RE/_CERTIFICATION_NEGATED_RE, ya borrados)."""

    @pytest.mark.parametrize(
        "message",
        [
            "soy certificado", "somos buzos certificados", "tengo licencia PADI", "certified diver",
            # Hallazgo en vivo (bateria sintetica shadow-mode, 2026-09-10):
            # "titulo"/"titulad[oa]" es sinonimo real de "certificado" que
            # ningun patron cubria -- el bot volvia a preguntar algo que el
            # cliente ya habia respondido.
            "tengo el titulo de buceo", "estoy titulada en buceo", "estoy titulado en buceo",
        ],
    )
    def test_affirms_certification(self, message):
        assert certification_claim(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "no estoy certificado", "no soy buzo", "sin certificar",
            "nunca he buceado", "primera vez", "quiero certificarme",
            # Hallazgo en vivo (bateria sintetica shadow-mode is_certified,
            # 2026-09-10): sin un patron dedicado para "nunca ... certificado"
            # (distinto de "nunca ... buce*", ya cubierto arriba), esto caia
            # al catch-all generico \bcertificado\b y resolvia True -- justo
            # lo contrario de lo que dice el cliente.
            "hola nunca me he certificado pero quiero probar",
            "nunca me he certificado",
            # Hallazgo 2026-09-14: con tilde ("está") la negacion no casaba y el
            # catch-all resolvia True. Texto y patrones se comparan sin tildes.
            "no está certificada",
            "No Está Certificado", "todavía no están certificados",
        ],
    )
    def test_denies_certification(self, message):
        assert certification_claim(message) is False

    def test_someone_elses_denial_is_not_the_writers(self):
        """"mi amigo no está certificado" habla del amigo (2026-09-15): no dice nada de
        quien escribe, pero sigue negando la certificacion de esa otra persona (con tilde)."""
        assert certification_claim("mi amigo no está certificado") is None
        assert certification_claim("mi amigo no está certificado", about_writer=False) is False

    def test_no_signal_returns_none(self):
        assert certification_claim("hola, cuál es el horario") is None

    def test_negation_wins_over_generic_cert_catchall(self):
        """'not certfied' (typo real, bug live 2026-07-21) debe leer False,
        no True por el catch-all generico \\bcert\\w*\\b."""
        assert certification_claim("not certfied") is False
