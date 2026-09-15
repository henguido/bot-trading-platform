from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


def test_main_reutiliza_mismo_exchange_info_para_fill_paper():
    fuente = MAIN.read_text(encoding="utf-8")

    assert 'info_por_symbol = {s["symbol"]: s for s in symbols_info}' in fuente
    assert "paper_symbol_info_provider=(" in fuente
    assert "lambda symbol: info_por_symbol.get(symbol)" in fuente

    # El camino productivo no debe llamar get_exchange_symbols_info(): ya posee
    # el exchangeInfo devuelto por get_available_assets en este mismo ciclo.
    bloque_loop = fuente[fuente.index("def trading_loop():"):]
    assert ".get_exchange_symbols_info(" not in bloque_loop


def test_filtros_se_construyen_antes_de_cartera_y_elegibilidad():
    fuente = MAIN.read_text(encoding="utf-8")
    inicio = fuente.index("def trading_loop():")
    info = fuente.index("info_por_symbol =", inicio)
    cartera = fuente.index("cartera = construir_cartera(", info)
    gate = fuente.index("elegibilidad.evaluar_compra(", cartera)

    assert info < cartera < gate
