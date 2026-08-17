"""Regresiones para la carga deterministica del .env local.

El proyecto llego a tener `/.env` y `/backend/.env` con valores distintos. Con
`load_dotenv()` sin ruta, el valor efectivo dependia del CWD/modo de arranque.
Estas pruebas NO tocan ninguno de los .env reales: copian settings.py a un
proyecto temporal y prueban alli la resolucion basada en __file__.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SETTINGS = RAIZ / "backend" / "config" / "settings.py"


def _proyecto_temporal(tmp_path: Path, *, con_env_raiz=True) -> Path:
    raiz = tmp_path / "proyecto"
    config = raiz / "backend" / "config"
    config.mkdir(parents=True)
    (raiz / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (config / "__init__.py").write_text("", encoding="utf-8")
    (config / "settings.py").write_text(SETTINGS.read_text(encoding="utf-8"),
                                        encoding="utf-8")
    if con_env_raiz:
        (raiz / ".env").write_text(
            "APP_ENV=development\n"
            "DATABASE_URL=sqlite:///./backend/app.db\n"
            "SECRET_KEY=clave-local-sintetica-de-prueba-123456789\n"
            "INITIAL_CAPITAL_USD=500\n",
            encoding="utf-8",
        )
    # El fichero conflictivo reproduce exactamente el hallazgo de 03B. Debe
    # ser irrelevante aunque el proceso arranque con CWD=backend.
    (raiz / "backend" / ".env").write_text(
        "SECRET_KEY=otra-clave-sintetica-que-no-debe-ganar\n"
        "INITIAL_CAPITAL_USD=20\n",
        encoding="utf-8",
    )
    return raiz


def _entorno_limpio(fuente: str):
    entorno = dict(os.environ)
    # Elimina toda variable que settings pueda leer para que la prueba mida
    # exclusivamente el .env temporal. Se conserva el resto del entorno de SO
    # (importante en Windows para localizar DLLs y el runtime de Python).
    nombres = set(re.findall(r"os\.getenv\(['\"]([^'\"]+)", fuente))
    nombres.update({"RISK_PER_TRADE"})
    for nombre in nombres:
        entorno.pop(nombre, None)
    return entorno


def _importar(raiz: Path, cwd: Path, *, extra_env=None):
    fuente = (raiz / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    entorno = _entorno_limpio(fuente)
    entorno["PYTHONPATH"] = str(raiz)
    entorno.update(extra_env or {})
    programa = (
        "import backend.config.settings as s\n"
        "print('CAP', s.INITIAL_CAPITAL_USD)\n"
        "print('ENV', s.ENV_LOCAL_CANONICO.resolve())\n"
    )
    return subprocess.run(
        [sys.executable, "-c", programa], cwd=str(cwd), env=entorno,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )


@pytest.mark.parametrize("cwd_rel", [".", "backend", "otro/directorio"])
def test_mismo_env_canonico_desde_cualquier_cwd(tmp_path, cwd_rel):
    raiz = _proyecto_temporal(tmp_path)
    cwd = raiz / cwd_rel
    cwd.mkdir(parents=True, exist_ok=True)

    r = _importar(raiz, cwd)

    assert r.returncode == 0, r.stderr
    assert "CAP 500.0" in r.stdout
    assert f"ENV {(raiz / '.env').resolve()}" in r.stdout
    assert "CAP 20.0" not in r.stdout, "backend/.env no puede ganar por CWD"


def test_variable_real_del_entorno_gana_sobre_env_local(tmp_path):
    raiz = _proyecto_temporal(tmp_path)

    r = _importar(raiz, raiz / "backend",
                  extra_env={"INITIAL_CAPITAL_USD": "700"})

    assert r.returncode == 0, r.stderr
    assert "CAP 700.0" in r.stdout, "override=False debe preservar el entorno real"


def test_produccion_no_necesita_archivo_env(tmp_path):
    raiz = _proyecto_temporal(tmp_path, con_env_raiz=False)
    # Eliminamos tambien el backend/.env conflictivo: simula un artefacto de
    # despliegue limpio, configurado solo por variables reales del servicio.
    (raiz / "backend" / ".env").unlink()
    extra = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://u:p@host-produccion.invalid:5432/x",
        "SECRET_KEY": "clave-produccion-sintetica-solo-para-prueba-123456789",
        "INITIAL_CAPITAL_USD": "321",
    }

    r = _importar(raiz, raiz, extra_env=extra)

    assert r.returncode == 0, r.stderr
    assert "CAP 321.0" in r.stdout


def test_settings_declara_ruta_explicita_y_no_usa_find_dotenv():
    fuente = SETTINGS.read_text(encoding="utf-8")
    assert "ENV_LOCAL_CANONICO" in fuente
    assert "dotenv_path=ENV_LOCAL_CANONICO" in fuente
    assert "override=False" in fuente
    assert "find_dotenv" not in fuente
    assert "load_dotenv()" not in fuente
