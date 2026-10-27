"""arq-7b (23-oct, flag `rag_hechos_sin_reintento`, latencia): en los mezclados, si al RAG le faltan puntos de las listas
de los hechos, los añade el código en vez de rehacer la respuesta (G10 nº 5: ~5 s por reintento)."""

from src.agents.rag_agent import _completar_con_hechos

_B = [{"actividad": "minicourse",
       "incluye": {"cartagena": ["Seguro obligatorio de buceo", "Entrenamiento en piscina y 1 inmersión en el mar",
                                 "Almuerzo"]},
       "recogida": {"cartagena": ["Punto de encuentro en el Muelle de la Bodeguita, a 5 minutos del centro"]}}]


def test_anade_los_puntos_que_faltan_con_su_rotulo():
    answer = ("El minicurso incluye la piscina y una inmersión en el mar. Nos vemos en el Muelle de la Bodeguita a 5 "
              "minutos del centro.")
    completada = _completar_con_hechos(answer, _B, ["incluye"], "es")
    assert completada.startswith(answer) and "También incluye:\n• Seguro obligatorio de buceo\n• Almuerzo" in completada
    assert "piscina y 1 inmersión" not in completada.split("También incluye:")[1]  # lo que ya dijo no se repite


def test_sin_nada_que_anadir_queda_igual():
    answer = ("Incluye seguro obligatorio de buceo, entrenamiento en piscina y una inmersión en el mar, y almuerzo. "
              "Punto de encuentro en el Muelle de la Bodeguita, a 5 minutos del centro.")
    assert _completar_con_hechos(answer, _B, ["incluye"], "es") == answer


def test_lo_anadido_va_delante_de_la_pregunta_del_escritor():
    """CALN-6 paso 2 (sparring CALN4, b11 t1): la pregunta con que cierra el escritor sigue al final."""
    answer = "El minicurso incluye la piscina y una inmersión en el mar.\n\n¿Quieres que te comparta el enlace?"
    completada = _completar_con_hechos(answer, _B, ["incluye"], "es")
    assert completada.startswith("El minicurso incluye") and completada.endswith("¿Quieres que te comparta el enlace?")
    assert "Muelle de la Bodeguita" in completada and "También incluye:" in completada


def test_un_precio_que_falta_no_se_anade_se_rehace():
    bloques = [{"precio": {"cartagena": {"online": "183 USD", "normal": "204 USD"}}}]
    assert _completar_con_hechos("Cuesta 100 USD.", bloques, ["precio"], "es") is None
