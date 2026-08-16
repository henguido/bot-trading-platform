"""
Fase 6 · Un dato desconocido no se presenta como cero.

/balance leia backend.state.simulator, una instancia que NADIE escribia nunca:
average_price y pnl salian siempre 0.0, indistinguibles de un cero real.
/api/resumen hacia lo mismo y ademas llamaba `ganancia_total` a la suma del
VALOR de la cartera, que no es una ganancia.

INVARIANTE: desconocido != 0.0
"""
import ast
from pathlib import Path

import pytest

from backend.finanzas import (
    DISPONIBLE,
    NO_DISPONIBLE,
    campos,
    pnl_no_realizado,
    precio_medio_de,
)

RAIZ = Path(__file__).resolve().parents[1]


# ── Cero real vs desconocido ────────────────────────────────────────────────
def test_pnl_realmente_cero_es_cero_disponible():
    salida = campos("pnl", 0.0)
    assert salida["pnl"] == 0.0
    assert salida["pnl_status"] == DISPONIBLE, "un cero real SI es un dato"


def test_pnl_desconocido_es_null_no_disponible():
    salida = campos("pnl", None, motivo="sin coste base")
    assert salida["pnl"] is None, "jamas se inventa 0.0"
    assert salida["pnl_status"] == NO_DISPONIBLE
    assert salida["pnl_motivo"] == "sin coste base"


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf"), "abc"])
def test_valores_no_finitos_son_no_disponible(valor):
    salida = campos("pnl", valor)
    assert salida["pnl"] is None and salida["pnl_status"] == NO_DISPONIBLE


def test_posicion_realmente_cero_es_cero_valido():
    salida = campos("cantidad", 0.0)
    assert salida["cantidad"] == 0.0 and salida["cantidad_status"] == DISPONIBLE


# ── Precio medio ────────────────────────────────────────────────────────────
def test_precio_medio_cero_no_es_un_precio():
    """avg=0.0 significa 'sin coste base', no 'compre a cero'."""
    assert precio_medio_de({"BTCUSDT": {"precio_promedio": 0.0}}, "BTCUSDT") is None
    assert precio_medio_de({}, "BTCUSDT") is None
    assert precio_medio_de(None, "BTCUSDT") is None
    assert precio_medio_de({"BTCUSDT": {"precio_promedio": 100000.0}},
                           "BTCUSDT") == 100000.0


def test_sin_precio_medio_no_hay_pnl():
    assert pnl_no_realizado(110000.0, None, 0.001) is None, \
        "sin coste base no hay P&L, y desde luego no es cero"
    assert pnl_no_realizado(None, 100000.0, 0.001) is None
    assert pnl_no_realizado(110000.0, 100000.0, 0.001) == pytest.approx(10.0)


def test_pnl_cero_real_se_calcula_como_cero():
    """Comprado y cotizando al mismo precio: el P&L es cero DE VERDAD."""
    valor = pnl_no_realizado(100000.0, 100000.0, 0.001)
    assert valor == 0.0
    assert campos("pnl", valor)["pnl_status"] == DISPONIBLE


# ── Separacion PAPER / LIVE ─────────────────────────────────────────────────
def test_en_paper_el_saldo_del_exchange_no_tiene_coste_base(monkeypatch):
    from backend.config import settings
    from backend.routes import binance_routes

    monkeypatch.setattr(settings, "MODO_REAL", False)
    estado, motivo = binance_routes._coste_base_del_modo()

    assert estado == {}, "PAPER no debe leer el ledger LIVE"
    assert motivo and "PAPER" in motivo
    assert campos("pnl", pnl_no_realizado(100.0, precio_medio_de(estado, "BTCUSDT"),
                                          1.0), motivo=motivo)["pnl_status"] == NO_DISPONIBLE


def test_balance_ya_no_lee_el_simulator_huerfano():
    fuente = (RAIZ / "backend" / "routes" / "binance_routes.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            assert "state" not in nodo.module.split("."), \
                "/balance no puede leer una instancia de Simulator que nadie escribe"


def test_el_modulo_state_huerfano_ya_no_existe():
    assert not (RAIZ / "backend" / "state.py").exists(), (
        "backend/state.py contenia la instancia de Simulator que producia los "
        "average_price y pnl falsos de /balance")


# ── Sin ceros inventados en los endpoints ───────────────────────────────────
def _asignaciones_por_defecto(ruta, nombres):
    """Busca patrones tipo `x = algo or 0.0` o `.get(..., 0.0)` sobre esos nombres."""
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    ofensores = []
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", None) == "get"
                and len(nodo.args) == 2 and isinstance(nodo.args[1], ast.Constant)
                and nodo.args[1].value in (0, 0.0)
                and isinstance(nodo.args[0], ast.Constant)
                and nodo.args[0].value in nombres):
            ofensores.append(f"linea {nodo.lineno}: .get({nodo.args[0].value!r}, 0.0)")
    return ofensores


def test_los_endpoints_no_rellenan_con_cero():
    for ruta in (RAIZ / "backend" / "main.py",
                 RAIZ / "backend" / "routes" / "binance_routes.py"):
        ofensores = _asignaciones_por_defecto(
            ruta, {"precio_promedio", "pnl", "average_price"})
        assert not ofensores, f"{ruta.name}: {ofensores}"


def test_resumen_publica_el_valor_con_su_nombre_correcto():
    """`ganancia_total` sumaba el VALOR de la cartera, no una ganancia."""
    fuente = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")
    assert "valor_total_usd" in fuente
    assert '"ganancia_total"' not in fuente, \
        "el nombre antiguo afirmaba una ganancia que nunca se calculaba"


def test_el_frontend_no_sustituye_por_cero():
    fuente = (RAIZ / "frontend" / "src" / "pages" / "DashboardPage.jsx").read_text(
        encoding="utf-8")
    assert "b.pnl ?? 0" not in fuente and "b.average_price ?? 0" not in fuente, \
        "el frontend no puede convertir NO_DISPONIBLE en 0"
    assert "pnl_status" in fuente and "average_price_status" in fuente
    assert "ganancia_total" not in fuente


def test_ambos_endpoints_declaran_el_modo():
    """El consumidor debe saber si mira cifras PAPER o LIVE."""
    for ruta in (RAIZ / "backend" / "main.py",
                 RAIZ / "backend" / "routes" / "binance_routes.py"):
        assert '"modo": settings.TRADING_MODE' in ruta.read_text(encoding="utf-8"), \
            f"{ruta.name} debe declarar el modo en la respuesta"
