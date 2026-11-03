"""CALN-16 (3-nov, sparring s03h): el escritor con los hechos también busca. «Is lunch included? I'm vegetarian.» solo
pide «incluye» y, sin la búsqueda, lo que el cliente afirma en el mismo mensaje no llegaba (food_policy). Sin red."""
import asyncio

from src.agents import redactor_hechos
from src.flows.state import ConversationState


def test_el_escritor_con_hechos_no_pide_ir_sin_busqueda(monkeypatch):
    from src.agents import supervisor

    pedido = {}

    async def _rag_answer(message, **kw):
        pedido.update(kw)
        return "Yes, lunch is included. The vegetarian option is rice with vegetables."

    monkeypatch.setattr(supervisor, "rag_answer", _rag_answer)
    st = ConversationState(conversation_id="caln16", language="en")
    st.detected_activity, st.location = "snorkel", "cartagena"
    mensaje = "Is lunch included? I'm vegetarian."
    respuesta = asyncio.run(redactor_hechos._con_el_escritor(
        st, mensaje, [{"role": "user", "content": mensaje}], [{"actividad": "snorkel", "incluye": ["lunch"]}], ["incluye"]))
    assert respuesta and "vegetarian" in respuesta
    assert pedido.get("hechos") and not pedido.get("sin_busqueda") and pedido.get("sin_fichas") is True
