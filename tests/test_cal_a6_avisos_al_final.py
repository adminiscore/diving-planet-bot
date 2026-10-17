"""CAL-A6 (17-oct, flag `avisos_al_final`): el aviso que falta, como UNA frase añadida tras la respuesta.

Lo que §10 de docs/robustness/cal/cal-a5-avisos-condicionados.md dejó por probar. A5 metía el aviso en la redacción y
desplazaba lo que la respuesta tenía que decir (el golden empeoró dos rondas); y lo elegía el código con campos del
estado que en los casos que quedan no están (cal-49 habla del curso referido sin "elegirlo"). Aquí:

1. la lista cerrada de avisos (la misma de A5) va al revisor con sus condiciones EN PALABRAS, y sin los de `una_vez`
   ya dados;
2. el revisor (un modelo que lee la conversación) devuelve como mucho UN aviso de la lista con su frase; si nombra uno
   que no está, uno ya dado, o la llamada falla, no se añade nada;
3. la frase se AÑADE en su propio párrafo, antes de la pregunta final si la hay, sin tocar el resto de la respuesta;
4. en el RAG va a la vez que el juez de siempre, solo cuenta si la respuesta pasa, la frase pasa las mismas guardas
   deterministas (un teléfono o un importe que no está en el contexto la tiran) y el aviso queda apuntado como dado;
   sin el flag, el turno es el de siempre (ni una llamada más).
"""

import json

import pytest

from src.config import settings
from src.flows import avisos as av

# ---------------------------------------------------------------- 1. la lista para el revisor


def test_la_lista_lleva_cada_aviso_con_su_condicion_en_palabras():
    lista = av.lista_para_el_revisor([])
    linea = next(ln for ln in lista.splitlines() if ln.startswith("- carta-de-referido"))
    # Su `cuando_texto`, escrito a mano: el cliente describe el curso referido sin nombrarlo (cal-49).
    assert "aplica si: se habla de terminar aquí un Open Water empezado en otro centro PADI" in linea
    assert "carta/formato de referido PADI" in linea
    minicurso = next(ln for ln in lista.splitlines() if ln.startswith("- minicurso-no-certifica"))
    # Varias condiciones: tienen que cumplirse TODAS (con "; y " el revisor tomaba una sola: "quiero bucear
    # certificado" bastaba para el aviso de la profundidad).
    assert ("TODAS estas: (1) el cliente quiere hacer o pregunta por Minicurso de buceo; (2) se habla de certificarse"
            in minicurso)
    almuerzo = next(ln for ln in lista.splitlines() if ln.startswith("- almuerzo-desde-islas"))
    assert "sale desde las islas" in almuerzo and "la comida o el almuerzo" in almuerzo
    # Cada aviso en su línea, menos la información general (`"al_final": false`): el cierre de las 4:30, el formulario
    # médico... En la ronda core simulada eran 19 de los 33 avisos añadidos, casi todos relleno.
    assert len(lista.splitlines()) == len([a for a in av.avisos() if a.get("al_final", True)])
    for informativo in ("cierre-430-siguiente-dia", "operamos-todos-los-dias", "formulario-medico-tras-reservar",
                        "reserva-confirmada-al-pagar", "descuento-online-automatico"):
        assert informativo not in lista


def test_los_avisos_de_una_vez_ya_dados_no_vuelven_a_la_lista():
    lista = av.lista_para_el_revisor(["fotos-no-incluidas"])
    assert "fotos-no-incluidas" not in lista
    assert "carta-de-referido" in lista


def test_un_aviso_sin_condiciones_se_deja_al_criterio_del_revisor():
    aviso = {"id": "x", "aviso_es": "y", "cuando": {}}
    assert av.condicion_en_palabras(aviso) == "cuando venga al caso por lo que cuenta o pregunta el cliente"


# ---------------------------------------------------------------- 2. el revisor


def _cliente_que_contesta(monkeypatch, contenido=None, falla=False):
    from src.agents import rag_plan

    llamadas: list[dict] = []

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            if falla:
                raise RuntimeError("sin red")
            msg = type("M", (), {"content": json.dumps(contenido)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(rag_plan, "AsyncOpenAI", _OpenAI)
    return llamadas


_HISTORIAL = [{"role": "user", "content": "He's already doing the e-learning"},
              {"role": "assistant", "content": "He can finish it here with the Open Water referral course."}]


@pytest.mark.asyncio
async def test_el_revisor_devuelve_el_aviso_y_su_frase(monkeypatch):
    from src.agents import rag_plan

    llamadas = _cliente_que_contesta(monkeypatch, {
        "aviso": "carta-de-referido", "cita_del_cliente": "He's already doing the E-learning",
        "cita_del_ultimo_mensaje": "the form", "frase": "Remember to bring the PADI referral form signed by his instructor."})
    salida = await rag_plan.aviso_al_final(_HISTORIAL, "What info do I need for the form?", "Here it is.", "en")
    assert salida == ("carta-de-referido", "Remember to bring the PADI referral form signed by his instructor.")
    contenido = llamadas[0]["messages"][1]["content"]
    assert contenido.startswith("NOTICES:"), "la lista va delante: es fija y OpenAI cachea el prefijo"
    assert "Open Water referral course" in contenido, "el revisor lee la conversación"
    assert contenido.endswith("LANGUAGE OF THE SENTENCE: English"), "el idioma de la frase va explícito"


@pytest.mark.asyncio
@pytest.mark.parametrize("citas", [
    {"cita_del_cliente": "", "cita_del_ultimo_mensaje": "the form"},
    # una cita que dijo el BOT, no el cliente
    {"cita_del_cliente": "the Open Water referral course", "cita_del_ultimo_mensaje": "the form"},
    # la condición sale de lo que dijo, pero el aviso no tiene que ver con su último mensaje
    {"cita_del_cliente": "already doing the e-learning", "cita_del_ultimo_mensaje": "already doing the e-learning"},
])
async def test_sin_citas_reales_del_cliente_no_se_anade_nada(monkeypatch, citas):
    """Lo que hizo falta en la ronda (v2 añadía avisos en 24 de 93 turnos, alguno suponiendo la nacionalidad por el
    idioma): la condición tiene que salir de palabras REALES del cliente y el aviso tiene que ver con su último
    mensaje. Lo comprueba el código, no el modelo."""
    from src.agents import rag_plan

    _cliente_que_contesta(monkeypatch, {"aviso": "carta-de-referido", "frase": "Bring the signed referral form.",
                                        **citas})
    assert await rag_plan.aviso_al_final(_HISTORIAL, "What info do I need for the form?", "Here it is.", "en") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("contenido", [
    {"aviso": None, "frase": None},
    {"aviso": "aviso-inventado", "frase": "Algo."},
    {"aviso": "carta-de-referido", "frase": ""},
])
async def test_sin_aviso_valido_no_se_anade_nada(monkeypatch, contenido):
    from src.agents import rag_plan

    _cliente_que_contesta(monkeypatch, contenido)
    assert await rag_plan.aviso_al_final(_HISTORIAL, "¿y el formulario?", "Aquí lo tienes.", "es") is None


@pytest.mark.asyncio
async def test_un_aviso_de_una_vez_ya_dado_no_se_repite(monkeypatch):
    from src.agents import rag_plan

    _cliente_que_contesta(monkeypatch, {"aviso": "fotos-no-incluidas", "cita_del_cliente": "las fotos",
                                        "cita_del_ultimo_mensaje": "las fotos", "frase": "Las fotos no están incluidas."})
    assert await rag_plan.aviso_al_final([], "¿y las fotos?", "Claro.", "es", dados=["fotos-no-incluidas"]) is None


@pytest.mark.asyncio
async def test_si_la_llamada_falla_el_turno_sigue(monkeypatch):
    from src.agents import rag_plan

    _cliente_que_contesta(monkeypatch, falla=True)
    assert await rag_plan.aviso_al_final(_HISTORIAL, "¿y el formulario?", "Aquí lo tienes.", "es") is None


# ---------------------------------------------------------------- 3. dónde va la frase


def test_la_frase_va_antes_de_la_pregunta_final():
    from src.agents.rag_plan import insertar_frase

    respuesta = "El curso referido son 2 días.\n\n¿Quieres que te pase con un asesor?"
    assert insertar_frase(respuesta, "Trae la carta de referido firmada.") == (
        "El curso referido son 2 días.\n\nTrae la carta de referido firmada.\n\n¿Quieres que te pase con un asesor?")


def test_sin_pregunta_final_la_frase_va_al_final_y_lo_demas_no_cambia():
    from src.agents.rag_plan import insertar_frase

    respuesta = "Las fotos las hace el instructor si quiere.\n\nPuedes reservar en la web."
    assert insertar_frase(respuesta, "En el minicurso no se hacen.") == respuesta + "\n\nEn el minicurso no se hacen."
    # Un solo párrafo que pregunta: la frase va detrás (no se parte el párrafo).
    assert insertar_frase("¿Te ayudo con algo más?", "Dato.") == "¿Te ayudo con algo más?\n\nDato."


# ---------------------------------------------------------------- 4. el cableado en el RAG


@pytest.fixture
def rag(monkeypatch):
    """El RAG con una búsqueda, un LLM y un revisor de mentira; devuelve las llamadas al revisor."""
    from src.agents import rag_agent, rag_plan

    class _Completions:
        async def create(self, **kwargs):
            msg = type("M", (), {"content": "El curso referido son 2 días en las islas."})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                                  "usage": type("U", (), {"total_tokens": 10, "prompt_tokens_details": None})()})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    async def fake_search(query, lang="es", **kw):
        return [{"content": "El curso referido exige la carta de referido PADI firmada por el instructor.",
                 "metadata": {"source": "services", "key": "ficha:referral", "topics": ["certification"]},
                 "score": 0.9}]

    async def fake_expand(docs, lang):
        return docs

    async def fake_condense(query, history=None, lang="es", hechos=None):
        return query

    async def fake_verify(answer, context, lang="es"):
        return True, ""

    revisiones: list[str] = []
    frase = {"texto": "Recuerda traer la carta de referido firmada por tu instructor."}

    async def fake_aviso(history, query, answer, lang, dados=None):
        revisiones.append(answer)
        return ("carta-de-referido", frase["texto"])

    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", fake_expand)
    monkeypatch.setattr(rag_agent, "condense_query", fake_condense)
    monkeypatch.setattr(rag_agent, "_verify_grounding", fake_verify)
    monkeypatch.setattr(rag_plan, "aviso_al_final", fake_aviso)
    for flag in ("rag_v2", "rag_prompt_cache", "rag_plan_primero", "rag_revisor_completitud", "rag_revisor_avisos",
                 "avisos_condicionados"):
        monkeypatch.setattr(settings, flag, False)
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "")
    return rag_agent, revisiones, frase


@pytest.mark.asyncio
async def test_con_el_flag_la_frase_se_anade_y_el_aviso_queda_dado(rag, monkeypatch):
    rag_agent, revisiones, _ = rag
    monkeypatch.setattr(settings, "avisos_al_final", True)
    hechos = {"actividades": set(), "dados": []}
    respuesta = await rag_agent.rag_answer("¿qué necesito para el formulario?", lang="es", avisos_hechos=hechos)
    assert respuesta == ("El curso referido son 2 días en las islas.\n\n"
                         "Recuerda traer la carta de referido firmada por tu instructor.")
    assert revisiones == ["El curso referido son 2 días en las islas."], "revisa la respuesta, no la reescribe"
    assert hechos["dados"] == ["carta-de-referido"]


@pytest.mark.asyncio
async def test_sin_el_flag_no_hay_revisor(rag, monkeypatch):
    rag_agent, revisiones, _ = rag
    monkeypatch.setattr(settings, "avisos_al_final", False)
    respuesta = await rag_agent.rag_answer("¿qué necesito para el formulario?", lang="es")
    assert respuesta == "El curso referido son 2 días en las islas."
    assert revisiones == []


@pytest.mark.asyncio
async def test_una_frase_con_un_telefono_no_se_anade(rag, monkeypatch):
    rag_agent, _, frase = rag
    monkeypatch.setattr(settings, "avisos_al_final", True)
    frase["texto"] = "Para la carta, llama al +57 300 123 4567."
    hechos = {"actividades": set(), "dados": []}
    respuesta = await rag_agent.rag_answer("¿qué necesito para el formulario?", lang="es", avisos_hechos=hechos)
    assert respuesta == "El curso referido son 2 días en las islas."
    assert hechos["dados"] == [], "un aviso que no se dijo no queda apuntado"
