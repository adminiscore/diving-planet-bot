"""mej-3 (21-oct): el juez con votos en los criterios dudosos y la medida de su estabilidad, sin llamar a la API."""
import json

import pytest

from scripts import estabilidad_juez as ej
from scripts import judge_golden_set as jg


class _Resp:
    def __init__(self, contenido):
        self.choices = [type("C", (), {"message": type("M", (), {"content": contenido})()})()]
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": None})()


class _ClienteFalso:
    """Devuelve los veredictos de la lista, uno por llamada."""

    def __init__(self, veredictos):
        self.veredictos = list(veredictos)
        self.llamadas = 0
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **_kw):
        self.llamadas += 1
        v = self.veredictos.pop(0)
        cita = "precio 100" if v == "no_cumple" else None
        return _Resp(json.dumps({"verdict": v, "motivo": v, "evidencia_bot": cita}))


_DIALOGO = {"id": "d1", "category": "info"}
_CRITERIO = {"id": "c1", "check": "da el precio correcto"}
_RECORDS = [{"turn": 1, "msg": "¿cuánto cuesta?", "reply": "El precio 100 USD", "bubbles": ["El precio 100 USD"],
             "conv": 1}]


@pytest.fixture
def votos(monkeypatch):
    def poner(n):
        monkeypatch.setattr(jg, "VOTOS", n)
    return poner


def _juzgar(cliente):
    return jg.evaluate_criterion(cliente, "gpt-5-mini", "medium", "REF", _DIALOGO, _RECORDS, _CRITERIO, [_CRITERIO])


def test_con_un_voto_es_el_juez_de_siempre(votos):
    votos(1)
    cliente = _ClienteFalso(["no_cumple"])
    assert _juzgar(cliente)["verdict"] == "no_cumple" and cliente.llamadas == 1


def test_un_cumple_no_se_vuelve_a_preguntar(votos):
    votos(3)
    cliente = _ClienteFalso(["cumple"])
    r = _juzgar(cliente)
    assert r["verdict"] == "cumple" and cliente.llamadas == 1 and "votos" not in r


def test_un_suspenso_suelto_lo_tumba_la_mayoria(votos):
    votos(3)
    cliente = _ClienteFalso(["no_cumple", "cumple", "cumple"])
    r = _juzgar(cliente)
    assert r["verdict"] == "cumple" and r["votos"] == ["no_cumple", "cumple", "cumple"] and cliente.llamadas == 3
    assert r["usage"]["input"] == 30


def test_un_suspenso_que_se_repite_se_queda_con_su_evidencia(votos):
    votos(3)
    r = _juzgar(_ClienteFalso(["no_cumple", "cumple", "no_cumple"]))
    assert r["verdict"] == "no_cumple" and r["evidencia_bot"] == "precio 100"


def test_sin_mayoria_queda_para_revisar():
    r = jg.mayoria([{"verdict": "no_cumple"}, {"verdict": "cumple"}, {"verdict": "no_aplica"}])
    assert r["verdict"] == "revisar" and "sin mayoría" in r["reason"]


def test_la_clave_de_la_cache_solo_cambia_con_votos(votos):
    votos(1)
    una = jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje")
    votos(3)
    assert jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje") != una
    votos(1)
    assert jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje") == una


def test_la_estabilidad_cuenta_los_criterios_que_cambian():
    def pasada(v2):
        return [{"id": "d1", "category": "info", "criteria": [
            {"id": "c1", "verdict": "cumple", "by": "gpt-5-mini"},
            {"id": "c2", "verdict": v2, "by": "gpt-5-mini"},
            {"id": "auto1", "verdict": "cumple", "by": "auto"},
        ]}]

    informe = ej.comparar([pasada("cumple"), pasada("no_cumple")])
    assert informe["criterios_llm"] == 2 and informe["criterios_que_cambian"] == 1
    assert informe["cambian"] == [{"dialogo": "d1", "criterio": "c2", "veredictos": ["cumple", "no_cumple"]}]
    assert informe["cambios_por_tipo"] == {"cumple -> no_cumple": 1}
