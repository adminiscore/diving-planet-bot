"""CAL-A5 (16-oct, CAL-A reabierta por Gadea): los avisos que el cliente necesita y no pregunta, como datos con
condiciones que elige el CÓDIGO (`src/flows/avisos.py`), no un modelo.

Se fija:
1. los hechos salen de campos ESTRUCTURADOS del estado (actividad, origen, nacionalidad), nunca del texto, y no hay
   ninguna lista de nombres ni de palabras;
2. el tema sale de los documentos que trajo la BÚSQUEDA (su clave, y los `topics` solo de los primeros), no del
   mensaje del cliente;
3. un aviso solo aplica si se cumplen TODAS sus condiciones y los de `una_vez` no se repiten; el que NO depende de
   nada del cliente (las fotos, los horarios) necesita además que la búsqueda haya traído SU fuente entre las
   primeras, o salía en cualquier turno. Exigírselo a TODOS se probó el 17-oct y el banco lo tumbó (41/48 frente a
   36/48): la fuente no siempre entra entre las primeras aunque la pregunta vaya de eso;
4. con el flag, los avisos elegidos van al mensaje de la redacción como puntos obligatorios y, si la respuesta no los
   da, se reintenta una vez; sin el flag, el turno es el de siempre (ni un token más);
5. los avisos del fichero son válidos: id único, fuente que existe en la base y condiciones conocidas.
"""

import json

import pytest

from src.config import settings
from src.flows import avisos as av
from src.flows.state import ConversationState

# ---------------------------------------------------------------- 1. hechos del estado


def _estado(**campos) -> ConversationState:
    return ConversationState(conversation_id="t", language="es", **campos)


def test_la_actividad_sale_del_estado_no_del_texto():
    """La actividad elegida en el árbol, la que detectó el extractor, la del carrito y las del reparto del grupo."""
    assert "minicourse" in av.hechos_del_estado(_estado(detected_activity="minicourse"))["actividades"]
    assert "minicourse" in av.hechos_del_estado(_estado(selected_service="minicourse"))["actividades"]
    assert av.hechos_del_estado(
        _estado(detected_group_allocation={"certified_diving": 2, "snorkel": 1, "undecided": 1}))["actividades"] \
        >= {"certified_diving", "snorkel"}
    # "undecided" no es una actividad: nadie la hace todavía.
    assert "undecided" not in av.hechos_del_estado(
        _estado(detected_group_allocation={"undecided": 2}))["actividades"]
    # El texto del cliente no entra: un mensaje que habla del minicurso sin que el extractor lo haya puesto, no cuenta.
    hablado = _estado(history=[{"role": "user", "content": "me interesa el minicurso para certificarme"}])
    assert av.hechos_del_estado(hablado)["actividades"] == set()


def test_el_refresher_y_el_buceo_certificado_constan_por_sus_campos():
    assert "refresher" in av.hechos_del_estado(_estado(last_dive_over_2_years=True))["actividades"]
    assert "refresher" in av.hechos_del_estado(_estado(refresher_interested=True))["actividades"]
    assert "certified_diving" in av.hechos_del_estado(_estado(is_certified=True))["actividades"]


def test_la_nacionalidad_mixta_manda_sobre_la_de_quien_escribe():
    """Grupo mezclado: la nacionalidad de quien escribe se guarda como extranjera (todo en USD, Gadea 14-sep), así que
    el aviso que toca es el del grupo mixto."""
    assert av.hechos_del_estado(_estado(is_colombian=True))["nacionalidad"] == "colombiano"
    assert av.hechos_del_estado(_estado(is_colombian=False))["nacionalidad"] == "extranjero"
    assert av.hechos_del_estado(_estado(is_colombian=False, mixed_nationality_notice=True))["nacionalidad"] == "mixto"
    assert av.hechos_del_estado(_estado())["nacionalidad"] is None


def test_no_hay_listas_de_nombres_de_lugares_ni_de_palabras():
    """Norma del proyecto (Gadea): soluciones genéricas, nunca patrones que acierten unas conversaciones y fallen
    otras. La primera versión tenía una tabla con cuatro nombres de hoteles de Barú sacados del golden: fuera. Un
    aviso que depende de dónde está el cliente espera a que el dato esté en el estado; el de "solo operamos en
    Rosario" depende de que la búsqueda traiga su propia fuente."""
    datos = json.loads(av.AVISOS_PATH.read_text(encoding="utf-8-sig"))
    assert "zonas" not in datos, "una tabla de nombres de lugares es un parche: el lugar lo da el estado"
    hechos = av.hechos_del_estado(_estado(island="Isla Barú"))
    assert "zona" not in hechos
    por_la_fuente = [a["id"] for a in av.seleccionar(hechos, set(), {"dive_area"})]
    assert "solo-operamos-en-rosario" in por_la_fuente
    assert "solo-operamos-en-rosario" not in [a["id"] for a in av.seleccionar(hechos, set(), {"food_policy"})]


# ---------------------------------------------------------------- 2. el tema, de los documentos recuperados


def test_el_tema_sale_de_los_documentos_que_trajo_la_busqueda():
    docs = [{"content": "...", "metadata": {"source": "policies", "key": "politica:minicourse_scope",
                                            "topics": ["certification"]}}]
    assert "certificacion" in av.temas_de_los_docs(docs)
    assert av.temas_de_los_docs([{"content": "x", "metadata": {"source": "faqs", "topics": ["seasickness"]}}]) == set()
    assert av.temas_de_los_docs([]) == set()
    assert av.temas_de_los_docs(None) == set()


def test_la_clave_del_documento_va_sin_prefijo():
    """Las claves de la base vienen prefijadas (`politica:food_policy`, `faq:20`, `ficha:refresher:minicourse`): sin
    quitarlo no casaba ninguna política y el tema salía solo de los `topics` (16-oct)."""
    assert av._clave({"metadata": {"key": "politica:food_policy"}}) == "food_policy"
    assert av._clave({"metadata": {"key": "ficha:refresher:minicourse"}}) == "minicourse"
    assert av._clave({"metadata": {"subtype": "pricing"}}) == "pricing"
    assert av._clave({"metadata": {}}) is None
    assert "comida" in av.temas_de_los_docs([{"metadata": {"key": "politica:food_policy"}}])


def test_los_topics_solo_cuentan_en_los_primeros_documentos():
    """Una ficha de servicio trae diez `topics` y la búsqueda devuelve 8-12 documentos: en el montón, los `topics` de
    todos cubrían 10 de los 13 temas (medido el 16-oct). Solo cuentan los de los primeros."""
    docs = [{"metadata": {"key": "faq:1", "topics": ["payment"]}},
            {"metadata": {"key": "faq:2", "topics": ["depth"]}},
            {"metadata": {"key": "faq:3", "topics": ["photos_media"]}},
            {"metadata": {"key": "faq:4", "topics": ["food_policy"]}}]
    temas = av.temas_de_los_docs(docs)
    assert "pago" in temas and "profundidad" in temas
    assert "fotos" not in temas, "el tercer documento ya no decide de qué va la pregunta"


def test_los_topics_de_una_ficha_de_servicio_no_dicen_de_que_va_la_pregunta():
    """Una ficha trae diez `topics` (su itinerario habla de horarios, profundidad, equipo, fotos): en una pregunta de
    precio hacía saltar "la profundidad depende del nivel" (medido el 16-oct sobre los casos de CAL-C)."""
    ficha = {"metadata": {"source": "services", "key": "ficha:2_dives_1_day", "subtype": "pricing",
                          "topics": ["pricing", "depth", "photos_media", "schedule"]}}
    temas = av.temas_de_los_docs([ficha])
    assert "profundidad" not in temas and "fotos" not in temas
    assert "precio" in temas, "el subtipo de la ficha sí identifica el documento"
    # La misma señal en una pregunta frecuente sí cuenta.
    assert "profundidad" in av.temas_de_los_docs([{"metadata": {"source": "faqs", "key": "faq:7",
                                                                "topics": ["depth"]}}])


def test_la_fuente_recuperada_son_las_claves_de_los_primeros():
    docs = [{"metadata": {"key": f"politica:p{i}"}} for i in range(8)]
    assert av.fuentes_recuperadas(docs) == {"p0", "p1", "p2", "p3"}
    assert av.fuentes_recuperadas([]) == set()


def test_el_aviso_que_no_depende_del_cliente_necesita_su_propia_fuente():
    """`fotos-no-incluidas` solo depende de la pregunta. Con el tema suelto salía en cualquier turno (en una pregunta
    por el enlace de pago, porque una política de certificación trae el topic `photos_media`)."""
    hechos = av.hechos_del_estado(_estado())
    assert "fotos-no-incluidas" not in [a["id"] for a in av.seleccionar(hechos, {"fotos"}, {"certification_required"})]
    assert "fotos-no-incluidas" in [a["id"] for a in av.seleccionar(hechos, {"fotos"}, {"photos_videos_policy"})]


# ---------------------------------------------------------------- 3. la selección


def test_el_aviso_necesita_todas_sus_condiciones():
    """minicurso-no-certifica: la actividad es el minicurso Y la pregunta va de certificarse."""
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    fuente = {"minicourse_scope"}
    elegidos = [a["id"] for a in av.seleccionar(hechos, {"certificacion"}, fuente)]
    assert "minicurso-no-certifica" in elegidos
    # Sin el tema (pregunta por el precio), ese aviso no toca.
    assert "minicurso-no-certifica" not in [a["id"] for a in av.seleccionar(hechos, {"precio"}, fuente)]
    # Sin la actividad (no se sabe qué quiere), tampoco.
    assert "minicurso-no-certifica" not in [
        a["id"] for a in av.seleccionar(av.hechos_del_estado(_estado()), {"certificacion"}, fuente)]
    # Este depende del cliente (la actividad), así que NO se le exige su fuente entre las primeras: medido el 17-oct,
    # exigirlo perdía el caso (su política salía en la posición 6 de 8).
    assert "minicurso-no-certifica" in [a["id"] for a in av.seleccionar(hechos, {"certificacion"}, {"food_policy"})]


def test_los_avisos_de_una_vez_no_se_repiten():
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    fuente = {"minicourse_scope"}
    assert "minicurso-no-certifica" in [a["id"] for a in av.seleccionar(hechos, {"certificacion"}, fuente)]
    hechos["dados"] = ["minicurso-no-certifica"]
    assert "minicurso-no-certifica" not in [a["id"] for a in av.seleccionar(hechos, {"certificacion"}, fuente)]


def test_el_extranjero_sin_cedula_paga_en_usd_y_el_colombiano_no_tiene_descuento():
    fuente = {"colombian_pricing"}
    extranjero = av.hechos_del_estado(_estado(is_colombian=False))
    assert "extranjero-paga-en-usd" in [a["id"] for a in av.seleccionar(extranjero, {"pago"}, fuente)]
    colombiano = av.hechos_del_estado(_estado(is_colombian=True))
    assert "extranjero-paga-en-usd" not in [a["id"] for a in av.seleccionar(colombiano, {"pago"}, fuente)]
    assert "sin-precio-especial-colombianos" in [a["id"] for a in av.seleccionar(colombiano, {"descuentos"}, fuente)]


def test_el_almuerzo_solo_se_avisa_a_quien_sale_de_las_islas():
    fuente = {"food_policy"}
    islas = av.hechos_del_estado(_estado(location="island"))
    assert "almuerzo-desde-islas" in [a["id"] for a in av.seleccionar(islas, {"comida"}, fuente)]
    cartagena = av.hechos_del_estado(_estado(location="cartagena"))
    assert "almuerzo-desde-islas" not in [a["id"] for a in av.seleccionar(cartagena, {"comida"}, fuente)]


def test_nunca_mas_de_un_aviso_en_un_turno():
    """Desde la ronda A/B del 17-oct: con dos, la respuesta desplazaba lo que ya tenía que decir (un diálogo se quedó
    sin el enlace de reserva). Un aviso de más nunca vale lo que cuesta perder la respuesta."""
    hechos = av.hechos_del_estado(_estado(location="island", is_colombian=False, detected_activity="minicourse"))
    todas = set(av._temas())
    fuentes = {av._fuente(a) for a in av.avisos()}
    assert len(av.seleccionar(hechos, todas, fuentes)) <= av.MAX_AVISOS == 1


def test_el_hueco_se_lo_queda_un_aviso_de_la_pregunta_no_el_primero_del_fichero():
    hechos = av.hechos_del_estado(_estado(location="island", is_colombian=False, detected_activity="minicourse"))
    elegidos = [a["id"] for a in av.seleccionar(hechos, set(av._temas()), {"food_policy", "island_pickup"})]
    assert len(elegidos) == 1
    assert elegidos[0] in ("almuerzo-desde-islas", "recogida-en-hotel-islas"), elegidos


def test_sin_hechos_ni_temas_no_hay_aviso_que_dependa_de_ellos():
    elegidos = [a["id"] for a in av.seleccionar(av.hechos_del_estado(_estado()), set())]
    assert "minicurso-no-certifica" not in elegidos and "almuerzo-desde-islas" not in elegidos


# ---------------------------------------------------------------- 4. el cableado en el RAG


@pytest.fixture
def rag(monkeypatch):
    """El RAG con una búsqueda y un LLM de mentira: devuelve las llamadas que se hicieron."""
    from src.agents import rag_agent, rag_plan

    llamadas: list[dict] = []
    # Sin cifras: un precio que no esté en el contexto lo tira la guarda de siempre (no es lo que se mide aquí).
    respuestas = ["El minicurso es una experiencia guiada con instructor.",
                  "El minicurso es una experiencia guiada con instructor y no otorga certificación PADI."]

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            texto = respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]
            msg = type("M", (), {"content": texto})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                                  "usage": type("U", (), {"total_tokens": 10,
                                                          "prompt_tokens_details": None})()})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    async def fake_search(query, lang="es", **kw):
        return [{"content": "El minicurso es una experiencia guiada y no otorga certificación.",
                 "metadata": {"source": "policies", "key": "minicourse_scope", "topics": ["certification"]},
                 "score": 0.9}]

    async def fake_expand(docs, lang):
        return docs

    async def fake_condense(query, history=None, lang="es", hechos=None):
        return query

    async def fake_verify(answer, context, lang="es"):
        return True, ""

    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(rag_plan, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", fake_expand)
    monkeypatch.setattr(rag_agent, "condense_query", fake_condense)
    monkeypatch.setattr(rag_agent, "_verify_grounding", fake_verify)
    monkeypatch.setattr(settings, "rag_plan_primero", False)
    monkeypatch.setattr(settings, "rag_revisor_completitud", False)
    monkeypatch.setattr(settings, "rag_revisor_avisos", False)
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "")
    return rag_agent, llamadas


def _mensaje_del_usuario(llamada: dict) -> str:
    return next(m["content"] for m in reversed(llamada["messages"]) if m["role"] == "user")


@pytest.mark.asyncio
async def test_con_el_flag_el_aviso_va_en_el_mensaje_de_la_redaccion(rag, monkeypatch):
    rag_agent, llamadas = rag
    monkeypatch.setattr(settings, "avisos_condicionados", True)
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    await rag_agent.rag_answer("¿el minicurso me certifica?", lang="es", avisos_hechos=hechos)
    primera = _mensaje_del_usuario(llamadas[0])
    assert "AVISO QUE EL CLIENTE NECESITA" in primera
    assert "PRIMERO contesta" in primera, "lo que pidió el cliente va antes que el aviso (ronda A/B del 17-oct)"
    assert "NO certifica" in primera
    # El aviso queda apuntado: no se repite en el turno siguiente.
    assert hechos["dados"] == ["minicurso-no-certifica"]


@pytest.mark.asyncio
async def test_sin_el_flag_nada_cambia(rag, monkeypatch):
    rag_agent, llamadas = rag
    monkeypatch.setattr(settings, "avisos_condicionados", False)
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    await rag_agent.rag_answer("¿el minicurso me certifica?", lang="es", avisos_hechos=hechos)
    assert len(llamadas) == 1
    assert "AVISOS" not in _mensaje_del_usuario(llamadas[0])
    assert hechos["dados"] == []


@pytest.mark.asyncio
async def test_si_la_respuesta_no_da_el_aviso_se_reintenta_una_vez(rag, monkeypatch):
    """El revisor de completitud (A3) comprueba que el aviso ESTÉ; los avisos ya los eligió el código."""
    from src.agents import rag_plan

    rag_agent, llamadas = rag
    monkeypatch.setattr(settings, "avisos_condicionados", True)
    faltas = [["El minicurso no certifica"], []]

    async def fake_sin_cubrir(puntos, answer, lang):
        return faltas.pop(0) if faltas else []

    monkeypatch.setattr(rag_plan, "puntos_sin_cubrir", fake_sin_cubrir)
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    respuesta = await rag_agent.rag_answer("¿el minicurso me certifica?", lang="es", avisos_hechos=hechos)
    assert len(llamadas) == 2, "tiene que reintentarse una vez con el aviso que falta"
    assert "no otorga certificación" in respuesta
    assert "falta avisar al cliente" in _mensaje_del_usuario(llamadas[1])


@pytest.mark.asyncio
async def test_si_no_toca_ningun_aviso_no_hay_reintento(rag, monkeypatch):
    rag_agent, llamadas = rag
    monkeypatch.setattr(settings, "avisos_condicionados", True)
    hechos = av.hechos_del_estado(_estado())  # no se sabe nada del cliente
    await rag_agent.rag_answer("¿cuánto cuesta?", lang="es", avisos_hechos=hechos)
    assert len(llamadas) == 1
    assert "AVISOS" not in _mensaje_del_usuario(llamadas[0])


# ---------------------------------------------------------------- 5. el fichero de avisos es válido


def _de_la_base(fichero: str, clave: str) -> list[str]:
    datos = json.loads((av.AVISOS_PATH.parent / fichero).read_text(encoding="utf-8-sig"))
    return list(datos.get(clave, datos).keys())


def test_el_fichero_de_avisos_es_valido():
    """Lo edita el negocio: un id repetido, una fuente que no existe o una condición inventada tienen que verse aquí."""
    from src.domain import activities as dom

    datos = json.loads(av.AVISOS_PATH.read_text(encoding="utf-8-sig"))
    politicas = set(_de_la_base("policies.json", "policies"))
    servicios = set(_de_la_base("services.json", "services"))
    descuentos = set(_de_la_base("discounts.json", "discounts"))  # ord-6c: el descuento de grupo vive ahí
    ids = [a["id"] for a in datos["avisos"]]
    assert len(ids) == len(set(ids)), "ids repetidos"
    campos_validos = {"actividad", "actividad_tambien", "origen", "nacionalidad", "tema",
                      "inactivo_mas_de_2_anos", "estancia_menor_que_plan"}
    actividades = set(dom.activity_ids())
    for aviso in datos["avisos"]:
        assert aviso["aviso_es"].strip(), aviso["id"]
        fuente = aviso["fuente"]
        if fuente.startswith("ficha:"):
            assert fuente.split(":", 1)[1] in servicios, f"{aviso['id']}: ficha {fuente} no existe"
        elif fuente.startswith("descuento:"):
            assert fuente.split(":", 1)[1] in descuentos, f"{aviso['id']}: descuento {fuente} no existe"
        else:
            assert fuente in politicas, f"{aviso['id']}: política {fuente} no existe"
        tambien = aviso.get("tambien") or {}
        assert set(tambien) <= {"tema", "fuentes"}, f"{aviso['id']}: 'tambien' solo admite tema y fuentes"
        assert set(tambien.get("tema") or []) <= set(av._temas()), f"{aviso['id']}: tema de 'tambien' sin definir"
        assert set(tambien.get("fuentes") or []) <= politicas, f"{aviso['id']}: fuente de 'tambien' no existe"
        for campo, valor in (aviso.get("cuando") or {}).items():
            assert campo in campos_validos, f"{aviso['id']}: condición {campo} desconocida"
            if campo in ("actividad", "actividad_tambien"):
                assert set(valor) <= actividades, f"{aviso['id']}: actividad fuera del registro"
            if campo == "tema":
                assert set(valor) <= set(av._temas()), f"{aviso['id']}: tema sin definir"
            if campo == "origen":
                assert valor in ("cartagena", "island"), f"{aviso['id']}: origen desconocido"
            if campo == "nacionalidad":
                assert valor in ("colombiano", "extranjero", "mixto"), f"{aviso['id']}: nacionalidad desconocida"


def test_los_temas_son_de_la_base_de_conocimiento():
    """Los temas se comparan con `metadata.topics` (de `scripts.load_embeddings.detect_topics`) y con las claves de
    política o ficha: si alguno no sale de ahí, nunca se cumpliría."""
    from scripts.load_embeddings import TOPIC_PATTERNS

    conocidos = {n for n, _ in TOPIC_PATTERNS}
    conocidos |= set(_de_la_base("policies.json", "policies"))
    conocidos |= set(_de_la_base("discounts.json", "discounts"))  # ord-6c: «descuento:group_discount» de la base curada
    conocidos |= {"included", "requirements", "pricing", "itinerary", "summary"}  # subtipos de las fichas
    for tema, claves in av._temas().items():
        desconocidas = set(claves) - conocidos
        assert not desconocidas, f"tema {tema}: {desconocidas} no son topics ni claves de la base"


@pytest.mark.asyncio
async def test_arq1g_los_hechos_van_en_el_mensaje_y_los_ve_el_revisor(rag, monkeypatch):
    """ARQ-1g: en un mensaje mezclado el RAG recibe los hechos del código para la parte de la tabla."""
    rag_agent, llamadas = rag
    vistos: list[str] = []

    async def fake_verify(answer, context, lang="es"):
        vistos.append(context)
        return True, ""

    monkeypatch.setattr(rag_agent, "_verify_grounding", fake_verify)
    hechos = '[{"actividad": "minicourse", "precio": {"cartagena": {"online": "183 USD"}}}]'
    await rag_agent.rag_answer("¿cuánto cuesta el minicurso y qué peces se ven?", lang="es", hechos=hechos)
    primera = _mensaje_del_usuario(llamadas[0])
    assert "Hechos del sistema" in primera and "183 USD" in primera
    assert primera.index("183 USD") < primera.index("Pregunta del cliente")
