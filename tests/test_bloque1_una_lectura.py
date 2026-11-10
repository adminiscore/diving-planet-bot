"""Bloque 1 (10-nov): una sola lectura por turno. `datos_del_extractor` soltaba la tarea al empezar a esperarla y publicaba
la lectura al final; en el hueco, `lectura_del_extractor` (el redactor, el enrutado) relanzaba el extractor y vaciaba el
lector del grupo. En el panel, 23 a 29 de cada 117 turnos a partir del segundo llamaban dos veces al extractor
(visto-6926: una vuelta con el reparto y otra sin él). Sin IA."""
import asyncio

from src.agents import extractor_turno
from src.agents.nucleo import extractor as nucleo
from src.flows.state import ConversationState

MENSAJE = "somos tres, dos bucean y mi hija hace snorkel"


def _conv() -> ConversationState:
    return ConversationState(conversation_id="b1-una-lectura", language="es")


def test_lo_que_pide_la_lectura_en_el_hueco_espera_la_misma_y_no_vacia_el_lector(monkeypatch):
    llamadas = []

    async def turno():
        puerta = asyncio.Event()

        async def extraer(message, **kw):
            llamadas.append(message)
            await puerta.wait()
            return {"group_size": 3}

        monkeypatch.setattr(extractor_turno, "extraer_turno", extraer)
        st = _conv()
        lector = asyncio.ensure_future(asyncio.sleep(10))
        st._lector_grupo = lector
        consumo = asyncio.ensure_future(nucleo.datos_del_extractor(st, MENSAJE))
        await asyncio.sleep(0)  # `datos_del_extractor` ya espera al extractor
        lee = asyncio.ensure_future(nucleo.lectura_del_extractor(st, MENSAJE))
        await asyncio.sleep(0)
        assert st._lector_grupo is lector  # antes, el relanzamiento lo dejaba a None
        puerta.set()
        assert await lee == {"group_size": 3}
        assert await consumo == {"group_size": 3}
        lector.cancel()

    asyncio.run(turno())
    assert llamadas == [MENSAJE]


def test_al_publicar_la_lectura_la_tarea_se_suelta_como_antes(monkeypatch):
    """`guardar_lo_dicho_en_el_pase` toma «la tarea sigue sin usar al final del turno» como señal de que el núcleo no corrió."""
    async def extraer(message, **kw):
        return {"location": "island"}

    monkeypatch.setattr(extractor_turno, "extraer_turno", extraer)
    st = _conv()
    assert asyncio.run(nucleo.datos_del_extractor(st, "nos quedamos en Mulata")) == {"location": "island"}
    assert st._extraccion_adelantada is None
    assert st._lectura_del_turno == ("nos quedamos en Mulata", {"location": "island"})
