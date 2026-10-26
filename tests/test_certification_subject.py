"""De quien habla una frase de certificacion, en los dos ordenes del sujeto (2026-09-15).

Lo que se dice de otra persona no fija el estado de quien escribe. El sujeto delante del
verbo ("mi amigo no esta certificado") ya se reconocia; faltaba el sujeto pospuesto ("no
es certificado mi acompañante"), que se atribuia a quien escribe. Un complemento ("con mi
pareja", "para mi novia") no es el sujeto.
lat-11 T6d (26-oct): fuera las comprobaciones de `other_person_certification` (se quitó con IntentDetector; esos
campos los decide el extractor).
"""

import pytest

from src.agents.intent_detector import certification_claim


@pytest.mark.parametrize("message", [
    "mi amigo no esta certificado",          # sujeto delante
    "no es certificado mi acompañante",      # sujeto detras
    "está certificada mi novia",
    "no tiene licencia mi amigo, yo si",
    "is certified my wife",
])
def test_statement_about_another_person_is_not_the_writers(message):
    assert certification_claim(message) is None


@pytest.mark.parametrize("message, writer", [
    ("soy buzo certificado y viene conmigo mi novia", True),
    ("i am a certified diver with a companion, what do you offer for diving", True),
    ("no estoy certificado y quiero bucear con mi pareja", False),
])
def test_complements_do_not_steal_the_writers_statement(message, writer):
    assert certification_claim(message) is writer


@pytest.mark.parametrize("message", ["es para mi novia", "quiero bucear con mi pareja"])
def test_no_certification_statement_no_signal(message):
    assert certification_claim(message) is None
