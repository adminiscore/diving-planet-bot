"""arq-5c (23-oct, flag `dos_monedas_sin_nacionalidad`, decisión de Gadea): sin saber si el cliente es colombiano, el
precio de los hechos va en USD y en COP (G10 nº 5: «¿cuánto cuesta para colombianos?» recibía solo USD)."""

import pytest

from src.flows import hechos as hechos_mod
from src.flows.state import ConversationState


def _bloque(colombiano=None, mixto=False, actividad="snorkel"):
    st = ConversationState(conversation_id="arq5c", language="es")
    st.is_colombian = colombiano
    st.mixed_nationality_notice = mixto
    return hechos_mod.hechos(st, ["precio"], [actividad])[0]


@pytest.mark.parametrize("colombiano, mixto, dos", [
    (None, False, True), (True, False, False), (False, False, False),
    (None, True, False),  # el grupo mixto paga en USD
])
def test_las_dos_monedas_solo_sin_saber_la_nacionalidad(colombiano, mixto, dos):
    b = _bloque(colombiano, mixto)
    assert ("precio_cop" in b) is dos
    if dos:
        assert all("COP" in p["online"] for p in b["precio_cop"].values()) and b["moneda"] == "USD / COP"


def test_el_acompanante_y_los_otros_planes_tambien(monkeypatch):
    assert "COP" in next(iter(_bloque(actividad="companion")["precio_cop"].values()))["online"]
    assert all("COP" in p["precio_cop"]["online"] for p in _bloque(actividad="certified_diving")["otros_planes"])


def test_faltan_mira_tambien_el_precio_en_cop(monkeypatch):
    b = _bloque()
    usd = " ".join(p[k] for p in b["precio"].values() for k in ("online", "normal"))
    assert hechos_mod.faltan(usd, [b], ["precio"])  # faltan los de COP
    cop = " ".join(p[k] for p in b["precio_cop"].values() for k in ("online", "normal"))
    assert hechos_mod.faltan(f"{usd} {cop}", [b], ["precio"]) == []
