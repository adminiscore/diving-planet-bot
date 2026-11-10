"""Bloque 1 (10-nov): el escritor, con los datos ya guardados. La respuesta en paralelo se escribía antes de que la
extracción guardara lo que trae el mensaje, con una copia del estado que repetía sus reglas (`lectura.foto_del_turno` y
la de gen-14 solo con la nacionalidad). Ahora espera a lo guardado (`extractor.con_lo_guardado`): la extracción del
núcleo avisa al guardar (`marcar_guardado`) y un turno que contesta sin el núcleo guarda antes de contestar lo mismo que
guardaba al final. Frases nuestras, sin IA."""
import asyncio

from src.agents import conversational_core as core
from src.agents import extractor_turno, redactor_hechos, supervisor
from src.agents.nucleo import extractor as nucleo
from src.flows.state import ConversationState

MENSAJE = "somos de Medellín, ¿cuánto cuesta el minicurso?"


def _conv() -> ConversationState:
    st = ConversationState(conversation_id="b1-lo-guardado", language="es")
    st._guardado = asyncio.Event()  # como lo deja `lanzar_extraccion_adelantada` al empezar el turno
    return st


def _escritor_que_apunta(monkeypatch) -> list:
    """El RAG sin búsqueda ni modelo: apunta la nacionalidad del estado con que se escribe."""
    vista = []

    async def nada(*a, **kw):
        return None

    def entradas(state, history, message):
        vista.append(state.is_colombian)
        return {}

    async def contesta(*a, **kw):
        return "El minicurso cuesta…"

    monkeypatch.setattr(core, "await_pending_notes", nada)
    monkeypatch.setattr(core, "_con_hechos", nada)
    monkeypatch.setattr(core, "_hechos_para_el_rag", nada)
    monkeypatch.setattr(core, "_entradas_rag", entradas)
    monkeypatch.setattr(core, "_precios_por_codigo", lambda state, entradas: False)
    monkeypatch.setattr(core, "contar_si_el_escritor_pregunta", lambda entradas, answer: None)
    monkeypatch.setattr(supervisor, "rag_answer", contesta)
    return vista


def test_la_respuesta_en_paralelo_escribe_con_la_nacionalidad_ya_guardada(monkeypatch):
    vista = _escritor_que_apunta(monkeypatch)

    async def turno():
        st = _conv()
        st._pending_answer = asyncio.create_task(core._rag_answer(st, MENSAJE, history=[], puerta_al_recoger=True))
        for _ in range(5):
            await asyncio.sleep(0)
        assert vista == []  # espera: la extracción aún no ha guardado
        st.is_colombian = True  # lo que guarda la extracción del núcleo (`_poner_nacionalidad`)
        nucleo.marcar_guardado(st)
        assert await st._pending_answer == "El minicurso cuesta…"

    asyncio.run(turno())
    assert vista == [True]  # antes, la copia de gen-14; ahora, lo guardado


def test_quien_recoge_la_respuesta_no_se_queda_esperando(monkeypatch):
    """Si el turno recoge la respuesta sin pasar por la extracción del núcleo, no hay nada que esperar."""
    vista = _escritor_que_apunta(monkeypatch)

    async def turno():
        st = _conv()
        st._pending_answer = asyncio.create_task(core._rag_answer(st, MENSAJE, history=[], puerta_al_recoger=True))
        await asyncio.sleep(0)
        return await asyncio.wait_for(core._take_parallel_answer(st), timeout=2)

    assert asyncio.run(turno()) == "El minicurso cuesta…"
    assert vista == [None]  # con lo que había: el turno no guardó nada antes


def test_sin_el_nucleo_se_guarda_antes_de_contestar_y_se_lee_una_vez(monkeypatch):
    llamadas = []

    async def extraer(message, **kw):
        llamadas.append(message)
        return {"is_colombian": True}

    monkeypatch.setattr(extractor_turno, "extraer_turno", extraer)

    async def turno():
        st = _conv()
        st._extraccion_adelantada = asyncio.ensure_future(extraer(MENSAJE))
        await nucleo.con_lo_guardado(st, MENSAJE)  # quien contesta sin el núcleo (una puerta del enrutado)
        assert st.is_colombian is True and st._guardado.is_set()
        assert await nucleo.lectura_del_extractor(st, MENSAJE) == {"is_colombian": True}  # la misma, publicada
        await nucleo.guardar_lo_dicho_sin_nucleo(st)  # el cierre del turno ya no tiene nada que guardar

    asyncio.run(turno())
    assert llamadas == [MENSAJE]


def test_la_copia_ya_no_repite_las_reglas_de_la_extraccion():
    """Lo que el extractor lee y la extracción no guardó no llega a los hechos por la copia; lo guardado, sí."""
    datos = {"is_colombian": True, "group_size": 4, "edades": [9], "group_allocation": {"snorkel": 2}}
    st = ConversationState(conversation_id="b1-copia", language="es")
    foto = redactor_hechos._foto(st, datos, "cartagena", "somos 4 colombianos, mi hijo tiene 9")
    assert foto.is_colombian is None
    assert not (foto.detected_group_size or foto.detected_ages or foto.detected_group_allocation)
    st.is_colombian, st.detected_group_size = True, 4
    foto = redactor_hechos._foto(st, datos, "cartagena", "somos 4 colombianos, mi hijo tiene 9")
    assert foto.is_colombian is True and foto.detected_group_size == 4
