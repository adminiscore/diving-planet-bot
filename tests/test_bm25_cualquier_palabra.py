"""BM25 (17-oct, flag `bm25_cualquier_palabra`): `websearch_to_tsquery` exige TODAS las palabras y, medido en la base de
PRE con las 51 preguntas de rag_piezas, 48 no traían ningún documento (4 de 97 datos en el top-8); con CUALQUIER
palabra (OR), ninguna vacía y 53 de 97. Además BM25 buscaba la última línea de la consulta, que puede ser la marca de
origen de rag_agent ("[origen_cliente]=ya en las islas") en vez de la pregunta."""
import pytest

from src.config import settings
from src.knowledge import vector_store as vs


class _Conn:
    def __init__(self, sqls):
        self.sqls = sqls

    async def fetch(self, sql, *args):
        self.sqls.append((sql, args))
        return []


class _Pool:
    def __init__(self, sqls):
        self.sqls = sqls

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return _Conn(pool.sqls)

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.mark.asyncio
@pytest.mark.parametrize("flag, esperado", [(False, "websearch_to_tsquery"), (True, "replace(plainto_tsquery")])
async def test_la_consulta_sql_segun_el_flag(monkeypatch, flag, esperado):
    sqls: list = []

    async def _pool():
        return _Pool(sqls)

    monkeypatch.setattr(vs, "_get_pool", _pool)
    monkeypatch.setattr(settings, "bm25_cualquier_palabra", flag)
    await vs._bm25_search("¿cuánto cuesta el minicurso?", lang="es", k=8)
    assert esperado in sqls[0][0]
    assert sqls[0][1][0] == "¿cuánto cuesta el minicurso?"  # la pregunta va como parámetro, nunca en el texto SQL


@pytest.mark.asyncio
@pytest.mark.parametrize("flag, linea", [(False, "[origen_cliente]=ya en las islas"),
                                         (True, "¿cuánto cuesta el minicurso?")])
async def test_bm25_busca_la_pregunta_y_no_la_marca_de_origen(monkeypatch, flag, linea):
    vistas: list[str] = []

    async def _bm25(query, lang="es", k=8):
        vistas.append(query)
        return []

    async def _vector(query, lang="es", k=8):
        return []

    monkeypatch.setattr(vs, "_bm25_search", _bm25)
    monkeypatch.setattr(vs, "_vector_search", _vector)
    monkeypatch.setattr(settings, "bm25_cualquier_palabra", flag)
    await vs.search_knowledge_base("¿cuánto cuesta el minicurso?\n\n[origen_cliente]=ya en las islas", lang="es")
    assert vistas == [linea]
