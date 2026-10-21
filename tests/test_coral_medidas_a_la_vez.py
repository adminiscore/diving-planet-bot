"""Coral #787 (21-oct, propuesta de Gadea): con dos medidas `--codigo-local` a la vez desde el mismo ordenador, el
"PRE: libre" solo sale cuando termina la ÚLTIMA (antes lo publicaba la primera en terminar)."""
import os
import subprocess
import sys

from scripts import pre_access


def test_solo_cuentan_las_otras_medidas_vivas(monkeypatch, tmp_path):
    monkeypatch.setattr(pre_access, "_MARCAS_DE_MEDIDA", tmp_path)
    viva = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / str(os.getpid())).touch()  # la propia no cuenta
        (tmp_path / str(viva.pid)).touch()
        (tmp_path / "999999").touch()  # un proceso que ya no existe: su marca se limpia
        (tmp_path / "no-es-un-pid").touch()
        assert pre_access._otras_medidas_vivas() == [viva.pid]
        assert not (tmp_path / "999999").exists()
    finally:
        viva.kill()
        viva.wait()
    assert pre_access._otras_medidas_vivas() == []
