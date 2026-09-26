"""r6-3: `scripts/check_deploy.py` comprueba que un push a `pre_*` SÍ se desplegó.

Por qué existe: un CI rojo se salta el deploy sin avisar, y del 24-sep 23:04 al 25-sep 21:30 PRE sirvió
código viejo sin que nadie lo viera (HISTORY 0.29.27). Aquí se fija, sin red ni SSH:

1. qué se compara: lo que el compose fija para `dp-pre-bot`, sin contraseñas ni URLs;
2. cómo se compara (booleanos, números con tolerancia, ajuste que falta);
3. que el run de GitHub se encuentra por el SHA corto y que un CI rojo da error con el paso que falla;
4. que el camino completo sale bien solo cuando PRE sirve ese commit, esa rama, healthy y con los
   mismos ajustes;
5. que el acceso a PRE es uno solo (`scripts/pre_access.py`) y respeta `PRE_SSH_KEY` / `PRE_SSH_HOST`.
"""

import subprocess

import pytest

from scripts import check_deploy as cd
from scripts import pre_access


def test_el_compose_da_interruptores_y_modelos_sin_contrasenas_ni_urls():
    esperado = cd.expected_from_compose()
    assert "database_url" not in esperado and "redis_url" not in esperado
    for modelo in ("openai_model", "rag_answer_model", "extraction_model", "jev_model"):
        assert modelo in esperado
    assert isinstance(esperado["rag_min_score"], float)
    assert isinstance(esperado["agent_arch"], bool)
    assert all(isinstance(v, (bool, int, float, str)) for v in esperado.values())


@pytest.mark.parametrize(
    ("crudo", "valor"),
    [("true", True), ("FALSE", False), ("0.40", 0.4), ("8", 8), ("gpt-4o-mini", "gpt-4o-mini"), ("staging", "staging")],
)
def test_as_setting_convierte_como_pydantic(crudo, valor):
    assert cd.as_setting(crudo) == valor
    assert type(cd.as_setting(crudo)) is type(valor)


def test_compare_detecta_lo_distinto_y_lo_que_falta():
    esperado = {"answer_and_continue": True, "rag_min_score": 0.4, "openai_model": "gpt-4o-mini", "nuevo": 1}
    en_pre = {"answer_and_continue": False, "rag_min_score": 0.4000000000001, "openai_model": "gpt-4o-mini"}
    diffs = cd.compare(esperado, en_pre)
    assert any(d.startswith("answer_and_continue:") for d in diffs)
    assert any(d.startswith("nuevo:") for d in diffs)
    assert not any(d.startswith("rag_min_score") for d in diffs), "un float igual no es una diferencia"
    assert not any(d.startswith("openai_model") for d in diffs)
    assert cd.compare({"a": True}, {"a": True}) == []


def test_find_run_por_sha_corto_y_el_mas_reciente():
    runs = [{"head_sha": "a8d731d0000", "id": 2}, {"head_sha": "a8d731d0000", "id": 1}, {"head_sha": "c0773a2ffff", "id": 0}]
    assert cd.find_run(runs, "a8d731d")["id"] == 2
    assert cd.find_run(runs, "deadbee") is None


@pytest.mark.parametrize(
    "url",
    ["https://github.com/adminiscore/diving-planet-bot.git", "https://github.com/adminiscore/diving-planet-bot",
     "git@github.com:adminiscore/diving-planet-bot.git\n"],
)
def test_slug_de_la_url_del_remoto(url):
    assert cd.slug_from_url(url) == "adminiscore/diving-planet-bot"


def test_slug_de_un_remoto_que_no_es_github_para():
    with pytest.raises(SystemExit):
        cd.slug_from_url("https://gitlab.com/x/y.git")


def _preparar(monkeypatch, run, estado_pre, jobs=None):
    monkeypatch.setattr(cd, "repo_slug", lambda: "o/r")
    monkeypatch.setattr(cd, "_git", lambda *a: "feature/pre_alvaro" if "--abbrev-ref" in a else "a8d731dfull")

    def fake_get(slug, path):
        return {"jobs": jobs or []} if "/jobs" in path else {"workflow_runs": [run]}

    monkeypatch.setattr(cd, "_get", fake_get)
    monkeypatch.setattr(cd, "pre_state", lambda keys: estado_pre)
    monkeypatch.setattr(cd, "expected_from_compose", lambda: {"answer_and_continue": True, "openai_model": "gpt-4o-mini"})


RUN_OK = {"head_sha": "a8d731dfull", "status": "completed", "conclusion": "success", "html_url": "u", "id": 1}
PRE_OK = {"sha": "a8d731dfull", "branch": "feature/pre_alvaro", "health": "healthy",
          "settings": {"answer_and_continue": True, "openai_model": "gpt-4o-mini"}}


def test_todo_bien_sale_0(monkeypatch, capsys):
    _preparar(monkeypatch, RUN_OK, PRE_OK)
    assert cd.main(["--no-wait"]) == 0
    assert "coinciden en PRE" in capsys.readouterr().out


def test_ci_rojo_sale_1_y_dice_el_paso_que_falla(monkeypatch, capsys):
    rojo = {**RUN_OK, "conclusion": "failure"}
    jobs = [{"name": "Lint + Tests", "steps": [{"name": "Run DB migrations", "conclusion": "failure"},
                                              {"name": "Checkout", "conclusion": "success"}]}]
    _preparar(monkeypatch, rojo, PRE_OK, jobs)
    assert cd.main(["--no-wait"]) == 1
    salida = capsys.readouterr().out
    assert "el deploy NO se hizo" in salida and "Run DB migrations" in salida and "Checkout" not in salida


def test_pre_con_otro_ajuste_que_el_repo_sale_1(monkeypatch, capsys):
    _preparar(monkeypatch, RUN_OK, {**PRE_OK, "settings": {"answer_and_continue": False, "openai_model": "gpt-4o-mini"}})
    assert cd.main(["--no-wait"]) == 1
    assert "answer_and_continue" in capsys.readouterr().out


def test_pre_en_otra_rama_sale_1(monkeypatch):
    _preparar(monkeypatch, RUN_OK, {**PRE_OK, "branch": "feature/pre_gadea"})
    assert cd.main(["--no-wait"]) == 1


def test_pre_todavia_con_el_commit_anterior_sin_esperar_sale_2(monkeypatch):
    _preparar(monkeypatch, RUN_OK, {**PRE_OK, "sha": "c0773a2full"})
    assert cd.main(["--no-wait"]) == 2


def test_un_solo_acceso_ssh_con_clave_y_host_configurables(monkeypatch):
    visto = {}

    def fake_run(args, **kwargs):
        visto["args"], visto["input"] = args, kwargs.get("input")
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(pre_access.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_SSH_KEY", "/tmp/clave")
    monkeypatch.setenv("PRE_SSH_HOST", "root@1.2.3.4")
    pre_access.pre_ssh("echo hola", input_text="x")
    assert visto["args"][:3] == ["ssh", "-i", "/tmp/clave"]
    assert "BatchMode=yes" in visto["args"] and "root@1.2.3.4" in visto["args"]
    assert visto["args"][-1] == "echo hola" and visto["input"] == "x"
