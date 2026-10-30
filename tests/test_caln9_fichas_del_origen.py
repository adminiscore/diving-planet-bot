"""CALN-9a (30-oct; diseño docs/robustness/caln/diseno-caln9-origen.md): con el origen del cliente sabido, al escritor
solo le llega la ficha de su origen de cada plan."""
from src.agents.rag_agent import fichas_del_origen


def _ficha(service_id: str, origen: str) -> dict:
    return {"content": f"ficha de {service_id}",
            "metadata": {"source": "services", "key": f"ficha:{service_id}", "service_id": service_id, "origin": origen}}


FAQ = {"content": "¿Qué pasa si llueve?", "metadata": {"source": "faqs", "key": "faq:lluvia"}}


def test_si_vino_la_del_suyo_la_del_otro_origen_sale():
    """precio-desde-islas-vs-cartagena: en las islas, la ficha de Cartagena («lancha Cartagena-Islas incluida») sobra."""
    docs = [_ficha("2_dives_1_day", "cartagena"), _ficha("2_dives_1_day_already_on_island", "islas"), FAQ]
    assert fichas_del_origen(docs, "islas", "es") == [docs[1], FAQ]


def test_si_solo_vino_la_del_otro_se_cambia_por_la_del_suyo():
    salida = fichas_del_origen([_ficha("minicourse", "cartagena"), FAQ], "islas", "es")
    assert salida[0]["metadata"]["service_id"] == "minicourse_already_on_island"
    assert salida[0]["metadata"]["origin"] == "islas"
    assert "Islas del Rosario" in salida[0]["content"] and "Minicurso" in salida[0]["content"]
    assert salida[1] == FAQ
    vuelta = fichas_del_origen([_ficha("snorkeling_already_on_island", "islas")], "cartagena", "en")
    assert vuelta[0]["metadata"]["service_id"] == "snorkeling" and "Cartagena" in vuelta[0]["content"]


def test_sin_origen_o_sin_pareja_no_cambia_nada():
    docs = [_ficha("2_dives_1_day", "cartagena"), _ficha("2_dives_1_day_already_on_island", "islas"), FAQ]
    assert fichas_del_origen(docs, None, "es") == docs
    assert fichas_del_origen(docs, "", "es") == docs
    solo = [_ficha("divemaster", "cartagena")]  # sin servicio en las islas
    assert fichas_del_origen(solo, "islas", "es") == solo
