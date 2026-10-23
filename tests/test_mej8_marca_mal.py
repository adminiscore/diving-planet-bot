"""mej-8 (24-oct, flag `marcar_mal`): «#mal» de quien prueba el bot. Sin red:
1. qué cuenta como marca y qué comentario lleva;
2. con el flag, el bot no lo contesta (ni por el webhook ni por el repaso de cada segundo): etiqueta y acuse;
3. sin el flag, se contesta como cualquier mensaje;
4. la etiqueta se AÑADE a las que había (el POST de Chatwoot las sustituye) y, si Chatwoot falla, el acuse sale igual;
5. `scripts/exportar_mal.py` saca un caso del banco de fallos por marca, sin las notas privadas ni el acuse."""
import pytest

from scripts import exportar_mal
from src.channels import chatwoot, marca_mal
from src.config import settings
from src.flows.state import ConversationState


@pytest.mark.parametrize("texto, es", [
    ("#mal", True), ("  #MAL: no me dio el enlace", True), ("#mal no era eso", True), ("#mal\nfalta el precio", True),
    ("#malecón", False), ("esto está #mal", False), ("mal", False), ("", False), (None, False),
])
def test_que_es_una_marca(texto, es):
    assert marca_mal.es_marca(texto) is es


def test_el_comentario_es_lo_que_va_detras():
    assert marca_mal.comentario("#mal: no me dio el enlace") == "no me dio el enlace"
    assert marca_mal.comentario("#MAL - faltaba el precio online") == "faltaba el precio online"
    assert marca_mal.comentario("#mal") == ""


@pytest.fixture
def canal(monkeypatch):
    vistos = {"rutas": [], "marcas": []}

    async def route(state, message):
        vistos["rutas"].append(message)
        return "respuesta"

    async def anotar(conversation_id, lang):
        vistos["marcas"].append((conversation_id, lang))

    async def load(conversation_id):
        return ConversationState(conversation_id=conversation_id, language="en")

    async def nada(*a, **k):
        return None

    async def no_visto(key):
        return False

    monkeypatch.setattr(chatwoot, "route_message", route)
    monkeypatch.setattr(chatwoot, "_anotar_fallo_marcado", anotar)
    monkeypatch.setattr(chatwoot, "finalize_chatwoot_delivery", nada)
    monkeypatch.setattr(chatwoot, "set_typing", nada)
    monkeypatch.setattr(chatwoot.state_store, "load_state", load)
    monkeypatch.setattr(chatwoot.state_store, "save_state", nada)
    monkeypatch.setattr(chatwoot.state_store, "check_and_mark_processed", no_visto)
    return vistos


def _webhook(texto, n=1):
    return {"id": n, "message_type": "incoming", "content": texto, "conversation": {"id": 700}, "sender": {"name": "t"}}


@pytest.mark.asyncio
async def test_con_el_flag_el_webhook_no_lo_contesta(canal, monkeypatch):
    monkeypatch.setattr(settings, "marcar_mal", True)
    await chatwoot.handle_message(_webhook("#mal: faltaba el enlace"))
    assert canal["rutas"] == [] and canal["marcas"] == [("700", "en")]
    await chatwoot.handle_message(_webhook("¿y el precio?", 2))
    assert canal["rutas"] == ["¿y el precio?"]


@pytest.mark.asyncio
async def test_sin_el_flag_se_contesta_como_siempre(canal, monkeypatch):
    monkeypatch.setattr(settings, "marcar_mal", False)
    await chatwoot.handle_message(_webhook("#mal"))
    assert canal["rutas"] == ["#mal"] and canal["marcas"] == []


class _Resp:
    def __init__(self, datos=None, falla=False):
        self.datos, self.falla = datos, falla

    def raise_for_status(self):
        if self.falla:
            raise RuntimeError("chatwoot caído")

    def json(self):
        return self.datos


class _Cliente:
    def __init__(self, get=None, falla=False):
        self.get_datos, self.falla, self.posts = get, falla, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        return _Resp(self.get_datos, self.falla)

    async def post(self, url, json=None, **k):
        self.posts.append((url, json))
        return _Resp({"payload": json["labels"]})


@pytest.mark.asyncio
async def test_el_repaso_de_cada_segundo_tampoco_lo_contesta(canal, monkeypatch):
    monkeypatch.setattr(settings, "marcar_mal", True)

    async def activas():
        return ["701"]

    async def desde(conversation_id):
        return 0

    mensajes = {"payload": [{"id": 9, "message_type": 0, "content": "#mal", "created_at": 1},
                            {"id": 8, "message_type": 0, "content": "hola", "created_at": 1}]}
    monkeypatch.setattr(chatwoot.state_store, "list_active_conversation_ids", activas)
    monkeypatch.setattr(chatwoot.state_store, "get_poll_started_at", desde)
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", lambda *a, **k: _Cliente(mensajes))
    await chatwoot.poll_active_conversations_once()
    assert canal["rutas"] == ["hola"] and canal["marcas"] == [("701", "en")]


@pytest.mark.asyncio
async def test_la_etiqueta_se_suma_a_las_que_habia_y_se_acusa(monkeypatch):
    cliente = _Cliente({"payload": ["vip"]})
    enviados = []

    async def enviar(conversation_id, message, quick_replies=None):
        enviados.append(message)

    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", lambda *a, **k: cliente)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", enviar)
    await chatwoot._anotar_fallo_marcado("702", "es")
    [(url, cuerpo)] = cliente.posts
    assert url.endswith("/conversations/702/labels") and cuerpo == {"labels": ["vip", "mal"]}
    assert enviados == [marca_mal.ACUSE["es"]]


@pytest.mark.asyncio
async def test_si_chatwoot_falla_el_acuse_sale_igual(monkeypatch):
    enviados = []

    async def enviar(conversation_id, message, quick_replies=None):
        enviados.append(message)

    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", lambda *a, **k: _Cliente(falla=True))
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", enviar)
    await chatwoot._anotar_fallo_marcado("703", None)
    assert enviados == [marca_mal.ACUSE["es"]]


def _m(i, tipo, texto, privado=False):
    return {"id": i, "message_type": tipo, "content": texto, "private": privado, "created_at": 1761300000 + i}


CHARLA = [
    _m(5, 1, "¿Te ayudo con algo más?"),
    _m(1, 0, "hola"),
    _m(2, 1, "¡Hola! ¿En qué te ayudo?"),
    _m(3, 0, "¿cuánto cuesta el snorkel?"),
    _m(4, 1, "El snorkel cuesta 45 USD."),
    _m(6, 0, "#mal: faltaba el precio online; escríbeme a prueba@example.com"),
    _m(7, 1, marca_mal.ACUSE["es"]),
    _m(8, 1, "nota interna del lead", privado=True),
    _m(9, 2, "Conversación asignada"),
    _m(10, 0, "gracias"),
]


def test_un_caso_por_marca_con_la_respuesta_y_lo_que_esperaba():
    [caso] = exportar_mal.casos_de_la_conversacion(55, CHARLA)
    assert caso["id"] == "mal-55-1" and caso["dialogo"] == "chatwoot-55" and caso["turno"] == 2
    assert caso["mensaje_cliente"] == "¿cuánto cuesta el snorkel?"
    assert caso["respuesta_mala"] == "El snorkel cuesta 45 USD.\n\n¿Te ayudo con algo más?"  # las dos burbujas
    assert caso["historial"] == [{"role": "user", "content": "hola"},
                                 {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"}]
    assert caso["pedia"].startswith("faltaba el precio online") and "example.com" not in caso["pedia"]
    assert caso["turnos_dialogo"] == 3 and caso["marcado_en"].startswith("2025-10-24")


def test_una_marca_sin_respuesta_del_bot_delante_no_es_caso():
    assert exportar_mal.casos_de_la_conversacion(56, [_m(1, 0, "#mal")]) == []
    assert exportar_mal.casos_de_la_conversacion(56, [_m(1, 0, "hola"), _m(2, 0, "#mal")]) == []


def test_los_casos_que_ya_estaban_no_se_pisan():
    viejo = {"id": "mal-55-1", "pedia": "corregido a mano"}
    fallos = exportar_mal.juntar([viejo], exportar_mal.casos_de_la_conversacion(55, CHARLA))
    assert fallos == [viejo]
