"""r6-1(c): la comprobación horaria del saldo de OpenAI de PRE (`scripts/vigilar_saldo_openai.py`).

Se fija: sin saldo / clave inválida / caída = alarma (sale con 2); un 429 de ritmo se reintenta y no es alarma si luego
contesta; sin la identidad `vigilante` de Coral no se escribe en el chat (queda el correo de GitHub); nunca se imprime
el token.
"""

import pytest

from scripts import vigilar_saldo_openai as v


class _FalloError(Exception):
    def __init__(self, status_code, body=""):
        super().__init__(body)
        self.status_code = status_code
        self.body = body


def _cliente(*resultados):
    pendientes = list(resultados)

    class _C:
        def create(self, **kw):
            r = pendientes.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


@pytest.mark.parametrize("exc, alarma", [
    (_FalloError(429, "{'code': 'insufficient_quota'}"), True),
    (_FalloError(429, "rate limit reached"), False),
    (_FalloError(401, "invalid key"), True),
    (_FalloError(503, "unavailable"), True),
])
def test_clasificar(exc, alarma):
    assert v.clasificar(exc)[1] is alarma


def test_la_llamada_no_usa_max_tokens():
    """mej-5: gpt-5.4-nano rechaza `max_tokens` (400): la comprobación fallaba siempre y la alarma no distinguía la falta
    de saldo. Va `max_completion_tokens`."""
    llamadas = []

    class _C:
        def create(self, **kw):
            llamadas.append(kw)
            return object()

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    assert v.comprobar(cliente, pausa=0) == (True, "OpenAI contesta")
    assert "max_tokens" not in llamadas[0] and llamadas[0]["max_completion_tokens"] >= 16


def test_sin_saldo_no_se_reintenta():
    ok, motivo = v.comprobar(_cliente(_FalloError(429, "insufficient_quota")), pausa=0)
    assert not ok and "sin saldo" in motivo


def test_un_429_de_ritmo_y_luego_contesta_es_ok():
    ok, _ = v.comprobar(_cliente(_FalloError(429, "rate limit"), "respuesta"), pausa=0)
    assert ok


def test_caido_tras_los_reintentos_es_alarma():
    ok, motivo = v.comprobar(_cliente(*[_FalloError(503, "down")] * v.REINTENTOS), pausa=0)
    assert not ok and "503" in motivo


def test_sin_identidad_vigilante_no_escribe_en_coral(monkeypatch):
    monkeypatch.delenv("CORAL_TOKEN_VIGILANTE", raising=False)
    monkeypatch.setenv("CORAL_URL", "https://pre.is-core.dev/coral")
    assert "solo el correo" in v.avisar_en_coral("sin saldo")


def test_main_sale_con_2_y_no_imprime_el_token(monkeypatch, capsys):
    monkeypatch.setattr(v, "comprobar", lambda: (False, "sin saldo (429 insufficient_quota)"))
    monkeypatch.setattr(v, "avisar_en_coral", lambda motivo: "aviso en Coral (200)")
    monkeypatch.setenv("CORAL_TOKEN_VIGILANTE", "tok-secreto-123")
    assert v.main(["--coral"]) == 2
    salida = capsys.readouterr().out
    assert "ALERTA" in salida and "tok-secreto-123" not in salida
