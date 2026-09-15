"""
Fase 5 · Separacion segura entre desarrollo y produccion.

El .env local apuntaba a la PostgreSQL de produccion: abrir el proyecto en
local leia y escribia contra Render sin avisar. Ahora development usa SQLite por
defecto y conectar a una base remota exige autorizacion explicita.

Cada caso se ejecuta en un SUBPROCESO limpio con load_dotenv neutralizado:
settings valida en tiempo de importacion y un modulo solo se importa una vez.
Ninguna prueba se conecta a ninguna base de datos.
"""
import os
import pathlib
import subprocess
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]

PLANTILLA = """
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import os
{env}
import backend.config.settings as s
print("IMPORT_OK")
{extra}
"""

# URL sintetica: host inexistente, credenciales de mentira. Nunca se conecta.
BD_REMOTA = "postgresql://usuario:clave@bd.ejemplo-inexistente.invalid:5432/x"
BD_LOCAL = "sqlite:///./backend/app.db"


def importar(variables, extra=""):
    """Importa settings en un subproceso con el entorno indicado."""
    entorno = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_URL", "APP_ENV", "TRADING_MODE",
                            "ALLOW_LIVE_TRADING", "MAX_DAILY_LOSS_USDT",
                            "MAX_DAILY_LOSS", "INITIAL_CAPITAL_USD", "WAIT_TIME",
                            "OPENAI_MODEL", "ACCESS_TOKEN_EXPIRE_MINUTES",
                            "PERMITIR_BD_REMOTA_EN_DESARROLLO", "CORS_ORIGINS")}
    entorno["PYTHONPATH"] = str(RAIZ)
    entorno.setdefault("SECRET_KEY", "clave-de-prueba-no-es-un-secreto-real")
    lineas = "\n".join(f"os.environ[{k!r}] = {v!r}" for k, v in variables.items())
    r = subprocess.run(
        [sys.executable, "-c", PLANTILLA.format(env=lineas, extra=extra)],
        cwd=str(RAIZ), env=entorno, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)
    return r.returncode, r.stdout or "", r.stderr or ""


# ── development ─────────────────────────────────────────────────────────────
def test_development_con_sqlite_arranca():
    code, out, err = importar({"APP_ENV": "development", "DATABASE_URL": BD_LOCAL})
    assert code == 0, err
    assert "IMPORT_OK" in out


def test_development_sin_database_url_usa_sqlite_local():
    code, out, _ = importar({"APP_ENV": "development"},
                            extra="print('URL_SQLITE', s.DATABASE_URL.startswith('sqlite'))")
    assert code == 0
    assert "URL_SQLITE True" in out, "sin DATABASE_URL debe caer a la SQLite local"


def test_development_con_bd_remota_falla_seguro():
    code, out, err = importar({"APP_ENV": "development", "DATABASE_URL": BD_REMOTA})
    assert code != 0, "abrir el proyecto en local no debe conectar a produccion"
    assert "IMPORT_OK" not in out
    assert "REMOTA" in err and "PERMITIR_BD_REMOTA_EN_DESARROLLO" in err


def test_development_con_bd_remota_autorizada_si_arranca():
    code, out, err = importar({"APP_ENV": "development", "DATABASE_URL": BD_REMOTA,
                               "PERMITIR_BD_REMOTA_EN_DESARROLLO": "true"})
    assert code == 0, err
    assert "IMPORT_OK" in out


def test_la_deteccion_de_remoto_es_generica():
    """No se detecta produccion buscando el nombre de un proveedor concreto."""
    from backend.config.settings import es_url_remota
    assert es_url_remota("postgresql://u:p@cualquier-host.desconocido/x") is True
    assert es_url_remota("postgresql://u:p@10.20.30.40:5432/x") is True
    assert es_url_remota("postgresql://u:p@localhost:5432/x") is False
    assert es_url_remota("postgresql://u:p@127.0.0.1/x") is False
    assert es_url_remota("sqlite:///./backend/app.db") is False
    assert es_url_remota("") is False

    fuente = (RAIZ / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    for proveedor in ("render", "amazonaws", "heroku", "supabase", "neon"):
        assert proveedor not in fuente.lower(), \
            f"la proteccion no debe depender del proveedor {proveedor!r}"


# ── production ──────────────────────────────────────────────────────────────
def test_production_sin_database_url_falla():
    code, out, err = importar({"APP_ENV": "production"})
    assert code != 0
    assert "IMPORT_OK" not in out
    assert "DATABASE_URL" in err


def test_production_con_database_url_arranca():
    code, out, err = importar({
        "APP_ENV": "production",
        "DATABASE_URL": BD_REMOTA,
        "CORS_ORIGINS": "https://frontend.test.invalid",
    })
    assert code == 0, err
    assert "IMPORT_OK" in out


def test_production_sin_cors_origins_falla_seguro():
    code, out, err = importar({
        "APP_ENV": "production",
        "DATABASE_URL": BD_REMOTA,
    })
    assert code != 0
    assert "IMPORT_OK" not in out
    assert "CORS_ORIGINS" in err


def test_cors_wildcard_se_rechaza():
    code, out, err = importar({
        "APP_ENV": "production",
        "DATABASE_URL": BD_REMOTA,
        "CORS_ORIGINS": "*",
    })
    assert code != 0
    assert "IMPORT_OK" not in out
    assert "CORS_ORIGINS" in err and "no admite *" in err


def test_cors_multiples_origenes_se_parsean():
    code, out, err = importar({
        "APP_ENV": "production",
        "DATABASE_URL": BD_REMOTA,
        "CORS_ORIGINS": "https://uno.test.invalid, https://dos.test.invalid",
    }, extra="print('CORS', s.CORS_ORIGINS)")
    assert code == 0, err
    assert "https://uno.test.invalid" in out
    assert "https://dos.test.invalid" in out


def test_app_env_invalido_falla():
    code, _, err = importar({"APP_ENV": "produccion-typo", "DATABASE_URL": BD_LOCAL})
    assert code != 0 and "APP_ENV" in err


# ── Variables que antes se ignoraban ────────────────────────────────────────
def test_initial_capital_se_lee_del_entorno():
    code, out, _ = importar({"APP_ENV": "development", "INITIAL_CAPITAL_USD": "137.5"},
                            extra="print('CAP', s.INITIAL_CAPITAL_USD)")
    assert code == 0 and "CAP 137.5" in out


def test_wait_time_se_lee_del_entorno():
    code, out, _ = importar({"APP_ENV": "development", "WAIT_TIME": "300"},
                            extra="print('WT', s.WAIT_TIME)")
    assert code == 0 and "WT 300" in out


def test_openai_model_se_lee_del_entorno():
    code, out, _ = importar({"APP_ENV": "development", "OPENAI_MODEL": "modelo-de-prueba"},
                            extra="print('MODELO', s.OPENAI_MODEL)")
    assert code == 0 and "MODELO modelo-de-prueba" in out


def test_openai_model_no_esta_hardcodeado():
    import ast
    fuente = (RAIZ / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign)
                and any(getattr(t, "id", None) == "OPENAI_MODEL" for t in nodo.targets)):
            assert isinstance(nodo.value, ast.Call) or isinstance(nodo.value, ast.BoolOp), \
                "OPENAI_MODEL debe leerse del entorno, no ser un literal"


# ── Validacion de valores ───────────────────────────────────────────────────
@pytest.mark.parametrize("variable,valor", [
    ("INITIAL_CAPITAL_USD", "-5"),
    ("INITIAL_CAPITAL_USD", "nan"),
    ("INITIAL_CAPITAL_USD", "inf"),
    ("INITIAL_CAPITAL_USD", "no-es-numero"),
    ("WAIT_TIME", "0"),
    ("WAIT_TIME", "-100"),
    ("WAIT_TIME", "nan"),
    ("WAIT_TIME", "99999999"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", "0"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", "-1"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", "99999"),
    ("MAX_DAILY_LOSS_USDT", "-1"),
    ("MAX_DAILY_LOSS_USDT", "inf"),
])
def test_valores_invalidos_se_rechazan(variable, valor):
    code, out, _ = importar({"APP_ENV": "development", variable: valor})
    assert code != 0, f"{variable}={valor!r} deberia rechazarse"
    assert "IMPORT_OK" not in out


# ── MAX_DAILY_LOSS_USDT segun modo ──────────────────────────────────────────
def test_live_sin_max_daily_loss_falla():
    code, out, err = importar({
        "APP_ENV": "development", "TRADING_MODE": "LIVE",
        "ALLOW_LIVE_TRADING": "yes-i-understand-the-risk"})
    assert code != 0, "LIVE sin limite de perdida diaria no debe arrancar"
    assert "MAX_DAILY_LOSS_USDT" in err and "obligatoria" in err.lower()


def test_live_con_max_daily_loss_arranca():
    code, out, err = importar({
        "APP_ENV": "development", "TRADING_MODE": "LIVE",
        "ALLOW_LIVE_TRADING": "yes-i-understand-the-risk",
        "MAX_DAILY_LOSS_USDT": "25"},
        extra="print('MODO', s.TRADING_MODE, s.MODO_REAL, s.MAX_DAILY_LOSS_USDT)")
    assert code == 0, err
    assert "MODO LIVE True 25.0" in out


def test_paper_sin_max_daily_loss_usa_el_default():
    code, out, _ = importar({"APP_ENV": "development"},
                            extra="print('MDL', s.MAX_DAILY_LOSS_USDT, s.MODO_REAL)")
    assert code == 0 and "MDL 20.0 False" in out


def test_max_daily_loss_antiguo_es_obsoleto_y_no_se_aliasa():
    code, out, _ = importar({"APP_ENV": "development", "MAX_DAILY_LOSS": "0.05"},
                            extra="print('MDL', s.MAX_DAILY_LOSS_USDT)")
    assert code == 0
    assert "MDL 20.0" in out, "0.05 jamas debe interpretarse como el limite"
    assert "OBSOLETA" in out


# ── Secretos ────────────────────────────────────────────────────────────────
def test_sin_secret_key_falla_seguro():
    entorno = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    entorno["PYTHONPATH"] = str(RAIZ)
    r = subprocess.run(
        [sys.executable, "-c", PLANTILLA.format(
            env="os.environ.pop('SECRET_KEY', None)\nos.environ['APP_ENV']='development'",
            extra="")],
        cwd=str(RAIZ), env=entorno, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode != 0 and "SECRET_KEY" in (r.stderr or "")


def test_ninguna_credencial_tiene_fallback():
    """Las claves de API pueden faltar en PAPER, pero jamas tener valor conocido."""
    import ast
    arbol = ast.parse((RAIZ / "backend" / "config" / "settings.py").read_text(encoding="utf-8"))
    sensibles = ("KEY", "SECRET", "TOKEN", "PASSWORD")
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", None) == "getenv"):
            continue
        if not (nodo.args and isinstance(nodo.args[0], ast.Constant)):
            continue
        nombre = nodo.args[0].value
        if any(t in nombre for t in sensibles) and len(nodo.args) > 1:
            assert False, f"{nombre} no puede tener valor por defecto"


# Nombres que contienen una palabra "sensible" pero NO son credenciales.
# Se listan explicitamente para que el heuristico no de falsos positivos y, a
# la vez, no se relaje para cualquier variable.
NO_SON_SECRETOS = {
    "ACCESS_TOKEN_EXPIRE_MINUTES",   # duracion en minutos
    "SECRET_KEY_ROTATION_DAYS",      # reservado; duracion, no clave
}


def test_env_example_no_contiene_secretos_ni_url_de_produccion():
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for linea in texto.splitlines():
        if linea.strip().startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        if clave in NO_SON_SECRETOS:
            continue
        if any(t in clave for t in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            assert valor.strip() == "", f"{clave} debe estar vacia en la plantilla"
    assert "postgresql://" not in texto, "la plantilla no puede traer una URL real"
    assert texto.count("DATABASE_URL=") == 1
    assert "DATABASE_URL=sqlite" in texto


# ── Fuente canonica de configuracion ────────────────────────────────────────
def test_solo_settings_carga_el_entorno():
    """Un unico modulo interpreta las variables; sin fuentes divergentes."""
    ofensores = []
    for archivo in list((RAIZ / "backend").rglob("*.py")):
        if "__pycache__" in archivo.parts:
            continue
        if archivo.name == "settings.py":
            continue
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        if "load_dotenv()" in texto:
            ofensores.append(str(archivo.relative_to(RAIZ)))
    assert not ofensores, f"solo settings.py debe cargar el .env: {ofensores}"


def test_el_modulo_de_configuracion_duplicado_ya_no_existe():
    assert not (RAIZ / "backend" / "app" / "config.py").exists(), (
        "backend/app/config.py declaraba ACCESS_TOKEN_EXPIRE_MINUTES=30 frente a "
        "los 60 del modulo canonico: dos fuentes divergentes")
