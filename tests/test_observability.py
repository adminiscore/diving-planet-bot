"""Observabilidad Langfuse (Fase 5.3 / tarea 8): la máscara de PII y que sin
claves todo es no-op y `langfuse` NO se importa (3.14-safe)."""

import sys
import types

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
