"""La memoria compartida del equipo (Coral #3686, opción A): rama `memoria` en git, `tools/coral/memoria.py` y el gancho de inicio.
Con un origin y dos copias de verdad (git local), sin red."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "coral"))
import hook  # noqa: E402
import memoria  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def copias(tmp_path, monkeypatch):
    for clave, valor in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                         "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(clave, valor)
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    a = tmp_path / "a"
    _git(tmp_path, "clone", "-q", str(origin), str(a))
    (a / "docs" / "plan").mkdir(parents=True)
    (a / "docs" / "plan" / "memoria.md").write_text("# Memoria\nv1\n", encoding="utf-8")
    (a / "docs" / "plan" / "marcador.md").write_text("| m |\n", encoding="utf-8")
    _git(a, "checkout", "-q", "-b", "memoria")
    _git(a, "add", "docs")
    _git(a, "commit", "-q", "-m", "memoria v1")
    _git(a, "push", "-q", "origin", "memoria")
    _git(a, "checkout", "-q", "-b", "trabajo")  # cada uno trabaja en su rama, no en la de la memoria
    b = tmp_path / "b"
    _git(tmp_path, "clone", "-q", str(origin), str(b))
    return a, b, tmp_path


def test_cada_uno_lee_la_ultima_de_origin_sin_cambiar_de_rama(copias):
    a, b, _ = copias
    assert memoria.leer("memoria", a) == "# Memoria\nv1\n"
    assert memoria.leer("memoria", b) == "# Memoria\nv1\n"
    assert subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=a, capture_output=True, text=True).stdout.strip() == "trabajo"


def test_publicar_la_sube_y_el_otro_la_ve(copias):
    a, b, tmp = copias
    memoria.leer("memoria", b)
    nueva = tmp / "copia.md"
    nueva.write_text("# Memoria\nv2\n", encoding="utf-8")
    memoria.publicar(nueva, "memoria", "v2", b)
    assert memoria.leer("memoria", a) == "# Memoria\nv2\n"


def test_no_pisa_el_cambio_de_otro(copias):
    a, b, tmp = copias
    memoria.leer("memoria", a)
    memoria.leer("memoria", b)
    (tmp / "b.md").write_text("# Memoria\nde b\n", encoding="utf-8")
    memoria.publicar(tmp / "b.md", "memoria", "b", b)
    (tmp / "a.md").write_text("# Memoria\nde a\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="vuelve a verla"):
        memoria.publicar(tmp / "a.md", "memoria", "a", a)  # a no ha visto lo de b
    memoria.leer("memoria", a)
    memoria.publicar(tmp / "a.md", "memoria", "a", a)
    assert memoria.leer("memoria", b) == "# Memoria\nde a\n"


def test_el_marcador_va_aparte(copias):
    a, _, tmp = copias
    memoria.leer("marcador", a)
    (tmp / "m.md").write_text("| m |\n| 9-nov |\n", encoding="utf-8")
    memoria.publicar(tmp / "m.md", "marcador", "línea", a)
    assert memoria.leer("marcador", a).endswith("| 9-nov |\n") and memoria.leer("memoria", a) == "# Memoria\nv1\n"


def test_el_gancho_de_inicio_la_muestra(copias, monkeypatch, capsys):
    a, _, _ = copias
    monkeypatch.setattr(hook.cliente, "configurado", lambda: False)  # sin Coral, la memoria sale igual
    hook.inicio({"cwd": str(a)})
    salida = capsys.readouterr().out
    assert "[Memoria del equipo]" in salida and "v1" in salida


def test_sin_la_rama_el_gancho_no_dice_nada_de_la_memoria(tmp_path, monkeypatch, capsys):
    _git(tmp_path, "init", "-q", str(tmp_path / "solo"))
    monkeypatch.setattr(hook.cliente, "configurado", lambda: False)
    hook.inicio({"cwd": str(tmp_path / "solo")})
    assert "[Memoria del equipo]" not in capsys.readouterr().out
