import pytest
from src.agents.intent_detector import IntentDetector, DetectedIntent
from src.flows.decision_tree import ConversationState


@pytest.fixture
def detector():
    return IntentDetector()


@pytest.fixture
def state():
    return ConversationState(conversation_id="test-123")


class TestLanguageDetection:
    
    def test_detect_spanish(self, detector, state):
        intent = detector.detect("Hola quiero bucear", state)
        assert intent.language == "es"
        assert "language" in intent.detected_fields
    
    def test_detect_english(self, detector, state):
        intent = detector.detect("Hello I want to dive", state)
        assert intent.language == "en"
        assert "language" in intent.detected_fields
    
    def test_spanish_with_multiple_keywords(self, detector, state):
        intent = detector.detect("Hola somos dos personas que queremos hacer buceo", state)
        assert intent.language == "es"


class TestActivityDetection:
    
    def test_detect_certified_diving(self, detector, state):
        intent = detector.detect("quiero hacer buceo", state)
        assert intent.activity == "certified_diving"
        assert intent.service_id == "2_dives_1_day"
        assert "activity" in intent.detected_fields
    
    def test_detect_minicourse(self, detector, state):
        intent = detector.detect("quiero hacer un minicurso de buceo", state)
        assert intent.activity == "minicourse"
        assert intent.service_id == "minicourse"
        assert intent.is_certified is False
    
    def test_detect_snorkel(self, detector, state):
        intent = detector.detect("quiero hacer snorkel", state)
        assert intent.activity == "snorkel"
        assert intent.service_id == "snorkeling"
    
    def test_detect_padi_open_water(self, detector, state):
        intent = detector.detect("quiero hacer el curso open water", state)
        assert intent.activity == "padi_open_water"
        assert intent.service_id == "open_water"

    def test_detect_advanced_course(self, detector, state):
        intent = detector.detect("I want to do the advanced course", state)
        assert intent.activity == "padi_advanced"
        assert intent.service_id == "advanced"

    def test_detect_specialty_nitrox(self, detector, state):
        intent = detector.detect("quiero hacer el curso de nitrox", state)
        assert intent.activity == "padi_specialty"
        assert intent.service_id == "nitrox"

    def test_already_have_cert_not_classified_as_wanting_the_course(self, detector, state):
        """Bug real hallado en la batería de la Fase 6 (docs/robustness/
        live-test-battery-fase6.md A6): '_HOLDS_CERT_RE' exigía "i have"
        pegado; "i ALREADY have" con la palabra de por medio rompía el match
        y el mensaje se clasificaba como querer TOMAR el curso Open Water
        (padi_open_water) en vez de reconocer que ya lo tiene."""
        intent = detector.detect("i already have my open water card, want to do more dives", state)
        assert intent.activity != "padi_open_water"
        assert intent.activity == "certified_diving"

    def test_ya_tengo_el_open_water_es(self, detector, state):
        intent = detector.detect("ya tengo el open water, quiero seguir buceando", state)
        assert intent.activity == "certified_diving"


class TestCertificationDetection:
    
    def test_detect_certified(self, detector, state):
        intent = detector.detect("soy buzo certificado", state)
        assert intent.is_certified is True
        assert "is_certified" in intent.detected_fields
    
    def test_detect_not_certified(self, detector, state):
        intent = detector.detect("no soy certificado, es mi primera vez", state)
        assert intent.is_certified is False
    
    def test_detect_certified_english(self, detector, state):
        intent = detector.detect("I am a certified diver", state)
        assert intent.is_certified is True
    
    def test_minicourse_implies_not_certified(self, detector, state):
        intent = detector.detect("quiero hacer el minicurso", state)
        assert intent.is_certified is False
        assert intent.activity == "minicourse"

    def test_english_not_certified_typo(self, detector, state):
        """Real bug found live against PRE (2026-07-21): 'not_certified_patterns'
        required exact "certified" spelling ('\\bnot\\s+certified\\b'), while
        'certified_patterns' has a typo-tolerant catch-all ('\\bcert\\w*\\b')
        checked afterwards. So "im not certfied tho" matched NEITHER negation
        pattern NOR the exact positive one, fell through to the typo-tolerant
        catch-all, and was wrongly read as is_certified=True — the bot told a
        beginner "I see you are a certified diver"."""
        intent = detector.detect("hi i wanna dive, im not certfied tho, just me", state)
        assert intent.is_certified is False

    def test_spanish_bv_typo_activity_detection(self, detector, state):
        """Real bug found live against PRE (2026-07-21): "vucea" (b/v typo for
        "bucea", a very common confusion for Spanish speakers since both letters
        sound identical) was not recognized as a diving-activity word at all —
        the message fell through to RAG entirely and got rejected as a
        hallucination, landing on the generic advisor fallback instead of
        entering the booking flow. Without the typo ("bucea"), the exact same
        message correctly asks certification."""
        intent = detector.detect("vamos 2, mi novia y yo, ella no vucea solo yo", state)
        assert intent.activity == "certified_diving"


class TestGroupDetection:
    
    def test_detect_group_size_somos_dos(self, detector, state):
        intent = detector.detect("somos dos personas", state)
        assert intent.group_size == 2
        assert "group_size" in intent.detected_fields
    
    def test_detect_group_size_venimos_tres(self, detector, state):
        intent = detector.detect("venimos tres", state)
        assert intent.group_size == 3
    
    def test_detect_group_size_number(self, detector, state):
        intent = detector.detect("somos 4 personas", state)
        assert intent.group_size == 4
    
    def test_detect_group_size_english(self, detector, state):
        intent = detector.detect("we are 3 people", state)
        assert intent.group_size == 3

    def test_detect_group_size_somos_nueve(self, detector, state):
        """Word-form numbers used to stop at 'ocho' (8) in this pattern while
        digits ('9') already worked — real bug found 2026-07-16."""
        intent = detector.detect("somos nueve, queremos bucear", state)
        assert intent.group_size == 9

    def test_detect_group_size_somos_diez(self, detector, state):
        intent = detector.detect("somos diez, queremos bucear", state)
        assert intent.group_size == 10

    def test_detect_group_size_family_of_nine_english(self, detector, state):
        intent = detector.detect("family of nine", state)
        assert intent.group_size == 9

    def test_detect_group_size_me_plus_n_friends(self, detector, state):
        """Fase 7 candidato / bug real hallado en la batería de la Fase 6
        (docs/robustness/live-test-battery-fase6.md B3): 'me plus 3 friends'
        son 4 personas (el hablante + 3), no 3 — el patrón genérico de conteo
        capturaba solo el número pegado a 'friends' sin sumar al hablante."""
        intent = detector.detect("me plus 3 friends, ppl wanna try diving first time", state)
        assert intent.group_size == 4

    def test_detect_group_size_n_plus_me(self, detector, state):
        intent = detector.detect("3 friends plus me want to dive", state)
        assert intent.group_size == 4

    def test_detect_mixed_group_yo_buceo_amigo_snorkel(self, detector, state):
        intent = detector.detect("yo quiero buceo y mi amigo snorkel", state)
        assert intent.group_allocation is not None
        assert intent.group_allocation.get("certified_diving") == 1
        assert intent.group_allocation.get("snorkel") == 1
        assert intent.group_size == 2
    
    def test_detect_mixed_group_uno_buceo_otro_snorkel(self, detector, state):
        intent = detector.detect("uno quiere buceo y el otro snorkel", state)
        assert intent.group_allocation is not None
        assert intent.group_allocation.get("certified_diving") == 1
        assert intent.group_allocation.get("snorkel") == 1
    
    def test_detect_mixed_minicourse_snorkel(self, detector, state):
        intent = detector.detect("yo haría el minicurso y mi novia snorkel", state)
        # Should detect minicourse activity at minimum
        assert intent.activity == "minicourse"
        assert intent.is_certified is False


class TestLastDiveDetection:
    
    def test_detect_last_dive_6_months(self, detector, state):
        # Note: This requires exact phrasing with numbers
        intent = detector.detect("mi última inmersión fue hace 6 meses", state)
        assert intent.last_dive_over_2_years is False
        assert "last_dive_over_2_years" in intent.detected_fields
    
    def test_detect_last_dive_3_years(self, detector, state):
        intent = detector.detect("última inmersión fue hace 3 años", state)
        assert intent.last_dive_over_2_years is True
    
    def test_detect_last_dive_english(self, detector, state):
        intent = detector.detect("my last dive was 1 year ago", state)
        assert intent.last_dive_over_2_years is False

    def test_hace_como_n_anos_does_not_leak_into_ages(self, detector, state):
        """Bug real hallado en la batería de la Fase 6 (docs/robustness/
        live-test-battery-fase6.md D5): 'hace como 3 años que no buceo' —
        la guarda que descarta 'hace N años' como edad solo miraba 8
        caracteres atrás, y 'como' entre 'hace' y el número empujaba 'hace'
        fuera de esa ventana, colando un niño fantasma de 3 años que
        contaminaría kids_under_8_count en el checkout."""
        intent = detector.detect("hace como 3 años que no buceo, seré yo solo", state)
        assert intent.ages == []
        assert intent.last_dive_over_2_years is True

    def test_hace_ya_n_anos_does_not_leak_into_ages_english(self, detector, state):
        intent = detector.detect("it's been like 4 years since i last dived", state)
        assert intent.ages == []


class TestDurationDetection:
    
    def test_detect_single_day(self, detector, state):
        intent = detector.detect("estoy solo un día", state)
        assert intent.duration == "single_day"
        assert "duration" in intent.detected_fields
    
    def test_detect_multi_day(self, detector, state):
        intent = detector.detect("estoy varios días en las islas", state)
        assert intent.duration == "multi_day"
    
    def test_detect_multi_day_number(self, detector, state):
        intent = detector.detect("estoy 3 días", state)
        assert intent.duration == "multi_day"

    def test_detect_multi_day_without_accent_typo(self, detector, state):
        """'dias'/'dia' without the accent (very common on phones) used to
        silently fail to match — real bug found 2026-07-16."""
        intent = detector.detect("estamos 5 dias en la isla, que podemos hacer?", state)
        assert intent.duration == "multi_day"

    def test_detect_varios_dias_without_accent_typo(self, detector, state):
        intent = detector.detect("vamos varios dias a la isla", state)
        assert intent.duration == "multi_day"

    def test_detect_single_day_without_accent_typo(self, detector, state):
        intent = detector.detect("estoy solo un dia", state)
        assert intent.duration == "single_day"


class TestNationalityDetection:

    def test_colombian_by_city_medellin(self, detector, state):
        """A common way to self-identify as Colombian is naming a Colombian
        city instead of the country — real gap found 2026-07-16."""
        intent = detector.detect("soy de Medellin, quiero bucear", state)
        assert intent.is_colombian is True

    def test_colombian_by_city_bogota(self, detector, state):
        intent = detector.detect("somos de Bogota", state)
        assert intent.is_colombian is True

    def test_not_colombian_when_only_currently_in_cartagena(self, detector, state):
        """'estoy en Cartagena' is current whereabouts, not an origin claim —
        must NOT be misread as Colombian nationality (a foreign tourist could
        say this)."""
        intent = detector.detect("estoy en Cartagena, soy de España", state)
        assert intent.is_colombian is not True


class TestLocationDetection:
    
    def test_detect_cartagena(self, detector, state):
        intent = detector.detect("estoy en Cartagena", state)
        assert intent.location == "cartagena"
        assert "location" in intent.detected_fields
    
    def test_detect_isla_grande(self, detector, state):
        intent = detector.detect("estoy en Isla Grande", state)
        assert intent.island == "isla_grande"
        assert intent.location == "island"
    
    def test_detect_hotel_pao_pao(self, detector, state):
        intent = detector.detect("estoy en el hotel Pao Pao", state)
        assert intent.hotel == "pao_pao"
        assert "hotel" in intent.detected_fields
    
    def test_detect_hotel_cocoliso(self, detector, state):
        intent = detector.detect("me hospedo en Cocoliso", state)
        assert intent.hotel == "cocoliso"


class TestCompleteScenarios:
    
    def test_complete_certified_group_spanish(self, detector, state):
        intent = detector.detect("Hola somos dos personas que queremos hacer buceo y estamos certificados", state)
        assert intent.language == "es"
        assert intent.activity == "certified_diving"
        assert intent.is_certified is True
        assert intent.group_size == 2
        assert intent.confidence > 0.5
    
    def test_complete_certified_single_english(self, detector, state):
        intent = detector.detect("Hello I am a certified diver and want to dive", state)
        assert intent.language == "en"
        assert intent.activity == "certified_diving"
        assert intent.is_certified is True
        assert intent.confidence > 0.4
    
    def test_complete_minicourse_spanish(self, detector, state):
        intent = detector.detect("Hola quiero hacer el minicurso de buceo, es mi primera vez", state)
        assert intent.language == "es"
        assert intent.activity == "minicourse"
        assert intent.is_certified is False
        assert intent.confidence > 0.4
    
    def test_complete_mixed_group(self, detector, state):
        intent = detector.detect("Somos dos, yo quiero buceo certificado y mi novia snorkel", state)
        assert intent.language == "es"
        assert intent.group_size == 2
        assert intent.is_certified is True
        assert intent.activity == "certified_diving"
        # Group allocation might not be detected in all cases, but key info is there
        assert intent.confidence > 0.5
    
    def test_ambiguous_diving_no_certification(self, detector, state):
        intent = detector.detect("Hola quiero bucear", state)
        assert intent.language == "es"
        assert intent.activity == "certified_diving"
        assert intent.is_certified is None
    
    def test_diving_with_location(self, detector, state):
        intent = detector.detect("Quiero hacer buceo, estoy en Cartagena y soy certificado", state)
        assert intent.activity == "certified_diving"
        assert intent.is_certified is True
        assert intent.location == "cartagena"


class TestConfidenceScoring:
    
    def test_high_confidence_complete_info(self, detector, state):
        intent = detector.detect("Hola somos dos buzos certificados que queremos hacer buceo", state)
        assert intent.confidence >= 0.5
    
    def test_medium_confidence_partial_info(self, detector, state):
        intent = detector.detect("Hola quiero bucear", state)
        # Should detect language and activity at minimum
        assert intent.confidence >= 0.2
    
    def test_low_confidence_minimal_info(self, detector, state):
        intent = detector.detect("Hola", state)
        assert intent.confidence <= 0.2


class TestOpenWaterCertSplit:
    """v0.17.2: 'dos tenemos open water y una no' must yield a cert+minicourse
    allocation so the bot skips the ambiguous certification question."""

    def test_es_open_water_and_one_not(self, detector, state):
        intent = detector.detect(
            "hola somos tres personas que queremos bucear, dos tenemos el open water y una no",
            state,
        )
        assert intent.group_allocation == {"certified_diving": 2, "minicourse": 1}
        assert intent.group_size == 3

    def test_es_con_open_water_short(self, detector, state):
        intent = detector.detect("somos 3, 2 con open water y 1 no", state)
        assert intent.group_allocation == {"certified_diving": 2, "minicourse": 1}

    def test_en_have_open_water(self, detector, state):
        intent = detector.detect("we are three, two have open water and one does not", state)
        assert intent.group_allocation == {"certified_diving": 2, "minicourse": 1}


class TestCertificationOnlyNotCertifiedCount:
    """Regression: "somos 2 ... y uno no esta certificado" only states the
    NOT-certified count (no explicit "N certified" phrase) — the certified
    count must be inferred as the complement of the known group size, and the
    activity must be inferred as diving even without the word "buceo", since
    certification is a diving-only concept in this business. Also covers the
    typo "certficado" that was breaking detection entirely."""

    def test_es_only_not_certified_count_no_activity_word(self, detector, state):
        intent = detector.detect(
            "Hola somos dos personas y uno no esta certificado", state
        )
        assert intent.activity == "certified_diving"
        assert intent.group_allocation == {"certified_diving": 1, "minicourse": 1}
        assert intent.confidence > 0.2

    def test_es_typo_certficado_still_detected(self, detector, state):
        """The exact reported typo: "certficado" (missing the second "i")."""
        intent = detector.detect(
            "Hola somos dos personas y uno no esta certficado", state
        )
        assert intent.activity == "certified_diving"
        assert intent.is_certified is False
        assert intent.group_allocation == {"certified_diving": 1, "minicourse": 1}

    def test_es_three_people_one_not_certified(self, detector, state):
        intent = detector.detect("somos 3, uno no esta certificado", state)
        assert intent.group_allocation == {"certified_diving": 2, "minicourse": 1}

    def test_en_one_is_not_certified(self, detector, state):
        intent = detector.detect(
            "we are 2 and one is not certified", state
        )
        assert intent.activity == "certified_diving"
        assert intent.group_allocation == {"certified_diving": 1, "minicourse": 1}

    def test_certification_mention_without_group_size_still_infers_activity(
        self, detector, state
    ):
        """No group size at all — still infers diving from "certficado" alone
        (typo) so a solo "estoy certficado" doesn't fall through to RAG."""
        intent = detector.detect("hola estoy certficado", state)
        assert intent.activity == "certified_diving"
        assert intent.is_certified is True


class TestSingularSelfInfersOnePerson:
    """A singular first-person self-identification as a diver means 1 person, so
    the flow shouldn't ask "¿cuántas personas?" (reported miss: "hola soy Sofia,
    ya soy certificada, quiero unas inmersiones" was asking for a headcount)."""

    @pytest.mark.parametrize(
        "message",
        [
            "hola soy Sofia, ya soy certificada, quiero hacer unas inmersiones en Cartagena",
            "soy certificado, quiero bucear en cartagena",
            "quiero bucear, soy certificada",
            "soy buzo open water",
            "estoy certificado y quiero bucear",
            "i am a certified diver, i want to dive in cartagena",
        ],
    )
    def test_singular_certified_self_infers_one(self, detector, state, message):
        assert detector.detect(message, state).group_size == 1

    @pytest.mark.parametrize(
        "message",
        [
            "soy certificado y quiero bucear con mi novia",   # companion
            "soy certificado, quiero bucear con 3 amigos",    # explicit other count
            "somos certificados, queremos bucear",            # plural
            "quiero reservar para mi familia, soy certificado",  # collective
            "soy certificado pero mi esposa no bucea",        # companion (spouse)
        ],
    )
    def test_more_than_one_hint_stays_conservative(self, detector, state, message):
        # Any "more than one" signal must NOT be collapsed to 1 (a wrong 1 would
        # undercount the booking); the flow asks instead.
        assert detector.detect(message, state).group_size != 1
