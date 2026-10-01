"""2-oct, flag `juez_privacidad_por_linea`: el juez tapa los datos personales línea a línea.

`redact_pii` tapa TODOS los números largos de un texto si en cualquier parte aparece "pasaporte", "cuenta",
"Bancolombia"... Sobre el contexto entero del juez, una FAQ de pagos ("con tarjeta extranjera se usa el pasaporte")
borraba todos los precios del catálogo de 1.000.000 COP o más y el juez rechazaba el precio correcto (reproducido en
PRE con `scripts/reproducir_juez_pre.py paquete-5-buceos-cop-refresh-y-hoteles`). Se fija:
1. por líneas, los precios del catálogo quedan y una cédula del cliente se sigue tapando;
2. con el flag, el juez recibe los precios completos; sin él, el comportamiento de antes (tapados).
"""

import pytest

from src.agents import grounding_check
from src.privacy import redact_pii, redact_pii_por_lineas

CONTEXTO = (
    "CATÁLOGO OFICIAL\n"
    "- Paquete de 5 inmersiones (2 dias): 392 USD / 1.429.000 COP online, 436 USD / 1.587.000 COP normal\n"
    "[8] Fuente: policies\n"
    "Respuesta: Los clientes extranjeros pagan con tarjeta; con tarjeta extranjera se usa el pasaporte como documento.\n"
    "Cliente: mi cédula es 1.023.456.789"
)


def test_por_lineas_quedan_los_precios_y_se_tapa_la_cedula():
    assert "1.429.000" not in redact_pii(CONTEXTO)  # el fallo: todo el texto de golpe
    limpio = redact_pii_por_lineas(CONTEXTO)
    assert "1.429.000" in limpio and "1.587.000" in limpio
    assert "1.023.456.789" not in limpio and "[REDACTED_NUMBER]" in limpio


@pytest.mark.parametrize("flag,ve_el_precio", [(True, True), (False, False)])
@pytest.mark.asyncio
async def test_el_juez_ve_los_precios_con_el_flag(monkeypatch, flag, ve_el_precio):
    visto = []

    class _Completions:
        async def create(self, **kwargs):
            visto.append(kwargs["messages"][-1]["content"])
            msg = type("M", (), {"content": "- El paquete de 5 cuesta 1.429.000 COP online SÍ\n\nGROUNDED"})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(grounding_check, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(grounding_check.settings, "juez_privacidad_por_linea", flag)
    monkeypatch.setattr(grounding_check.settings, "juez_segunda_opinion", False)
    await grounding_check.is_grounded("El paquete de 5 cuesta 1.429.000 COP online.", CONTEXTO, lang="es")
    contexto_enviado = visto[0].split("RESPUESTA:")[0]
    assert ("1.429.000" in contexto_enviado) is ve_el_precio
    assert "1.023.456.789" not in contexto_enviado
