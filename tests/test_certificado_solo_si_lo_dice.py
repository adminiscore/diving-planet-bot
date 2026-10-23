"""19-oct (ronda mod-G): con `certificado_solo_si_lo_dice` (promocionado; su flag se borró en sim-5) la regla del código "buceo certificado ⇒ certificado" se
quita (decisión de Gadea: «fun dives» no dice que esté certificado), y el extractor tiene que ver la certificación en
todo lo que SÍ la dice: «completé el curso básico» o «necesito un refresher» (en la ronda mod-G se repreguntaban)."""

import pytest

from src.agents import extractor_turno as et


@pytest.mark.asyncio
async def test_la_regla_de_is_certified_nombra_todas_las_formas_de_decirlo():
    visto = {}

    class _Cliente:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    visto.update(kwargs)
                    raise RuntimeError("sin red en el test")

    await et.extraer_turno("yo complete el curso básico el 3 de abril", lang="es", client=_Cliente())
    sistema = visto["messages"][0]["content"]
    assert et.IS_CERTIFIED_DICHO_ES in sistema
    assert et.IS_CERTIFIED_HOY_ES not in sistema
