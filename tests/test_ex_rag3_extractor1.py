"""EX-EXTRACTOR-1 (aclaraciones del extractor), 14-oct. El revisor con cita de EX-RAG-3 (flag `juez_revisa_con_cita`,
APAGADO desde el 14-oct) se borró en ex-9b con sus tests."""
import asyncio



def test_aclaraciones_del_extractor_con_el_flag(monkeypatch):
    from src.agents import extractor_turno as ex

    capturado = {}

    class _Cliente:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kw):
                    capturado["sistema"] = kw["messages"][0]["content"]
                    raise RuntimeError("solo miramos el prompt")

    asyncio.run(ex.extraer_turno("Va quiero comprar sin ir de cartagena", client=_Cliente()))
    assert ex.UBICACION_NEGACION_ES in capturado["sistema"]
