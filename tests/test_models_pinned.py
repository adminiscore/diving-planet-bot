"""Los modelos de PRE viven en DOS sitios a propósito, y este test impide que se separen.

- `src/config.py`: el valor por defecto de cada modelo ES el de PRE, para que un entorno sin
  esas variables (el `.env.dev` de cualquiera) no mida otro bot. Pasaba hasta el 25-sep: un
  `.env.dev` sin `OPENAI_MODEL` medía con `gpt-4o` mientras PRE usaba `gpt-4o-mini`.
- `docker-compose.vps.yml`: PRE los fija en `environment`, que gana al `.env.pre` del VPS, para
  que nadie los cambie a mano en el servidor sin que se vea en el repo (mismo patrón que
  `RAG_MIN_SCORE`).

Cambiar un modelo es cambiar los dos a la vez, y medirlo. Mapa de qué usa cada uno:
README.md, "LLM models".
"""

from pathlib import Path

import yaml

from src.config import Settings

ROOT = Path(__file__).resolve().parent.parent
MODELOS = (
    "openai_model",
    "rag_answer_model",
    "extraction_model",
    "openai_embedding_model",
    "openai_transcription_model",
    "jev_model",
)


def _entorno_de_pre() -> dict:
    compose = yaml.safe_load((ROOT / "docker-compose.vps.yml").read_text(encoding="utf-8"))
    return compose["services"]["dp-pre-bot"]["environment"]


def test_pre_fija_todos_los_modelos_en_el_compose():
    entorno = _entorno_de_pre()
    faltan = [m.upper() for m in MODELOS if m.upper() not in entorno]
    assert not faltan, f"PRE no fija en el compose: {faltan}"


def test_el_valor_por_defecto_del_codigo_es_el_de_pre():
    entorno = _entorno_de_pre()
    distintos = {
        m: (Settings.model_fields[m].default, entorno[m.upper()])
        for m in MODELOS
        if Settings.model_fields[m].default != entorno[m.upper()]
    }
    assert not distintos, f"código != PRE, (código, compose): {distintos}"


def test_ningun_modelo_de_config_queda_sin_vigilar():
    """Un ajuste de modelo nuevo en config.py tiene que entrar aquí y en el compose."""
    en_config = {n for n in Settings.model_fields if n.endswith("_model")}
    assert en_config == set(MODELOS), en_config ^ set(MODELOS)
