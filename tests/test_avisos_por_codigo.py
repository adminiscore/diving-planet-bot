"""lat-deuda (26-oct, diseño aprobado por Gadea): los avisos que el cliente necesita y no pregunta los pone el CÓDIGO al
final de la respuesta, en cualquier camino (`src/flows/avisos.py`, `supervisor.route_message`), sin ninguna llamada.

Se fija:
1. los hechos salen de campos ESTRUCTURADOS del estado (actividad, origen, nacionalidad, grupo), nunca del texto, y no
   hay ninguna lista de nombres ni de palabras;
2. el tema sale de las intenciones de Jev del turno, no de la búsqueda del RAG (que solo existe en un camino);
3. un aviso aplica si se cumple uno de sus juegos de condiciones, los de `una_vez` no se repiten y uno sin condiciones
   no sale nunca;
4. va como mucho UNO por turno, en el idioma del cliente, al final y delante de la pregunta final; si la respuesta ya
   lo dice no se repite; en un pase a persona no se pone;
5. el fichero de avisos es válido: id único, fuente que existe en la base, textos en los dos idiomas, condiciones y
   temas conocidos.
"""

import json

import pytest

from src.agents import supervisor
from src.flows import avisos as av
from src.flows.state import ConversationState, Step

# ---------------------------------------------------------------- 1. hechos del estado


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="t", language=campos.pop("language", "es"))
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def _ids(hechos: dict, temas: set[str]) -> list[str]:
    return [a["id"] for a in av.seleccionar(hechos, temas)]


def test_la_actividad_sale_del_estado_no_del_texto():
    """La actividad elegida en el árbol, la que detectó el extractor, la del carrito y las del reparto del grupo."""
    assert "minicourse" in av.hechos_del_estado(_estado(detected_activity="minicourse"))["actividades"]
    assert "minicourse" in av.hechos_del_estado(_estado(selected_service="minicourse"))["actividades"]
    assert av.hechos_del_estado(
        _estado(detected_group_allocation={"certified_diving": 2, "snorkel": 1, "undecided": 1}))["actividades"] \
        >= {"certified_diving", "snorkel"}
    assert "undecided" not in av.hechos_del_estado(
        _estado(detected_group_allocation={"undecided": 2}))["actividades"]
    hablado = _estado(history=[{"role": "user", "content": "me interesa el minicurso para certificarme"}])
    assert av.hechos_del_estado(hablado)["actividades"] == set()


def test_el_refresher_y_el_buceo_certificado_constan_por_sus_campos():
    assert "refresher" in av.hechos_del_estado(_estado(last_dive_over_2_years=True))["actividades"]
    assert "refresher" in av.hechos_del_estado(_estado(refresher_interested=True))["actividades"]
    assert "certified_diving" in av.hechos_del_estado(_estado(is_certified=True))["actividades"]


def test_la_nacionalidad_mixta_manda_sobre_la_de_quien_escribe():
    assert av.hechos_del_estado(_estado(is_colombian=True))["nacionalidad"] == "colombiano"
    assert av.hechos_del_estado(_estado(is_colombian=False))["nacionalidad"] == "extranjero"
    assert av.hechos_del_estado(_estado(is_colombian=False, mixed_nationality_notice=True))["nacionalidad"] == "mixto"
    assert av.hechos_del_estado(_estado())["nacionalidad"] is None


def test_el_grupo_es_el_del_extractor_o_la_suma_del_reparto():
    assert av.hechos_del_estado(_estado(detected_group_size=6))["grupo"] == 6
    assert av.hechos_del_estado(_estado(detected_group_allocation={"certified_diving": 2, "minicourse": 4}))["grupo"] == 6
    assert av.hechos_del_estado(_estado())["grupo"] == 0


def test_no_hay_listas_de_nombres_de_lugares_ni_de_palabras():
    """Norma del proyecto (Gadea): soluciones genéricas, nunca patrones que acierten unas conversaciones y fallen otras.
    Un aviso que depende de dónde está el cliente espera a que el dato esté en el estado (Barú salió del fichero el
    26-oct porque el estado no guarda la zona del hotel)."""
    datos = json.loads(av.AVISOS_PATH.read_text(encoding="utf-8-sig"))
    assert "zonas" not in datos, "una tabla de nombres de lugares es un parche: el lugar lo da el estado"
    assert "zona" not in av.hechos_del_estado(_estado(island="Isla Barú"))


# ---------------------------------------------------------------- 2. el tema, de las intenciones de Jev


def test_el_tema_sale_de_las_intenciones_de_jev():
    assert av.temas_del_turno(["precio"]) == {"precio"}
    assert av.temas_del_turno(["enlace"]) == {"reservar"}
    assert {"comida", "recogida", "certificacion"} <= av.temas_del_turno(["incluye"])
    assert av.temas_del_turno([]) == set() and av.temas_del_turno(None) == set()
    assert av.temas_del_turno(["edad"]) == set()


# ---------------------------------------------------------------- 3. la selección


def test_el_aviso_necesita_todas_sus_condiciones():
    """minicurso-no-certifica: la actividad es el minicurso Y la pregunta va de certificarse (requisitos o qué incluye)."""
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    assert "minicurso-no-certifica" in _ids(hechos, av.temas_del_turno(["incluye"]))
    assert "minicurso-no-certifica" not in _ids(hechos, av.temas_del_turno(["precio"]))
    assert "minicurso-no-certifica" not in _ids(av.hechos_del_estado(_estado()), av.temas_del_turno(["incluye"]))


def test_el_descuento_de_grupo_al_hablar_de_descuentos_o_a_un_grupo_de_5_que_pregunta_el_precio():
    """Juegos de condiciones: basta con que se cumpla uno."""
    seis = av.hechos_del_estado(_estado(detected_group_size=6))
    tres = av.hechos_del_estado(_estado(detected_group_size=3))
    assert "descuento-grupo-no-cursos" in _ids(seis, {"precio"})
    assert "descuento-grupo-no-cursos" not in _ids(tres, {"precio"})
    assert "descuento-grupo-no-cursos" in _ids(tres, {"descuentos"})
    assert "descuento-grupo-no-cursos" not in _ids(seis, set())


def test_los_avisos_de_una_vez_no_se_repiten():
    hechos = av.hechos_del_estado(_estado(detected_activity="minicourse"))
    assert "minicurso-no-certifica" in _ids(hechos, {"certificacion"})
    hechos["dados"] = ["minicurso-no-certifica"]
    assert "minicurso-no-certifica" not in _ids(hechos, {"certificacion"})


def test_un_aviso_sin_condiciones_no_sale_nunca(monkeypatch):
    monkeypatch.setattr(av, "_datos", lambda: {"avisos": [
        {"id": "suelto", "fuente": "x", "aviso_es": "a", "aviso_en": "a", "cuando": {}},
        {"id": "suelto-lista", "fuente": "x", "aviso_es": "a", "aviso_en": "a", "cuando": [{}]}]})
    assert _ids(av.hechos_del_estado(_estado()), {"precio"}) == []


def test_moneda_segun_la_nacionalidad():
    extranjero = av.hechos_del_estado(_estado(is_colombian=False))
    assert "extranjero-paga-en-usd" in _ids(extranjero, {"pago"})
    assert "extranjero-paga-en-usd" in _ids(extranjero, {"reservar"})
    colombiano = av.hechos_del_estado(_estado(is_colombian=True))
    assert "extranjero-paga-en-usd" not in _ids(colombiano, {"pago"})
    assert "sin-precio-especial-colombianos" in _ids(colombiano, {"descuentos"})
    mixto = av.hechos_del_estado(_estado(is_colombian=False, mixed_nationality_notice=True))
    assert "grupo-mixto-todo-usd" in _ids(mixto, {"precio"})


def test_lo_de_las_islas_solo_a_quien_sale_de_las_islas():
    islas = av.hechos_del_estado(_estado(location="island"))
    assert "almuerzo-desde-islas" in _ids(islas, {"comida"})
    assert "recogida-en-hotel-islas" in _ids(islas, {"precio"})
    cartagena = av.hechos_del_estado(_estado(location="cartagena"))
    assert not {"almuerzo-desde-islas", "recogida-en-hotel-islas"} & set(_ids(cartagena, {"comida", "precio"}))


def test_refresher_y_certificados_juntos_solo_en_un_grupo():
    """Un solo buzo inactivo consta a la vez como refresher y como buceo certificado: no es un grupo."""
    solo = av.hechos_del_estado(_estado(is_certified=True, last_dive_over_2_years=True))
    assert "refresher-y-certificado-juntos" not in _ids(solo, set())
    assert "refresh-tras-dos-anos" in _ids(solo, set())
    pareja = av.hechos_del_estado(_estado(is_certified=True, last_dive_over_2_years=True, detected_group_size=2))
    assert "refresher-y-certificado-juntos" in _ids(pareja, set())


# ---------------------------------------------------------------- 4. poner el aviso en la respuesta


def _con(intenciones, **campos) -> ConversationState:
    st = _estado(**campos)
    st._intenciones = intenciones
    return st


def test_va_delante_de_la_pregunta_final():
    st = _con(["disponibilidad"])
    resp = av.poner_avisos(st, "El buceo certificado desde Cartagena cuesta 178 USD. ¿Para cuántas personas sería? 😊")
    partes = resp.split("\n\n")
    assert partes[0] == "El buceo certificado desde Cartagena cuesta 178 USD."
    assert partes[1].startswith("Siempre hay disponibilidad")
    assert partes[2] == "¿Para cuántas personas sería? 😊"
    assert st.avisos_dados == ["operamos-todos-los-dias"]


def test_sin_pregunta_final_va_al_final():
    st = _con(["disponibilidad"])
    resp = av.poner_avisos(st, "Perfecto, te espero.\n- uno\n- dos")
    assert resp.startswith("Perfecto, te espero.\n- uno\n- dos\n\nSiempre hay disponibilidad")


def test_la_lista_de_antes_no_se_toca():
    resp = av._insertar("Incluye:\n- equipo\n- guía\n¿Te lo reservo?", "AVISO")
    assert resp == "Incluye:\n- equipo\n- guía\n\nAVISO\n\n¿Te lo reservo?"


def test_dos_preguntas_al_final_van_juntas_detras():
    assert av._insertar("Hecho. ¿Cuántos sois? ¿De dónde salís?", "AVISO") == "Hecho.\n\nAVISO\n\n¿Cuántos sois? ¿De dónde salís?"
    assert av._insertar("Which date? How many people?", "AVISO") == "AVISO\n\nWhich date? How many people?"


def test_la_pregunta_con_sus_opciones_en_lista_va_al_final():
    """Ronda avisos-B: en la bienvenida el aviso salía detrás del menú de actividades."""
    resp = av._insertar("¡Hola!\n\nCuéntame, ¿qué te gustaría vivir con nosotros? 🤿\n• *Buceo*\n• *Minicurso*", "AVISO")
    assert resp == "¡Hola!\n\nAVISO\n\nCuéntame, ¿qué te gustaría vivir con nosotros? 🤿\n• *Buceo*\n• *Minicurso*"


def test_la_frase_de_cierre_tras_la_pregunta_va_con_ella():
    texto = "Son 5 personas.\n\nNecesito saber: ¿sales desde Cartagena o ya estás en las islas? Los precios cambian. 🌊"
    assert av._insertar(texto, "AVISO") == ("Son 5 personas.\n\nAVISO\n\nNecesito saber: ¿sales desde Cartagena o ya "
                                            "estás en las islas? Los precios cambian. 🌊")


def test_el_interrogante_de_un_enlace_no_es_una_pregunta():
    resp = av._insertar("Reserva aquí:\nhttps://book.divingplanet.org/book/x?language=es", "AVISO")
    assert resp.endswith("?language=es\n\nAVISO")


def test_con_sus_cifras_y_parte_de_sus_palabras_ya_lo_dice():
    """Ronda avisos-B: «siempre hay disponibilidad, excepto el 25 de diciembre y el 1 de enero» ya lo decía."""
    ya = ("¡Buenos días! Sí, siempre hay disponibilidad, excepto el 25 de diciembre y el 1 de enero. La fecha se elige "
          "en el enlace. ¿Qué te gustaría hacer?")
    st = _con(["disponibilidad"])
    assert av.poner_avisos(st, ya) == ya and st.avisos_dados == ["operamos-todos-los-dias"]
    # Una cifra suelta no basta: «10 %» online y «5 personas» no son el descuento de grupo.
    st = _con(["precio"], detected_group_size=5)
    resp = av.poner_avisos(st, "Para las 5 personas el precio online incluye el 10 % de descuento.")
    assert "10 % de descuento de grupo" in resp


def test_en_ingles_va_en_ingles():
    st = _con(["disponibilidad"], language="en")
    assert "There is always availability" in av.poner_avisos(st, "Sure, it's 178 USD.")


def test_como_mucho_uno_y_el_siguiente_turno_otro():
    st = _con(["precio", "pago"], is_colombian=False, mixed_nationality_notice=True, detected_group_size=6,
              location="island")
    primera = av.poner_avisos(st, "Son 124 USD por persona.")
    assert len(st.avisos_dados) == 1 and primera.count("\n\n") == 1
    segunda = av.poner_avisos(st, "Son 124 USD por persona.")
    assert len(st.avisos_dados) == 2 and segunda != primera


def test_si_la_respuesta_ya_lo_dice_no_se_repite_y_cuenta_como_dado():
    st = _con(["disponibilidad"])
    ya = ("Siempre hay disponibilidad: operamos todos los días, festivos incluidos, salvo el 25 de diciembre y el 1 de "
          "enero.")
    assert av.poner_avisos(st, ya) == ya
    assert st.avisos_dados == ["operamos-todos-los-dias"]


def test_sin_nada_que_avisar_la_respuesta_no_cambia():
    assert av.poner_avisos(_con([]), "Hola, ¿en qué te ayudo?") == "Hola, ¿en qué te ayudo?"
    assert av.poner_avisos(_con(["disponibilidad"]), "") == ""


async def _route(monkeypatch, st, respuesta, pase=None):
    async def _grafo(state, message):
        state._intenciones = ["disponibilidad"]
        if pase:
            state.step = Step.ESCALATE
            state.pending_escalation_reason = pase
        return respuesta
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _grafo)
    return await supervisor.route_message(st, "¿tenéis sitio el sábado?")


@pytest.mark.asyncio
async def test_el_cierre_del_turno_lo_pone(monkeypatch):
    st = _estado()
    resp = await _route(monkeypatch, st, "Sí, el sábado salimos. ¿Cuántos sois?")
    assert "Siempre hay disponibilidad" in resp and resp.endswith("¿Cuántos sois?")


@pytest.mark.asyncio
async def test_en_un_pase_a_persona_no_se_pone(monkeypatch):
    st = _estado()
    resp = await _route(monkeypatch, st, "Te paso con un asesor del equipo.", pase="solicitó asesor")
    assert "Siempre hay disponibilidad" not in resp


@pytest.mark.asyncio
async def test_con_la_conversacion_ya_con_una_persona_no_se_pone(monkeypatch):
    st = _estado(step=Step.ESCALATE, pending_escalation_reason="solicitó asesor")
    resp = await _route(monkeypatch, st, "El asesor ya tiene tu caso.")
    assert "Siempre hay disponibilidad" not in resp


# ---------------------------------------------------------------- 5. el fichero


def _de_la_base(fichero: str, clave: str) -> list[str]:
    datos = json.loads((av.AVISOS_PATH.parent / fichero).read_text(encoding="utf-8-sig"))
    return list(datos.get(clave, datos).keys())


def test_el_fichero_de_avisos_es_valido():
    """Lo edita el negocio: un id repetido, una fuente que no existe, un texto que falta en un idioma o una condición
    inventada tienen que verse aquí."""
    from src.domain import activities as dom

    datos = json.loads(av.AVISOS_PATH.read_text(encoding="utf-8-sig"))
    politicas = set(_de_la_base("policies.json", "policies"))
    servicios = set(_de_la_base("services.json", "services"))
    descuentos = set(_de_la_base("discounts.json", "discounts"))
    ids = [a["id"] for a in datos["avisos"]]
    assert len(ids) == len(set(ids)), "ids repetidos"
    assert len(av.avisos()) == len(ids), "todos los avisos llevan el texto en los dos idiomas"
    actividades = set(dom.activity_ids())
    temas = set(av._temas())
    for aviso in datos["avisos"]:
        assert aviso["aviso_es"].strip() and aviso["aviso_en"].strip(), aviso["id"]
        fuente = aviso["fuente"]
        if fuente.startswith("ficha:"):
            assert fuente.split(":", 1)[1] in servicios, f"{aviso['id']}: ficha {fuente} no existe"
        elif fuente.startswith("descuento:"):
            assert fuente.split(":", 1)[1] in descuentos, f"{aviso['id']}: descuento {fuente} no existe"
        else:
            assert fuente in politicas, f"{aviso['id']}: política {fuente} no existe"
        cuando = aviso.get("cuando")
        juegos = cuando if isinstance(cuando, list) else [cuando]
        assert juegos and all(juegos), f"{aviso['id']}: sin condiciones no saldría nunca"
        for juego in juegos:
            for campo, valor in juego.items():
                assert campo in {"actividad", "actividad_tambien", "origen", "nacionalidad", "tema",
                                 "inactivo_mas_de_2_anos", "grupo_min"}, f"{aviso['id']}: condición {campo} desconocida"
                if campo in ("actividad", "actividad_tambien"):
                    assert set(valor) <= actividades, f"{aviso['id']}: actividad fuera del registro"
                if campo == "tema":
                    assert set(valor) <= temas, f"{aviso['id']}: tema sin definir"
                if campo == "origen":
                    assert valor in ("cartagena", "island"), f"{aviso['id']}: origen desconocido"
                if campo == "nacionalidad":
                    assert valor in ("colombiano", "extranjero", "mixto"), f"{aviso['id']}: nacionalidad desconocida"
                if campo == "grupo_min":
                    assert isinstance(valor, int) and valor >= 2, f"{aviso['id']}: grupo_min no es un número válido"


def test_los_temas_son_intenciones_de_jev():
    """Un tema que no sale de una intención de Jev no se cumpliría nunca."""
    from src.orchestration.graph import _INTENCION_DE_SENAL

    for tema, de_jev in av._temas().items():
        assert de_jev and set(de_jev) <= set(_INTENCION_DE_SENAL), f"tema {tema}: {de_jev}"
