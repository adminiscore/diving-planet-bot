"""El presupuesto de complejidad (scripts/complejidad.py): lo que cuenta, con textos de ejemplo."""
import json

from scripts import complejidad as cx

ESTADO = '''
@dataclass
class Otra:
    no_cuenta: int = 0


@dataclass
class ConversationState:
    conversation_id: str = ""
    language: str = "es"
    # un comentario no es un campo
    detected_group_size: int | None = None

    def metodo(self) -> None:
        x: int = 1


ConversationState.detected_group_allocation = property(lambda s: None)
'''


def test_los_campos_del_estado_son_los_de_su_clase():
    assert cx.campos_del_estado(ESTADO) == 3


def test_los_interruptores_son_los_bool_de_config():
    config = "class Settings:\n    a: bool = False\n    b: str = 'x'\n    c: bool = True\n"
    assert len(cx._BOOL.findall(config)) == 2


def test_llamadas_y_latencia_de_una_ronda(tmp_path):
    ronda = tmp_path / "r.metricas"
    ronda.write_text("\n".join(json.dumps({"llm_calls": n, "latency": s}) for n, s in ((2, 1.0), (4, 3.0))),
                     encoding="utf-8")
    assert cx.de_la_ronda(str(ronda)) == {"turnos": 2, "llamadas_por_turno": 3.0, "p50_s": 3.0, "p95_s": 3.0}


def test_tambien_de_una_medida_de_reproducir(tmp_path):
    medida = tmp_path / "m.jsonl"
    medida.write_text(json.dumps({"dialogo": "d", "metricas": [{"llm_calls": 5, "latency": 2.5}]}), encoding="utf-8")
    assert cx.de_la_ronda(str(medida))["llamadas_por_turno"] == 5
