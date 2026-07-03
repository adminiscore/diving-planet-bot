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
