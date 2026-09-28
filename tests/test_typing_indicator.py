"""l2-3: "escribiendo…" en el chat mientras el bot prepara la respuesta.

Una pregunta tarda ~4 s (medido en PRE el 28-sep). Se fija aquí, sin red:
1. se enciende antes de preparar la respuesta y se apaga DESPUÉS de enviarla;
2. se apaga también si preparar la respuesta falla;
3. si Chatwoot falla, el turno sigue (es solo un aviso);
4. con el interruptor apagado no se llama a Chatwoot;
5. la llamada es la de la API de Chatwoot (`toggle_typing_status`, on/off).
"""

import httpx
import pytest

from src.channels import chatwoot
from src.config import settings
from src.flows.state import ConversationState


@pytest.fixture
def pasos(monkeypatch):
    orden = []

    async def fake_typing(conversation_id, on):
        orden.append(f"typing-{'on' if on else 'off'}")

    async def fake_route(state, message):
        orden.append("preparar")
        return "respuesta"

    async def fake_finalize(conversation_id, state, response):
        orden.append("enviar")

    async def fake_load(conversation_id):
        return ConversationState(conversation_id=conversation_id, language="es")

    async def fake_noop(*a, **k):
        return None

    async def fake_mark(key):
        return False

    monkeypatch.setattr(chatwoot, "set_typing", fake_typing)
    monkeypatch.setattr(chatwoot, "route_message", fake_route)
    monkeypatch.setattr(chatwoot, "finalize_chatwoot_delivery", fake_finalize)
    monkeypatch.setattr(chatwoot.state_store, "load_state", fake_load)
    monkeypatch.setattr(chatwoot.state_store, "save_state", fake_noop)
    monkeypatch.setattr(chatwoot.state_store, "check_and_mark_processed", fake_mark)
    return orden


def _mensaje(n):
    return {"id": n, "message_type": "incoming", "content": "¿qué incluye el buceo?", "conversation": {"id": 900 + n}, "sender": {"name": "t"}}


@pytest.mark.asyncio
async def test_se_enciende_antes_de_preparar_y_se_apaga_despues_de_enviar(pasos):
    await chatwoot.handle_message(_mensaje(1))
    assert pasos == ["typing-on", "preparar", "enviar", "typing-off"]


@pytest.mark.asyncio
async def test_se_apaga_aunque_preparar_la_respuesta_falle(pasos, monkeypatch):
    async def falla(state, message):
        pasos.append("preparar")
        raise RuntimeError("fallo del LLM")

    monkeypatch.setattr(chatwoot, "route_message", falla)
    with pytest.raises(RuntimeError):
        await chatwoot.handle_message(_mensaje(2))
    assert pasos == ["typing-on", "preparar", "typing-off"]


class _Resp:
    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


def _cliente_falso(visto, code=200, error=None):
    class _Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            if error:
                raise error
            visto.append((url, json))
            return _Resp(code)

    return _Cliente


@pytest.mark.asyncio
async def test_llama_a_toggle_typing_status_con_on_y_off(monkeypatch):
    visto = []
    monkeypatch.setattr(settings, "chatwoot_typing_indicator", True)
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", _cliente_falso(visto))
    await chatwoot.set_typing("77", True)
    await chatwoot.set_typing("77", False)
    assert [j for _, j in visto] == [{"typing_status": "on"}, {"typing_status": "off"}]
    assert all(u.endswith("/conversations/77/toggle_typing_status") for u, _ in visto)


@pytest.mark.asyncio
async def test_si_chatwoot_falla_no_rompe_nada(monkeypatch):
    monkeypatch.setattr(settings, "chatwoot_typing_indicator", True)
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", _cliente_falso([], error=httpx.ConnectError("caido")))
    await chatwoot.set_typing("77", True)  # no lanza
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", _cliente_falso([], code=500))
    await chatwoot.set_typing("77", False)  # no lanza


@pytest.mark.asyncio
async def test_con_el_interruptor_apagado_no_se_llama_a_chatwoot(monkeypatch):
    visto = []
    monkeypatch.setattr(settings, "chatwoot_typing_indicator", False)
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", _cliente_falso(visto))
    await chatwoot.set_typing("77", True)
    assert visto == []
