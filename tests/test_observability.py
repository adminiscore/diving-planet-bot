"""Observabilidad Langfuse (Fase 5.3 / tarea 8): la máscara de PII y que sin
claves todo es no-op y `langfuse` NO se importa (3.14-safe)."""

import asyncio
import sys
import types

import pytest

from src import observability as obs


def _settings(**over):
    s = types.SimpleNamespace(
        langfuse_public_key="", langfuse_secret_key="",
        langfuse_host="https://cloud.langfuse.com", app_env="test",
        openai_api_key="sk-x",
    )
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── máscara de PII (lo que sale a un tercero) ──

def test_mask_redacts_strings_recursively():
    data = {
        "input": "mi correo es juan.perez@gmail.com y mi tel 3001234567",
        "nested": ["escribe a ana@x.com", {"deep": "sin pii aqui"}],
    }
    masked = obs._mask(data=data)
    flat = repr(masked)
    assert "juan.perez@gmail.com" not in flat
    assert "ana@x.com" not in flat
    assert "REDACTED" in flat
    assert "sin pii aqui" in flat  # lo que no es PII se conserva


def test_mask_never_raises():
    class Weird:
        def __repr__(self):
            raise RuntimeError("boom")
    # objeto no-str/dict/list: se devuelve tal cual, sin tocar
    assert obs._mask(data=Weird()).__class__.__name__ == "Weird"


# ── enabled / no-op sin claves ──

def test_disabled_without_keys():
    assert obs.langfuse_enabled(_settings()) is False


def test_disabled_when_env_says_false(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    assert obs.langfuse_enabled(_settings(langfuse_public_key="pk", langfuse_secret_key="sk")) is False


def test_enabled_with_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    assert obs.langfuse_enabled(_settings(langfuse_public_key="pk", langfuse_secret_key="sk")) is True


def test_no_keys_never_imports_langfuse():
    """Crítico (3.14): sin claves, ni el cliente ni el handler importan langfuse."""
    assert obs.traced_openai_client(_settings()) is None
    assert obs.langfuse_callback_handler(_settings()) is None
    assert "langfuse" not in sys.modules


# ── traza raiz por turno y resumen (m0-1) ──

class _FakeSpan:
    def __init__(self, log):
        self.log = log

    def update(self, **kw):
        self.log.append(("span.update", kw))

    def update_trace(self, **kw):
        self.log.append(("trace.update", kw))


class _FakeSpanCM:
    def __init__(self, log, kw):
        self.log, self.kw = log, kw

    def __enter__(self):
        self.log.append(("span.start", self.kw))
        return _FakeSpan(self.log)

    def __exit__(self, *exc):
        self.log.append(("span.end", None))
        return False


def _install_fake_langfuse(monkeypatch):
    """langfuse + opentelemetry falsos (los reales no importan en 3.14)."""
    log = []
    client = types.SimpleNamespace(start_as_current_span=lambda **kw: _FakeSpanCM(log, kw))
    monkeypatch.setitem(sys.modules, "langfuse", types.SimpleNamespace(get_client=lambda: client))
    ctx = types.SimpleNamespace(
        Context=lambda: "ctx-limpio",
        attach=lambda c: log.append(("otel.attach", c)) or "token",
        detach=lambda t: log.append(("otel.detach", t)),
    )
    monkeypatch.setitem(sys.modules, "opentelemetry", types.SimpleNamespace(context=ctx))
    monkeypatch.setitem(sys.modules, "opentelemetry.context", ctx)
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    return log


def test_note_turn_outside_a_turn_is_a_noop():
    obs.note_turn(route="booking")  # no rompe ni deja estado
    assert obs._TURN_FACTS.get() is None


def test_turn_summary_types():
    assert obs.turn_summary({"route": "booking", "rag_used": True}, "x")["turn_type"] == "rag"
    assert obs.turn_summary({"route": "booking", "greeting": True}, "x")["turn_type"] == "saludo"
    assert obs.turn_summary({"route": "safety"}, "x")["turn_type"] == "escalado"
    assert obs.turn_summary({"route": "changes"}, "x")["turn_type"] == "cambios"
    assert obs.turn_summary({"route": "deflection"}, "x")["turn_type"] == "deflection"
    assert obs.turn_summary({}, None)["turn_type"] == "otro"
    s = obs.turn_summary({"route": "booking"}, "reserva aqui: https://book.divingplanet.org/book/x")
    assert s["booking_link_sent"] is True and s["rag_used"] is False


def test_turn_trace_without_keys_collects_facts_and_never_imports_langfuse():
    async def run():
        async with obs.turn_trace(_settings(), "conv-1", "hola") as facts:
            obs.note_turn(route="booking")
            facts["reply"] = "ok"
        return facts

    facts = asyncio.run(run())
    assert facts == {"route": "booking", "reply": "ok"}
    assert obs._TURN_FACTS.get() is None
    assert "langfuse" not in sys.modules


def test_turn_trace_opens_clean_root_with_session_and_summary(monkeypatch):
    log = _install_fake_langfuse(monkeypatch)
    s = _settings(langfuse_public_key="pk", langfuse_secret_key="sk")

    async def run():
        async with obs.turn_trace(s, "conv-7", "cuanto cuesta?") as facts:
            obs.note_turn(route="booking", rag_used=True, language="es")
            facts["reply"] = "178 USD"

    asyncio.run(run())
    events = [e for e, _ in log]
    assert events[:2] == ["otel.attach", "span.start"]  # raiz en contexto limpio
    assert events[-2:] == ["span.end", "otel.detach"]
    assert ("trace.update", {"name": "turno", "session_id": "conv-7"}) in log
    meta = next(kw for e, kw in log if e == "trace.update" and "metadata" in kw)
    assert meta["metadata"]["turn"]["turn_type"] == "rag"
    assert "tipo:rag" in meta["tags"]


def test_turn_trace_closes_and_restores_context_when_the_turn_is_cancelled(monkeypatch):
    """Aunque el turno se corte, la traza se cierra y se restaura el contexto: el
    turno siguiente no puede heredar su id de traza (fallo visto en PRE el 2026-09-17)."""
    log = _install_fake_langfuse(monkeypatch)
    s = _settings(langfuse_public_key="pk", langfuse_secret_key="sk")

    async def run():
        async with obs.turn_trace(s, "conv-9", "hola"):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    events = [e for e, _ in log]
    assert events[-2:] == ["span.end", "otel.detach"]
    meta = next(kw for e, kw in log if e == "trace.update" and "metadata" in kw)
    assert meta["metadata"]["turn"]["error"] == "CancelledError"
    assert obs._TURN_FACTS.get() is None


def test_turn_trace_survives_a_broken_langfuse(monkeypatch):
    def boom():
        raise RuntimeError("langfuse caido")

    monkeypatch.setitem(sys.modules, "langfuse", types.SimpleNamespace(get_client=boom))
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    s = _settings(langfuse_public_key="pk", langfuse_secret_key="sk")

    async def run():
        async with obs.turn_trace(s, "c", "hola") as facts:
            facts["reply"] = "sigue"
        return facts

    assert asyncio.run(run())["reply"] == "sigue"
