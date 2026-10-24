"""CAL-A (16-oct): que el RAG conteste TODO lo que pregunta el cliente (diseño de Gadea, diagnóstico de los 73 fallos).

Se fija:
1. A1 `rag_temperatura_cero` (promocionado; su flag se borró en sim-5): la redacción va a temperatura 0;
2. A2 `rag_plan_primero`: la lista de puntos del plan se añade al mensaje de la redacción; sin el flag, nada cambia;
3. A3 `rag_revisor_completitud`: si a una respuesta aprobada le falta un punto, se reintenta una vez con lo que falta;
   si el reintento no pasa el revisor, vale la primera; si no falta nada, no hay reintento;
4. si el plan o la comprobación fallan, el turno sigue como hoy.
"""

import json

import pytest

from src.agents import rag_agent, rag_plan


def _fake_openai(respuestas, llamadas):
    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Resp:
        def __init__(self, c):
            self.choices = [type("C", (), {"message": _Msg(c)})()]
            self.usage = type("U", (), {"total_tokens": 10})()

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            return _Resp(respuestas[len(llamadas) - 1])

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


@pytest.fixture
def rag(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Minicurso: 120 USD. Almuerzo con opción vegetariana. Se reserva con un anticipo.",
                 "metadata": {"source": "faqs"}, "score": 0.9}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.5)
    for flag in ("rag_plan_primero", "rag_revisor_completitud", "rag_revisor_avisos"):
        monkeypatch.setattr(rag_agent.settings, flag, False)
    llamadas = []
    veredictos = []

    def preparar(respuestas, juicios):
        veredictos.extend(juicios)
        monkeypatch.setattr(rag_agent, "AsyncOpenAI", _fake_openai(respuestas, llamadas))

        async def juez(answer, context, lang="es"):
            return veredictos.pop(0)

        monkeypatch.setattr(rag_agent, "is_grounded", juez)
        return llamadas

    return preparar


@pytest.fixture
def plan(monkeypatch):
    estado = {"puntos": ["precio del minicurso", "si hay opción vegetariana"], "faltan": [], "comprobaciones": 0}

    async def planificar(query, history, lang):
        return estado["puntos"]

    async def sin_cubrir(puntos, answer, lang):
        estado["comprobaciones"] += 1
        return estado["faltan"] if estado["comprobaciones"] == 1 else []

    monkeypatch.setattr(rag_plan, "planificar", planificar)
    monkeypatch.setattr(rag_plan, "puntos_sin_cubrir", sin_cubrir)
    return estado


PREGUNTA = "¿cuánto cuesta el minicurso y el almuerzo tiene opción vegetariana?"
CORTA = "El minicurso cuesta 120 USD."
COMPLETA = "El minicurso cuesta 120 USD y el almuerzo tiene opción vegetariana."
OK = (True, "GROUNDED")
NO = (False, "HALLUCINATED - algo. NO")


@pytest.mark.asyncio
async def test_temperatura_cero(rag, monkeypatch):
    llamadas = rag([CORTA], [OK])
    await rag_agent.rag_answer(PREGUNTA, lang="es")
    assert llamadas[-1]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_sin_flags_no_hay_plan(rag, plan):
    llamadas = rag([CORTA], [OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA
    assert "PUNTOS QUE TU RESPUESTA" not in llamadas[0]["messages"][-1]["content"]
    assert plan["comprobaciones"] == 0


@pytest.mark.asyncio
async def test_plan_primero_añade_la_lista(rag, plan, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_plan_primero", True)
    llamadas = rag([COMPLETA], [OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == COMPLETA
    ultimo = llamadas[0]["messages"][-1]["content"]
    assert "PUNTOS QUE TU RESPUESTA TIENE QUE CUBRIR" in ultimo
    assert "- precio del minicurso\n- si hay opción vegetariana" in ultimo
    assert plan["comprobaciones"] == 0


@pytest.mark.asyncio
async def test_plan_vacio_o_fallido_no_cambia_nada(rag, plan, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_plan_primero", True)
    plan["puntos"] = None
    llamadas = rag([CORTA], [OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA
    assert "PUNTOS QUE TU RESPUESTA" not in llamadas[0]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_completitud_reintenta_con_lo_que_falta(rag, plan, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_completitud", True)
    plan["faltan"] = ["si hay opción vegetariana"]
    llamadas = rag([CORTA, COMPLETA], [OK, OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == COMPLETA
    assert len(llamadas) == 2
    segunda = llamadas[1]["messages"]
    assert segunda[-2] == {"role": "assistant", "content": CORTA}
    assert "- si hay opción vegetariana\n" in segunda[-1]["content"]
    # sin `rag_plan_primero` la redacción no lleva la lista, solo la comprobación la usa
    assert "PUNTOS QUE TU RESPUESTA" not in llamadas[0]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_si_el_reintento_no_pasa_vale_la_primera(rag, plan, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_completitud", True)
    plan["faltan"] = ["si hay opción vegetariana"]
    rag([CORTA, "El almuerzo es gratis para siempre."], [OK, NO])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA


@pytest.mark.asyncio
async def test_completa_no_reintenta(rag, plan, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_completitud", True)
    llamadas = rag([COMPLETA], [OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == COMPLETA
    assert len(llamadas) == 1 and plan["comprobaciones"] == 1


# --- las llamadas de rag_plan, con un cliente falso ---

def _cliente_falso(monkeypatch, contenido, llamadas):
    class _C:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            if isinstance(contenido, Exception):
                raise contenido
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": contenido})()})()]})()

    monkeypatch.setattr(rag_plan, "_cliente", lambda: type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})())


@pytest.mark.asyncio
async def test_planificar_lee_el_json_y_corta_a_seis(monkeypatch):
    llamadas = []
    _cliente_falso(monkeypatch, json.dumps({"puntos": [f"p{i}" for i in range(9)] + [" "]}), llamadas)
    historia = [{"role": "assistant", "content": "¿Qué plan te interesa?"}]
    assert await rag_plan.planificar("y el precio?", historia, "es") == ["p0", "p1", "p2", "p3", "p4", "p5"]
    assert llamadas[0]["temperature"] == 0
    assert "Bot: ¿Qué plan te interesa?" in llamadas[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_planificar_falla_y_devuelve_none(monkeypatch):
    _cliente_falso(monkeypatch, RuntimeError("429"), [])
    assert await rag_plan.planificar("hola", None, "es") is None


@pytest.mark.asyncio
async def test_puntos_sin_cubrir(monkeypatch):
    _cliente_falso(monkeypatch, json.dumps({"faltan": ["b"]}), [])
    assert await rag_plan.puntos_sin_cubrir(["a", "b"], "respuesta", "es") == ["b"]
    assert await rag_plan.puntos_sin_cubrir([], "respuesta", "es") == []
    _cliente_falso(monkeypatch, "no es json", [])
    assert await rag_plan.puntos_sin_cubrir(["a"], "respuesta", "en") == []


# --- A4 `rag_revisor_avisos`: el aviso que el cliente necesita y no pregunta ---

@pytest.fixture
def avisos(monkeypatch):
    estado = {"avisos": [], "llamadas": []}

    async def que_faltan(query, informacion, answer, lang):
        estado["llamadas"].append(informacion)
        return estado["avisos"] if len(estado["llamadas"]) == 1 else []

    monkeypatch.setattr(rag_plan, "avisos_que_faltan", que_faltan)
    return estado


@pytest.mark.asyncio
async def test_avisos_reintenta_con_el_aviso(rag, avisos, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_avisos", True)
    avisos["avisos"] = ["el minicurso no certifica"]
    llamadas = rag([CORTA, COMPLETA], [OK, OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == COMPLETA
    segunda = llamadas[1]["messages"]
    assert segunda[-2] == {"role": "assistant", "content": CORTA}
    assert "- el minicurso no certifica\n" in segunda[-1]["content"]
    # lee lo mismo que el revisor de siempre: el contexto de la búsqueda
    assert "Minicurso: 120 USD" in avisos["llamadas"][0]


@pytest.mark.asyncio
async def test_avisos_sin_falta_no_reintenta_y_sin_flag_no_llama(rag, avisos, monkeypatch):
    llamadas = rag([CORTA], [OK])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA
    assert avisos["llamadas"] == []
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_avisos", True)
    llamadas = rag([CORTA, CORTA], [OK])  # la lista de llamadas es la misma: la segunda respuesta es la de esta vuelta
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA
    assert len(llamadas) == 2 and len(avisos["llamadas"]) == 1  # 1 de la ronda anterior + 1 de esta


@pytest.mark.asyncio
async def test_avisos_reintento_rechazado_vale_la_primera(rag, avisos, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_revisor_avisos", True)
    avisos["avisos"] = ["el minicurso no certifica"]
    rag([CORTA, "El minicurso certifica en 1 hora."], [OK, NO])
    assert await rag_agent.rag_answer(PREGUNTA, lang="es") == CORTA


@pytest.mark.asyncio
async def test_avisos_que_faltan_corta_a_dos_y_falla_en_silencio(monkeypatch):
    _cliente_falso(monkeypatch, json.dumps({"faltan": ["a", "b", "c"]}), [])
    assert await rag_plan.avisos_que_faltan("q", "info", "resp", "es") == ["a", "b"]
    _cliente_falso(monkeypatch, RuntimeError("429"), [])
    assert await rag_plan.avisos_que_faltan("q", "info", "resp", "en") == []
