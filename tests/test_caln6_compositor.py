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
