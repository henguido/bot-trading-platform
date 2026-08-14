"""
P0-9 · La configuracion debe fallar de forma segura si no hay SECRET_KEY valida.

Una clave de firma conocida (el antiguo fallback 'dev-secret-key') permitiria a
cualquiera emitir tokens validos, anulando toda la proteccion de P0-3.

Cada caso se ejecuta en un SUBPROCESO limpio, porque `backend.config.settings`
valida en tiempo de importacion y un modulo solo se importa una vez por proceso.
En el subproceso se neutraliza `load_dotenv` para que el `.env` real no
reintroduzca la variable. Ninguna prueba contacta con servicios externos.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Neutraliza load_dotenv ANTES de que settings lo llame, fija el valor a probar
# e importa settings. Imprime el resultado por stdout.
PLANTILLA = """
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import os
{asignacion}
import backend.config.settings as s
print("IMPORT_OK")
"""


def _ejecutar(asignacion, secret_env=None):
    """Importa settings en un subproceso limpio. Devuelve (returncode, stdout, stderr)."""
    entorno = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    entorno["PYTHONPATH"] = str(RAIZ)
    entorno["TRADING_MODE"] = "PAPER"
    entorno.pop("ALLOW_LIVE_TRADING", None)
    if secret_env is not None:
        entorno["SECRET_KEY"] = secret_env

    r = subprocess.run(
        [sys.executable, "-c", PLANTILLA.format(asignacion=asignacion)],
        cwd=str(RAIZ), env=entorno, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    return r.returncode, r.stdout or "", r.stderr or ""


# ── SECRET presente -> configuracion valida ──────────────────────────────────
def test_con_secret_valida_la_configuracion_carga():
    code, out, err = _ejecutar("pass", secret_env="una-clave-aleatoria-de-pruebas-suficientemente-larga")
    assert code == 0, f"deberia importar sin error. stderr:\n{err}"
    assert "IMPORT_OK" in out


# ── SECRET ausente -> fallo explicito ────────────────────────────────────────
def test_sin_secret_la_configuracion_falla():
    code, out, err = _ejecutar("os.environ.pop('SECRET_KEY', None)")
    assert code != 0, "sin SECRET_KEY la aplicacion NO debe arrancar"
    assert "IMPORT_OK" not in out
    assert "SECRET_KEY" in err and "RuntimeError" in err, f"fallo poco explicito:\n{err}"


def test_secret_vacia_o_en_blanco_falla():
    for valor in ("", "   "):
        code, out, err = _ejecutar("pass", secret_env=valor)
        assert code != 0, f"SECRET_KEY={valor!r} deberia ser rechazada"
        assert "IMPORT_OK" not in out


# ── Valores de ejemplo conocidos -> rechazados ───────────────────────────────
def test_valores_de_ejemplo_conocidos_son_rechazados():
    for valor in ("dev-secret-key", "supersecret", "changeme", "SECRET"):
        code, out, err = _ejecutar("pass", secret_env=valor)
        assert code != 0, f"SECRET_KEY={valor!r} es publicamente conocida y debe rechazarse"
        assert "IMPORT_OK" not in out


# ── No queda ningun fallback en el codigo ────────────────────────────────────
def test_no_existe_fallback_hardcodeado_en_el_codigo():
    """Ningun getenv de SECRET_KEY puede tener segundo argumento."""
    import re
    ofensores = []
    for archivo in RAIZ.rglob("*.py"):
        if "node_modules" in archivo.parts or "__pycache__" in archivo.parts:
            continue
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"getenv\(\s*['\"]SECRET_KEY['\"]\s*,", texto):
            ofensores.append(f"{archivo.relative_to(RAIZ)}: getenv con valor por defecto")
    assert not ofensores, "SECRET_KEY no debe tener fallback:\n" + "\n".join(ofensores)


def test_las_claves_de_ejemplo_no_aparecen_como_literal_de_codigo():
    """
    'dev-secret-key' y 'supersecret' no pueden existir como cadena en el codigo.
    Se analiza el AST, de modo que los comentarios que las mencionan al
    documentar su eliminacion no cuentan: solo importan los literales reales.
    Unica excepcion: la lista _CLAVES_PROHIBIDAS que las rechaza.
    """
    import ast
    conocidas = {"dev-secret-key", "supersecret"}
    ofensores = []
    for archivo in RAIZ.rglob("*.py"):
        if "node_modules" in archivo.parts or "__pycache__" in archivo.parts or archivo.parent.name == "tests":
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8", errors="replace"))
        permitido = any(
            isinstance(n, ast.Name) and n.id == "_CLAVES_PROHIBIDAS"
            for n in ast.walk(arbol)
        )
        if permitido:
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and nodo.value in conocidas:
                ofensores.append(f"{archivo.relative_to(RAIZ)}:{nodo.lineno} -> {nodo.value!r}")
    assert not ofensores, "clave de ejemplo usada como literal en el codigo:\n" + "\n".join(ofensores)


# ── .env.example solo contiene placeholder ───────────────────────────────────
def test_env_example_solo_tiene_placeholder():
    lineas = Path(RAIZ, ".env.example").read_text(encoding="utf-8").splitlines()
    asignaciones = [l for l in lineas if l.startswith("SECRET_KEY")]
    assert asignaciones == ["SECRET_KEY="], f"debe estar vacia, se encontro: {asignaciones}"


def test_env_example_no_contiene_secretos():
    """Ningun valor sensible: las claves de API deben estar vacias."""
    texto = Path(RAIZ, ".env.example").read_text(encoding="utf-8")
    for linea in texto.splitlines():
        if linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        if any(t in clave for t in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            assert valor.strip() == "", f"{clave} deberia estar vacia en la plantilla"


# ── Ningun secreto se imprime ────────────────────────────────────────────────
def test_la_configuracion_no_imprime_la_clave():
    centinela = "CENTINELA-NO-DEBE-APARECER-EN-NINGUNA-SALIDA-12345"
    code, out, err = _ejecutar("pass", secret_env=centinela)
    assert code == 0
    assert centinela not in out, "la SECRET_KEY aparecio en stdout"
    assert centinela not in err, "la SECRET_KEY aparecio en stderr"
