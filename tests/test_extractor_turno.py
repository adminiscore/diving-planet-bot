"""ex-4 (fase EX, 12-oct): el extractor "LLM primero" — la parte determinista (citas y lugares) y la degradación."""
import asyncio

from src.agents import extractor_turno as ex


def test_la_cita_tiene_que_estar_en_el_mensaje():
    assert ex.cita_verificable("somos 3", "Hola, somos 3 y queremos bucear")
    assert ex.cita_verificable("Somos   3!", "hola somos 3")  # mayúsculas, espacios y puntuación no cuentan
    assert not ex.cita_verificable("buzo certificado", "gracias")  # lo sacado del historial no pasa
    assert not ex.cita_verificable("", "hola")


def test_cita_en_varios_trozos():
    msg = "2 diving sessions - All PADI\nSnorkeling\n1 Adult (Age 43)"
    assert ex.cita_verificable("2 diving sessions … Snorkeling", msg)
    assert not ex.cita_verificable("2 diving sessions … 3 kids", msg)


def test_la_ubicacion_tiene_que_nombrar_un_lugar():
    assert ex.nombra_un_lugar("desde cartagena")
    assert ex.nombra_un_lugar("Im staying at el hamaquero")  # hotel de la lista cerrada
    assert ex.nombra_un_lugar("quedándonos en el hotel")
    assert not ex.nombra_un_lugar("im getting in tmrw")


def test_ultima_pregunta_del_bot():
    h = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¿Desde dónde saldrías?"}]
    assert ex.ultima_pregunta_del_bot(h) == "¿Desde dónde saldrías?"
    assert ex.ultima_pregunta_del_bot([]) is None


class _ClienteRoto:
    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            async def create(**_):
                raise RuntimeError("API caída")


def test_si_la_api_falla_devuelve_none():
    assert asyncio.run(ex.extraer_turno("somos 3 desde cartagena", client=_ClienteRoto())) is None


def _cliente_que_devuelve(datos: dict):
    """Un cliente simulado cuya respuesta JSON es `datos` (los campos que faltan van a null)."""
    import json
    from types import SimpleNamespace

    completo = {c: None for c in (*ex.CAMPOS, *ex.EXTRAS)} | datos

    class _Cliente:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    msg = SimpleNamespace(content=json.dumps(completo))
                    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

    return _Cliente()


def _si(cita: str) -> dict:
    return {"valor": True, "cita": cita}


def test_buzo_certificado_que_quiere_bucear_hace_buceo_certificado():
    """ex-8: la regla del negocio la aplica el código con dos hechos que el cliente afirma (no la deduce el modelo)."""
    msg = "somos Advanced y queremos coordinar inmersiones"
    cliente = _cliente_que_devuelve({"is_certified": _si("somos Advanced"),
                                     "quiere_bucear": _si("queremos coordinar inmersiones")})
    assert asyncio.run(ex.extraer_turno(msg, client=cliente)) == {"is_certified": True, "activity": "certified_diving"}


def test_la_certificacion_ya_sabida_cuenta():
    cliente = _cliente_que_devuelve({"quiere_bucear": _si("valores de dos buceos")})
    salida = asyncio.run(ex.extraer_turno("valores de dos buceos", sabido={"is_certified": True}, client=cliente))
    assert salida == {"activity": "certified_diving"}


def test_querer_bucear_sin_certificacion_no_elige_actividad():
    """Decisión de Gadea (14/27-sep): sin actividad elegida, el bot recomienda; "quiere_bucear" no viaja al estado."""
    cliente = _cliente_que_devuelve({"quiere_bucear": _si("quiero bucear")})
    assert asyncio.run(ex.extraer_turno("quiero bucear con mi amigo", client=cliente)) == {}
