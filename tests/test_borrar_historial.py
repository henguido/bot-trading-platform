"""
P0-7 · La herramienta de borrado de base de datos debe ser inofensiva por defecto.

Ninguna prueba ejecuta drop_all() de verdad: se inyecta un `ejecutor` falso que
solo registra si fue invocado. Tampoco se usa la DATABASE_URL del .env: todas
las URLs son sinteticas.
"""
import importlib
import sys

import pytest

import borrar_historial as bh

URL_LOCAL = "sqlite:///./backend/app.db"
URL_PRODUCCION = "postgresql://usuario:contrasena@dpg-abc123.oregon-postgres.render.com/bot_db"
URL_LOCALHOST = "postgresql://usuario:contrasena@localhost:5432/bot_db"


class EjecutorEspia:
    """Sustituto del borrado real. Solo anota si alguien lo llamo."""
    def __init__(self):
        self.invocado = False

    def __call__(self):
        self.invocado = True


# ── 1 · Importar el modulo no borra nada ─────────────────────────────────────
def test_importar_el_modulo_no_ejecuta_nada():
    """Antes, importarlo lanzaba drop_all() de inmediato."""
    llamadas = []
    original = bh._reset_real
    bh._reset_real = lambda: llamadas.append("BORRADO")
    try:
        sys.modules.pop("borrar_historial", None)
        importlib.import_module("borrar_historial")
    finally:
        bh._reset_real = original
    assert llamadas == [], "importar el modulo no debe ejecutar ninguna accion destructiva"


def test_el_modulo_tiene_guarda_main():
    import ast, pathlib
    fuente = pathlib.Path(bh.__file__).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    tiene_guarda = any(
        isinstance(n, ast.If) and ast.dump(n.test).find("__main__") != -1
        for n in arbol.body
    )
    assert tiene_guarda, "el script debe protegerse con if __name__ == '__main__'"

    # Ninguna SENTENCIA EJECUTABLE a nivel de modulo puede llamar a drop_all.
    # Las definiciones de funcion no cuentan: su cuerpo no corre al importar.
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Import, ast.ImportFrom)):
            continue
        if isinstance(nodo, ast.If) and "__main__" in ast.dump(nodo.test):
            continue  # solo se ejecuta como script, no como import
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant) \
                and isinstance(nodo.value.value, str):
            continue  # docstring: texto, no codigo ejecutable
        assert "drop_all" not in ast.dump(nodo), (
            "drop_all no puede ejecutarse al importar el modulo"
        )


# ── 2 · Sin confirmacion no borra nada ───────────────────────────────────────
def test_sin_argumentos_solo_simula():
    espia = EjecutorEspia()
    code = bh.main([], database_url=URL_LOCAL, ejecutor=espia, entorno_os={})
    assert code == 0
    assert not espia.invocado, "sin --ejecutar no debe borrar nada"


def test_ejecutar_sin_confirmar_no_borra():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar"], database_url=URL_LOCAL, ejecutor=espia, entorno_os={})
    assert code == 2
    assert not espia.invocado


# ── 3 · Confirmacion incorrecta no borra nada ────────────────────────────────
@pytest.mark.parametrize("frase", ["yes", "si", "y", "YES", "BORRAR", "borrar-todo-local", ""])
def test_confirmacion_incorrecta_no_borra(frase):
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", frase],
                   database_url=URL_LOCAL, ejecutor=espia, entorno_os={})
    assert code == 2, f"la frase {frase!r} no debe bastar"
    assert not espia.invocado


def test_la_confirmacion_exige_mas_que_yes():
    assert bh.frase_requerida("local") == "BORRAR-TODO-LOCAL"
    assert len(bh.frase_requerida("local")) > len("yes")


# ── 4 · Produccion sin autorizacion adicional no borra nada ──────────────────
def test_produccion_sin_autorizacion_extra_no_borra():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
                   database_url=URL_PRODUCCION, ejecutor=espia, entorno_os={})
    assert code == 3, "produccion debe bloquearse aunque la frase sea correcta"
    assert not espia.invocado


def test_produccion_con_valor_de_autorizacion_erroneo_no_borra():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
                   database_url=URL_PRODUCCION, ejecutor=espia,
                   entorno_os={bh.VAR_AUTORIZACION_PRODUCCION: "si"})
    assert code == 3
    assert not espia.invocado


def test_url_desconocida_se_trata_como_produccion():
    """Fallo seguro: si no se puede probar que es local, se bloquea."""
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
                   database_url="postgresql://u:p@servidor-desconocido.example/db",
                   ejecutor=espia, entorno_os={})
    assert code == 3
    assert not espia.invocado


def test_database_url_ausente_se_trata_como_produccion():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
                   database_url="", ejecutor=espia, entorno_os={})
    assert code == 3
    assert not espia.invocado


# ── 5 · Entorno de prueba + confirmacion correcta llega al ejecutor ──────────
def test_local_con_confirmacion_correcta_llega_al_ejecutor():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-LOCAL"],
                   database_url=URL_LOCAL, ejecutor=espia, entorno_os={})
    assert code == 0
    assert espia.invocado, "con entorno local y frase correcta debe ejecutarse"


def test_localhost_se_considera_local():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-LOCAL"],
                   database_url=URL_LOCALHOST, ejecutor=espia, entorno_os={})
    assert code == 0
    assert espia.invocado


def test_produccion_con_autorizacion_completa_llega_al_ejecutor():
    espia = EjecutorEspia()
    code = bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
                   database_url=URL_PRODUCCION, ejecutor=espia,
                   entorno_os={bh.VAR_AUTORIZACION_PRODUCCION: bh.VALOR_AUTORIZACION_PRODUCCION})
    assert code == 0
    assert espia.invocado, "con las tres barreras superadas debe poder ejecutarse"


# ── 6 · Nunca se imprimen secretos ni la URL completa ────────────────────────
def test_no_se_imprime_la_url_completa_ni_credenciales(capsys):
    bh.main(["--ejecutar", "--confirmar", "BORRAR-TODO-PRODUCCION"],
            database_url=URL_PRODUCCION, ejecutor=EjecutorEspia(), entorno_os={})
    salida = capsys.readouterr().out
    assert URL_PRODUCCION not in salida, "no debe imprimirse la DATABASE_URL completa"
    assert "contrasena" not in salida.replace("usuario y contrasena ocultos", "")
    assert "usuario:contrasena" not in salida
    assert "postgresql://" not in salida


def test_describir_destino_oculta_credenciales():
    descripcion = bh.describir_destino(URL_PRODUCCION)
    assert "contrasena@" not in descripcion
    assert "usuario:" not in descripcion
    assert "oregon-postgres.render.com" in descripcion, "el host si es util para el operador"
    assert "bot_db" in descripcion


def test_describir_destino_sin_url():
    assert "sin DATABASE_URL" in bh.describir_destino("")


# ── 7 · Deteccion de entorno ─────────────────────────────────────────────────
@pytest.mark.parametrize("url,esperado", [
    (URL_LOCAL, "local"),
    ("sqlite://", "local"),
    (URL_LOCALHOST, "local"),
    ("postgresql://u:p@127.0.0.1:5432/db", "local"),
    (URL_PRODUCCION, "produccion"),
    ("postgresql://u:p@algo.amazonaws.com/db", "produccion"),
    ("", "produccion"),
])
def test_deteccion_de_entorno(url, esperado):
    assert bh.detectar_entorno(url) == esperado


# ── 8 · Ninguna prueba toca la BD real ───────────────────────────────────────
def test_toda_llamada_a_main_inyecta_dependencias():
    """
    Garantiza que ninguna prueba pueda alcanzar la BD real: cada invocacion de
    main() debe pasar `database_url`, `ejecutor` y `entorno_os` explicitos.
    Se analiza el AST de este mismo fichero.
    """
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    invocaciones = [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "main"
    ]
    assert invocaciones, "se esperaban llamadas a bh.main()"
    for llamada in invocaciones:
        claves = {k.arg for k in llamada.keywords}
        faltan = {"database_url", "ejecutor", "entorno_os"} - claves
        assert not faltan, (
            f"bh.main() en la linea {llamada.lineno} no inyecta {sorted(faltan)}: "
            "podria alcanzar la base de datos real"
        )
