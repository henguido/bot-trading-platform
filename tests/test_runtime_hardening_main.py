from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


def test_min_notional_desconocido_no_se_convierte_en_un_default_arbitrario():
    fuente = MAIN.read_text(encoding="utf-8")
    inicio = fuente.index("def get_min_notional")
    fin = fuente.index("def _obtener_assets_con_costes", inicio)
    bloque = fuente[inicio:fin]
    assert "elegibilidad.leer_filtros" in bloque
    assert "return 1.0" not in bloque
    assert "else None" in bloque
    assert "FILTROS_EXCHANGE_DESCONOCIDOS" in fuente


def test_venta_no_depende_de_min_notional_pero_compra_si_falla_cerrado():
    fuente = MAIN.read_text(encoding="utf-8")
    assert "if lado is Lado.COMPRA else 0.0" in fuente
    assert "if lado is Lado.COMPRA and min_notional is None" in fuente
    assert "min_notional=min_notional" in fuente


def test_loop_usa_espera_interrumpible_y_coordinador_comparte_stop_event():
    fuente = MAIN.read_text(encoding="utf-8")
    assert "stop_trading = threading.Event()" in fuente
    assert "while not stop_trading.is_set():" in fuente
    assert "stop_trading.wait(settings.WAIT_TIME)" in fuente
    assert "time.sleep(settings.WAIT_TIME)" not in fuente
    assert "stop_event=stop_trading" in fuente


def test_shutdown_no_reintroduce_sleep_bloqueante_de_cuatro_horas():
    fuente = MAIN.read_text(encoding="utf-8")
    assert "time.sleep(settings.WAIT_TIME)" not in fuente
    assert fuente.count("stop_trading.wait(settings.WAIT_TIME)") == 1
