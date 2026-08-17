"""
Robustez: informar de un error NO puede matar el bucle de trading.

CORRECCION DESCUBIERTA DURANTE LA VALIDACION FUNCIONAL DE BOT 2.0-02A.
No forma parte del diseno de 02A: es un fallo del baseline que la ejecucion
real en PAPER puso a la vista.

El manejador de errores del ciclo hacia:

    print(f"❌ Error inesperado en ciclo de trading: ...")
    traceback.print_exc()

Con un stdout incapaz de codificar el emoji -cp1252, que es lo que se obtiene
en cuanto la salida se redirige a un fichero o a un pipe- el propio print
lanzaba UnicodeEncodeError DENTRO del except y mataba el hilo de trading. Se
observo: el bot murio en el primer error en lugar de esperar y reintentar.

Ninguna prueba de este modulo sale a la red.
"""
import ast
import pathlib
import sys

import pytest

import backend.main as main

RAIZ = pathlib.Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"

EMOJI = "❌"          # ❌  no existe en cp1252
ESCAPE = "\\u274c"        # como queda tras degradar a ASCII


class StdoutCp1252:
    """
    Doble de una consola cp1252: lanza al escribir cualquier caracter que no
    sepa codificar, exactamente como el stdout redirigido de Windows.
    """

    encoding = "cp1252"

    def __init__(self):
        self.escrito = []
        self.rechazos = 0

    def write(self, s):
        try:
            s.encode(self.encoding)
        except UnicodeEncodeError:
            self.rechazos += 1
            raise
        self.escrito.append(s)
        return len(s)

    def flush(self):
        pass

    def texto(self):
        return "".join(self.escrito)


class StdoutRoto:
    """Stream que falla siempre, incluso en ASCII."""

    encoding = "ascii"

    def write(self, s):
        raise OSError("el stream esta cerrado")

    def flush(self):
        pass


class _Parar(BaseException):
    """Corta el `while True` sin pasar por su `except Exception`."""


# ═══════════════════════════════════════════════════════════════════════════
# EL FALLO REPRODUCIDO
# ═══════════════════════════════════════════════════════════════════════════
def test_el_print_original_si_habria_matado_el_hilo():
    """
    Demuestra el fallo que se corrige: con este stdout, el print del baseline
    lanza. Es la razon de existir de `reportar_error_de_ciclo`.
    """
    salida = StdoutCp1252()
    with pytest.raises(UnicodeEncodeError):
        print(f"{EMOJI} Error inesperado en ciclo de trading: X", file=salida)
    assert salida.rechazos == 1


def test_reportar_error_no_lanza_con_stdout_cp1252(monkeypatch):
    salida = StdoutCp1252()
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "stderr", salida)

    try:
        raise ValueError("fallo de ejemplo")
    except ValueError as e:
        main.reportar_error_de_ciclo(e)      # no debe lanzar

    texto = salida.texto()
    assert EMOJI not in texto, "el emoji no se pudo codificar"
    assert ESCAPE in texto, (
        "el caracter perdido debe quedar legible como escape, no borrado")


def test_no_se_oculta_la_excepcion_original(monkeypatch):
    """Clase, mensaje y traceback siguen apareciendo."""
    salida = StdoutCp1252()
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "stderr", salida)

    try:
        raise KeyError("clave-que-falta")
    except KeyError as e:
        main.reportar_error_de_ciclo(e)

    texto = salida.texto()
    assert "KeyError" in texto, "se pierde el TIPO de la excepcion"
    assert "clave-que-falta" in texto, "se pierde el MENSAJE"
    assert "Traceback (most recent call last)" in texto, "se pierde el traceback"
    assert "test_no_se_oculta_la_excepcion_original" in texto, \
        "el traceback debe seguir senalando donde ocurrio"


def test_funciona_igual_con_stdout_utf8(monkeypatch, capsys):
    """Con un stdout capaz, el mensaje sale intacto: nada se degrada de mas."""
    try:
        raise ValueError("fallo de ejemplo")
    except ValueError as e:
        main.reportar_error_de_ciclo(e)

    capturado = capsys.readouterr()
    assert EMOJI in capturado.out, "con stdout UTF-8 el emoji debe conservarse"
    assert ESCAPE not in capturado.out
    assert "ValueError: fallo de ejemplo" in capturado.out
    assert "Traceback (most recent call last)" in capturado.err, \
        "el traceback sigue yendo a stderr, como con print_exc()"


def test_un_traceback_con_emoji_tampoco_mata_el_reporte(monkeypatch):
    """El emoji puede venir en el propio mensaje de la excepcion."""
    salida = StdoutCp1252()
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "stderr", salida)

    try:
        raise RuntimeError(f"{EMOJI} fallo con emoji dentro {EMOJI}")
    except RuntimeError as e:
        main.reportar_error_de_ciclo(e)

    assert "RuntimeError" in salida.texto()


def test_una_excepcion_con_str_hostil_conserva_al_menos_el_tipo(monkeypatch):
    salida = StdoutCp1252()
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "stderr", salida)

    class ErrorHostil(Exception):
        def __str__(self):
            raise RuntimeError("no me conviertas a texto")

    try:
        raise ErrorHostil()
    except ErrorHostil as e:
        main.reportar_error_de_ciclo(e)

    assert "ErrorHostil" in salida.texto(), \
        "aunque __str__ falle, el TIPO debe informarse"


def test_un_stream_completamente_roto_no_propaga(monkeypatch):
    """Ultimo recurso: no imprimir. Informar nunca puede tumbar el bot."""
    monkeypatch.setattr(sys, "stdout", StdoutRoto())
    monkeypatch.setattr(sys, "stderr", StdoutRoto())

    try:
        raise ValueError("fallo")
    except ValueError as e:
        main.reportar_error_de_ciclo(e)     # no debe lanzar

    assert main.imprimir_resistente("texto", StdoutRoto()) is False


# ═══════════════════════════════════════════════════════════════════════════
# EL BUCLE LLEGA A SU ESPERA NORMAL Y REINTENTA
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def bucle_que_falla(monkeypatch):
    """
    trading_loop cuyo ciclo falla siempre, con un stdout cp1252.

    Es el escenario exacto de la validacion: el error se produce, hay que
    informarlo, y el bucle debe seguir hasta su espera y reintentar.
    """
    salida = StdoutCp1252()
    esperas = []
    intentos = {"n": 0}
    limite = {"n": 3}

    def contexto_que_falla():
        intentos["n"] += 1
        if intentos["n"] > limite["n"]:
            raise _Parar()
        # Mensaje CON emoji: reproduce el caso real.
        raise RuntimeError(f"{EMOJI} fallo del ciclo numero {intentos['n']}")

    monkeypatch.setattr(main, "cargar_contexto_usuario", contexto_que_falla)
    monkeypatch.setattr(main.time, "sleep", lambda s: esperas.append(s))

    def ejecutar(n=3):
        limite["n"] = n
        # Los streams se sustituyen AQUI, no en el cuerpo del fixture: la
        # captura de pytest reinstala sys.stdout al entrar en la fase de
        # llamada y pisaria un monkeypatch hecho durante el setup.
        monkeypatch.setattr(sys, "stdout", salida)
        monkeypatch.setattr(sys, "stderr", salida)
        with pytest.raises(_Parar):
            main.trading_loop()
        return esperas, salida, intentos

    return ejecutar


def test_tras_el_error_el_bucle_llega_a_su_espera_normal(bucle_que_falla):
    esperas, _, intentos = bucle_que_falla(n=3)

    assert esperas == [main.settings.WAIT_TIME] * 3, (
        "cada error debe terminar en la espera normal del bucle, con el mismo "
        "WAIT_TIME de siempre")
    assert intentos["n"] == 4, (
        "el bucle reintento tras cada error en lugar de morir en el primero")


def test_el_bucle_informa_de_cada_error_sin_morir(bucle_que_falla):
    _, salida, _ = bucle_que_falla(n=3)
    texto = salida.texto()

    assert texto.count("Error inesperado en ciclo de trading") == 3
    assert texto.count("RuntimeError") >= 3
    assert EMOJI not in texto
    assert salida.rechazos >= 3, (
        "el stdout SI rechazo el emoji: el fallo se reproduce de verdad")


def test_la_telemetria_del_ciclo_se_vuelca_igual_tras_el_error(bucle_que_falla,
                                                              monkeypatch):
    """El `finally` de 02A sigue ejecutandose por este camino."""
    volcados = []
    from backend import telemetria_http

    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar",
                        lambda self, **k: volcados.append(self.ciclo_id) or 0)
    bucle_que_falla(n=3)

    assert len(volcados) == 4, "un volcado por iteracion, incluidas las fallidas"
    assert len(set(volcados)) == 4, "un ciclo_id distinto por iteracion"


# ═══════════════════════════════════════════════════════════════════════════
# LA CORRECCION ES MINIMA Y AISLADA
# ═══════════════════════════════════════════════════════════════════════════
def _trading_loop_ast():
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")


def _manejador_principal():
    """
    El `except` del ciclo completo, no los internos.

    Se localiza como el `try` que es hijo DIRECTO del `while`: los demas estan
    dentro de su cuerpo, asi que un fallo suyo ya lo recoge este.
    """
    fn = _trading_loop_ast()
    bucle = next(n for n in ast.walk(fn) if isinstance(n, ast.While))
    principal = next(n for n in bucle.body if isinstance(n, ast.Try))
    assert principal.handlers, "el bucle debe seguir capturando sus errores"
    return principal.handlers


def test_el_manejador_no_vuelve_a_imprimir_en_crudo():
    """Guarda: ningun print ni print_exc directo dentro del except principal."""
    for h in _manejador_principal():
        for nodo in ast.walk(h):
            if not isinstance(nodo, ast.Call):
                continue
            assert getattr(nodo.func, "id", None) != "print", (
                f"linea {nodo.lineno}: un print directo en el manejador puede "
                f"lanzar y matar el hilo; usar reportar_error_de_ciclo")
            assert getattr(nodo.func, "attr", None) != "print_exc", (
                f"linea {nodo.lineno}: print_exc escribe por su cuenta y falla "
                f"por el mismo motivo que el print")


def test_el_scheduling_del_manejador_no_ha_cambiado():
    """
    La correccion de robustez no toca la espera ni el contador de ciclos.

    En la fase 03A la espera se traslado del manejador al `finally`, para que la
    telemetria se persista ANTES de dormir. El manejador conserva su
    `ciclo += 1` y marca que hay que esperar; la unica espera de WAIT_TIME vive
    ahora en el finally y la fija tests/test_persistencia_antes_de_esperar.py.
    """
    marcas, incrementos = [], []
    for h in _manejador_principal():
        for nodo in ast.walk(h):
            if isinstance(nodo, ast.Call) and \
                    getattr(nodo.func, "attr", None) == "sleep":
                pytest.fail(f"linea {nodo.lineno}: el manejador no debe dormir "
                            f"antes de que el finally vuelque la telemetria")
            if (isinstance(nodo, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "esperar_ciclo"
                            for t in nodo.targets)):
                marcas.append(nodo)
            if (isinstance(nodo, ast.AugAssign)
                    and isinstance(nodo.target, ast.Name)
                    and nodo.target.id == "ciclo"):
                incrementos.append(nodo)

    assert len(marcas) == 1, "el manejador debe seguir pidiendo UNA espera"
    assert len(incrementos) == 1, \
        "y seguir avanzando el ciclo exactamente una vez"


def test_la_correccion_no_toca_riesgo_decisiones_ni_modo():
    """
    Los helpers nuevos son de impresion y nada mas.

    Se comparan IDENTIFICADORES reales, no el volcado en bruto: el nombre de la
    propia funcion y su docstring mencionan "ciclo" sin usarlo.
    """
    prohibidos = {"motor_riesgo", "MotorRiesgo", "cartera", "MODO_REAL",
                  "TRADING_MODE", "real_trader", "SessionLocal", "WAIT_TIME",
                  "ciclo", "settings", "medidor"}
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))

    for nombre in ("imprimir_resistente", "reportar_error_de_ciclo"):
        fn = next(n for n in ast.walk(arbol)
                  if isinstance(n, ast.FunctionDef) and n.name == nombre)
        usados = set()
        for nodo in ast.walk(fn):
            if isinstance(nodo, ast.Name):
                usados.add(nodo.id)
            elif isinstance(nodo, ast.Attribute):
                usados.add(nodo.attr)
        intrusos = usados & prohibidos
        assert not intrusos, f"{nombre} no debe tocar {sorted(intrusos)}"


def test_paper_sigue_activo():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False
