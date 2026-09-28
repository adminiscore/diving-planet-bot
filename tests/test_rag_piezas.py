"""rag-1: el reparto de causas por dato de scripts/rag_piezas.py (sin red)."""
import json

from scripts.rag_piezas import PREGUNTAS, _oculto, norm, presente, puntuar

CASO = {"id": "c", "necesita": [
    {"id": "precio", "hecho": "1.429.000 COP", "anclas": ["1429000"]},
    {"id": "hotel", "hecho": "Majagua", "anclas": ["san pedro + majagua"]},
    {"id": "total", "hecho": "total", "anclas": ["1940000"], "calculo": True},
]}


def _fila(**kw):
    base = {"busquedas": [{"docs": [{"content": "otra cosa"}, {"content": "Precio: $1,429,000 COP"}]}],
            "fragmentos": [{"content": "Precio: $1,429,000 COP"}],
            "llamadas": [{"sistema": "CATÁLOGO: 1.429.000 COP", "usuario": "Contexto: hotel San Pedro de Majagua"}],
            "fallback": False, "verificacion": {"datos": {}}}
    base.update(kw)
    return base


def _causas(fila):
    return {d["id"]: d["causa"] for d in puntuar(CASO, fila)["datos"]}


def test_norm_quita_tildes_y_separadores_de_miles():
    assert norm("Canción 1.429.000 y $1,429,000") == "cancion 1429000 y $1429000"
    assert presente({"anclas": ["san pedro + majagua"]}, norm("Hotel San Pedro de Majagua"))
    assert not presente({"anclas": ["san pedro + majagua"]}, norm("Hotel San Pedro"))


def test_rango_en_top8_y_contexto_visto():
    d = {x["id"]: x for x in puntuar(CASO, _fila())["datos"]}
    assert d["precio"]["rango_top8"] == 2 and d["precio"]["en_contexto"]
    assert d["hotel"]["rango_top8"] is None and d["hotel"]["en_contexto"]  # llegó por el estado, no por la búsqueda
    assert d["total"]["en_contexto"] is None  # un cálculo no cuenta para la búsqueda


def test_causas():
    fila = _fila(verificacion={"datos": {"precio": "dice", "hotel": "contradice"}})
    assert _causas(fila) == {"precio": "ok", "hotel": "contradice", "total": "redaccion"}
    sin_hotel = _fila(llamadas=[{"sistema": "", "usuario": "1429000"}])
    assert _causas(sin_hotel)["hotel"] == "busqueda"
    assert _causas(_fila(fallback=True)) == {"precio": "juez_corta", "hotel": "juez_corta", "total": "juez_corta"}


def test_el_set_no_usa_el_examen_oculto():
    casos = json.loads(PREGUNTAS.read_text(encoding="utf-8"))["casos"]
    oculto = _oculto()
    assert casos and not [c["id"] for c in casos if c["origen"].split(":", 1)[-1].split("#")[0] in oculto]


def test_compactar_y_expandir_ida_y_vuelta():
    from scripts.rag_piezas import compactar, expandir

    run = {"filas": [{"llamadas": [{"sistema": "S1", "usuario": "u"}, {"sistema": "S1"}]},
                     {"llamadas": [{"sistema": "S2"}]}]}
    c = compactar(json.loads(json.dumps(run)))
    assert c["sistemas"] == ["S1", "S2"] and c["filas"][0]["llamadas"][1]["sistema"] == "@0"
    assert expandir(c)["filas"] == run["filas"]
