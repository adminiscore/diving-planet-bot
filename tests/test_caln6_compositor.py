"""CALN-6 paso 1 (27-oct): la pregunta de la reserva, una vez y al final (src/agents/compositor.py)."""
from types import SimpleNamespace

import pytest

from src.agents.compositor import componer

SEGURIDAD = "¿Ha pasado *más de 2 años* desde la última inmersión de alguno del grupo?"
PLAN_Y_SEGURIDAD = ("Te recomiendo el plan de *2 inmersiones en 1 día* en las Islas del Rosario. (Si prefieres un *paquete "
                    "multi-día* de 3 o más inmersiones, dímelo.)\n\n" + SEGURIDAD)
MENU = "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*? 🌊"
LISTAS = ("También incluye:\n• Tarifa de ingreso al Parque Nacional Natural\n• Equipo de buceo\n\n"
          "Muelle de la Bodeguita, a 5 minutos del centro histórico, a las 8:00 AM.")


def _turno(pendiente, *preguntas):
    return SimpleNamespace(core_pending_slot=pendiente, _preguntas_del_turno=list(preguntas))


def test_la_pregunta_pegada_dos_veces_queda_una_al_final():
    """regreso-otro-dia-paquete-5 t2 (caln1-B): el escritor cierra con ella, el código añade las listas y la repite."""
    r = f"Entiendo: el regreso en otra fecha lo coordina un asesor.\n\n{SEGURIDAD}\n\n{LISTAS}\n\n{SEGURIDAD}"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), r) == (
        f"Entiendo: el regreso en otra fecha lo coordina un asesor.\n\n{LISTAS}\n\n{SEGURIDAD}")


def test_la_pregunta_en_medio_pasa_al_final():
    r = f"Entiendo.\n\n{SEGURIDAD}\n\n{LISTAS}"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), r).endswith(f"{LISTAS}\n\n{SEGURIDAD}")


def test_sin_la_pregunta_no_se_toca():
    tarjeta = "🤿 *Minicurso*\n💰 2 × 655.000 COP p.p. = *1.310.000 COP*"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), tarjeta) == tarjeta
    assert componer(_turno(None, ("safety", SEGURIDAD)), f"Hola.\n\n{SEGURIDAD}") == f"Hola.\n\n{SEGURIDAD}"


def test_bien_puesta_queda_igual():
    r = f"Entiendo.\n\n{SEGURIDAD}"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), r) == r


def test_dentro_de_un_parrafo_solo_sale_la_frase():
    r = f"Con esos tiempos no alcanzarías a volar. {SEGURIDAD}\n\n{LISTAS}"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), r) == (
        f"Con esos tiempos no alcanzarías a volar.\n\n{LISTAS}\n\n{SEGURIDAD}")


def test_la_larga_y_la_corta_de_la_misma_pregunta():
    """El turno formuló la larga (con la recomendación del plan) y luego la corta: va la última, una vez."""
    r = f"{PLAN_Y_SEGURIDAD}\n\n{LISTAS}\n\n{SEGURIDAD}"
    assert componer(_turno("safety", ("safety", PLAN_Y_SEGURIDAD), ("safety", SEGURIDAD)), r) == f"{LISTAS}\n\n{SEGURIDAD}"


def test_el_menu_repetido_queda_uno():
    """vuelo-tras-bucear t2 (caln1-B): el menú de actividades dos veces, con la logística en medio."""
    r = f"Hay que esperar 18 horas para volar.\n\n{MENU}\n\n{LISTAS}\n\n{MENU}"
    assert componer(_turno("activity", ("activity", MENU)), r) == f"Hay que esperar 18 horas para volar.\n\n{LISTAS}\n\n{MENU}"


def test_en_un_pase_salen_las_copias_y_no_se_vuelve_a_poner():
    """pareja-certificados-cop-descuento-almuerzo t3 (caln1-B): pase por el pago en pesos, con la tarjeta y su nota."""
    lista = "Sobre los descuentos:\n• 10% reservando online."
    nota = "⚠️ Si alguno lleva *más de 2 años* sin bucear, se añade el *refresher*. ¿Es el caso de alguno de ustedes?"
    r = f"El de grupo no aplica.\n\n{SEGURIDAD}\n\n{lista}\n\nEl de grupo es desde 5.\n\n{SEGURIDAD}\n\n{lista}\n\n{nota}"
    assert componer(_turno("safety", ("safety", SEGURIDAD)), r, pase=True) == (
        f"El de grupo no aplica.\n\n{lista}\n\nEl de grupo es desde 5.\n\n{nota}")


def test_un_parrafo_identico_a_otro_sale():
    assert componer(_turno(None), "Hola.\n\nLista:\n• a\n\nOtra cosa.\n\nLista:\n•  a") == "Hola.\n\nLista:\n• a\n\nOtra cosa."


@pytest.mark.asyncio
async def test_sin_dato_tambien_cuando_la_pregunta_de_antes_se_aplazo(monkeypatch):
    """regateo-grupo-6 t5 (caln2-B): «¿cómo reservamos?» con el origen aplazado; la pendiente ya es la seguridad y el
    escritor no contestaba (solo salía la pregunta de seguridad, sin los enlaces)."""
    from src.agents.nucleo import slotfill_close
    from src.flows.state import ConversationState

    async def escritor(*_a, **_k):
        return "Se reserva por la web: elige la fecha y las 6 personas en el enlace."

    monkeypatch.setattr(slotfill_close, "_rag_answer", escritor)
    st = ConversationState(conversation_id="caln6", language="es")
    st._pregunta_del_escritor, st.core_pending_slot, st.preguntas_aplazadas = "¿Desde dónde saldrías?", "safety", ["location"]
    respuesta = await slotfill_close._sin_dato(st, "¿cómo reservamos?", "location", SEGURIDAD)
    assert respuesta.startswith("Se reserva por la web") and respuesta.endswith(SEGURIDAD)
    st.preguntas_aplazadas = []  # la contestó: la pregunta cambia porque ya hay dato, no es un turno sin dato
    assert await slotfill_close._sin_dato(st, "desde cartagena", "location", SEGURIDAD) is None


OFERTA_OW = "Si quieres, te ayudo a reservar: *Curso Open Water*. ¿Te animas? 🌊"
ORIGEN = ("¿Desde dónde saldrías? Puedes salir *desde Cartagena* (desde el Muelle de la Bodeguita, ida y vuelta el mismo "
          "día) o, si ya estás *en las islas*, coordinamos la recogida en tu hotel.")


def _con_botones(pendiente, *preguntas, sugerida=None, al_empezar=None):
    turno = _turno(pendiente, *preguntas)
    turno.quick_replies = [{"title": "✅ Sí, quiero reservar", "value": "sí"}]
    turno.suggested_activity, turno._sugerida_al_empezar = sugerida, al_empezar
    return turno


def test_si_el_escritor_ya_pregunta_la_de_la_reserva_espera():
    """edad-minima-open-water t1 (caln2-B): la pregunta del escritor, el bloque de lo que hace falta y la oferta de gen-8
    detrás. Va UNA: la del escritor; la de la reserva queda pendiente, sin sus botones ni la recomendación que el
    cliente no vio (un «sí» a «¿te cuento más?» no elige el Open Water)."""
    escritor = ("La edad mínima para el curso Open Water es de 10 años. ¿Quieres que te cuente algo más sobre el curso?"
                "\n\nTambién necesitas:\n• Traje de baño")
    turno = _con_botones("activity", ("activity", OFERTA_OW), sugerida="padi_open_water")
    assert componer(turno, f"{escritor}\n\n{OFERTA_OW}") == escritor
    assert turno.core_pending_slot == "activity" and turno.quick_replies == [] and turno.suggested_activity is None


def test_la_oferta_de_asesor_del_escritor_no_la_tapa_otra_pregunta():
    """curso-open-water-transporte-y-regreso-otro-dia t2 (caln2-B), la regla de u3-4 en todos los caminos."""
    oferta = "If you'd like, I can help you book it: *Open Water course*. Shall we? 🌊"
    escritor = "A team advisor would need to confirm the arrangements. Would you like me to connect you with one?"
    assert componer(_con_botones("activity", ("activity", oferta)), f"{escritor}\n\n{oferta}") == escritor


def test_la_recomendacion_de_un_turno_anterior_se_queda():
    turno = _con_botones("activity", ("activity", OFERTA_OW), sugerida="minicourse", al_empezar="minicourse")
    componer(turno, f"¿Te cuento más?\n\n{OFERTA_OW}")
    assert turno.suggested_activity == "minicourse"


def test_sin_otra_pregunta_la_de_la_reserva_sigue_con_sus_botones():
    turno = _con_botones("activity", ("activity", OFERTA_OW), sugerida="padi_open_water")
    assert componer(turno, f"La edad mínima es de 10 años.\n\n{OFERTA_OW}\n\n{LISTAS}") == (
        f"La edad mínima es de 10 años.\n\n{LISTAS}\n\n{OFERTA_OW}")
    assert turno.quick_replies and turno.suggested_activity == "padi_open_water"


@pytest.mark.parametrize("dicho", [
    "¡Perfecto, serían 2 personas para el minicurso de buceo para principiantes!",  # minicurso-precio-colombianos-…
    "¡Entendido! Entonces son 5 personas: 4 buzos certificados y 1 persona que haría el minicurso.",  # grupo-recompuesto
])
def test_la_explicacion_de_la_pregunta_no_se_repite(dicho):
    """caln2-B: el escritor dice la explicación del origen con la pregunta debajo, que la vuelve a decir."""
    explicacion = ORIGEN.split("? ", 1)[1]
    r = f"{dicho} {explicacion}\n\n{ORIGEN}"
    assert componer(_turno("location", ("location", ORIGEN)), r) == f"{dicho}\n\n{ORIGEN}"


@pytest.mark.parametrize("dijo,recomienda", [({}, True), ({"detected_cert_dives": 2}, False),
                                             ({"detected_cert_dives": 5}, False), ({"detected_cert_days": 3}, False)])
def test_la_recomendacion_del_plan_solo_si_el_cliente_no_lo_dijo(dijo, recomienda):
    """Sparring q2 t4 (27-oct): «I'd do the 2 dives» y debajo de sus enlaces «I recommend the 2 dives in 1 day plan»."""
    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="plan", language="es")
    st.detected_activity = "certified_diving"
    for campo, valor in dijo.items():
        setattr(st, campo, valor)
    assert bool(core._recommended_plan_intro(st)) is recomienda


def test_si_contesta_el_escritor_el_saludo_se_queda_en_la_presentacion():
    """Batería CALN4 (b5 t1): «…¡Qué alegría tenerte por acá! Con muchísimo gusto te ayudo a armar tu plan.» y debajo
    «¡Con mucho gusto te ayudo a armar el plan!». Si el turno es solo una pregunta del código, el saludo va entero."""
    from src.agents.conversational_core import _greeting

    saludo = _greeting(SimpleNamespace(client_name=None, language="es")).rstrip()
    escritor = "¡Con mucho gusto te ayudo a armar el plan! 🐠"
    compuesta = componer(_turno(None), f"{saludo}\n\n{escritor}", escribio=True)
    assert compuesta == ("¡Hola! 🪸 Soy *Coral*, de *Diving Planet* — buceamos todo el año en las Islas del Rosario, "
                         f"saliendo desde Cartagena o desde las propias islas. 🌊\n\n{escritor}")
    assert componer(_turno(None), f"{saludo}\n\n{MENU}", escribio=False) == f"{saludo}\n\n{MENU}"


def test_la_invitacion_generica_de_la_tarjeta_cede_ante_una_pregunta_concreta():
    """Batería CALN4 (b2 t2): la pregunta del escritor, la tarjeta y su «Is there anything else I can help you with?»."""
    from src.flows.cart_render import CIERRE_DE_LA_TARJETA

    tarjeta = "🤿 *Dive Mini Course*\n💰 2 × 134 USD p.p. = *268 USD*"
    escritor = "Would you like help adding the refresher for him?"
    cierre = CIERRE_DE_LA_TARJETA["en"]
    assert componer(_turno(None), f"{escritor}\n\n{tarjeta}\n\n{cierre}") == f"{escritor}\n\n{tarjeta}"
    assert componer(_turno(None), f"Done.\n\n{tarjeta}\n\n{cierre}") == f"Done.\n\n{tarjeta}\n\n{cierre}"


def test_en_el_historial_queda_lo_que_vio_el_cliente():
    from src.agents.supervisor import _lo_que_vio_el_cliente

    st = SimpleNamespace(history=[{"role": "assistant", "content": "turno de antes"}, {"role": "user", "content": "hola"},
                                  {"role": "assistant", "content": f"Respuesta.\n\n{OFERTA_OW}"}])
    _lo_que_vio_el_cliente(st, "Respuesta.", 1)
    assert [h["content"] for h in st.history] == ["turno de antes", "hola", "Respuesta."]
    st.history = st.history[:2]  # un turno que no apuntó nada: el de antes no se toca
    _lo_que_vio_el_cliente(st, "otra", 1)
    assert st.history[0]["content"] == "turno de antes"


@pytest.mark.parametrize("escritor,queda", [
    ("¡Hola! Bucear en las islas es una experiencia muy chévere 🐠", "Bucear en las islas es una experiencia muy chévere 🐠"),
    ("¡Hola! ¡Con mucho gusto! Sí, operamos todos los días.", "¡Con mucho gusto! Sí, operamos todos los días."),
    ("Hi! Snorkeling is a lovely way to enjoy the reef.", "Snorkeling is a lovely way to enjoy the reef."),
    ("Hola Marta, el minicurso cuesta 655.000 COP.", "El minicurso cuesta 655.000 COP."),
    ("Holandeses también vienen, ¿verdad?", "Holandeses también vienen, ¿verdad?"),  # no es un saludo
])
def test_tras_el_saludo_de_coral_el_escritor_no_vuelve_a_saludar(escritor, queda):
    saludo = "¡Hola! 🪸 Soy *Coral*, de *Diving Planet* — buceamos todo el año. 🌊"
    assert componer(_turno(None), f"{saludo}\n\n{escritor}") == f"{saludo}\n\n{queda}"
    assert componer(_turno(None), escritor) == escritor  # sin el saludo de Coral, nada
