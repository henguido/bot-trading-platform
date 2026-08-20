"""Pruebas de features relativas 04B-v2."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_historico import velas_desde_klines
from backend.economia.edge_relativo_v2 import (
    MIN_SYMBOLS_POR_TIMESTAMP_V2,
    construir_observaciones_relativas_v2,
)

HORA = 60 * 60 * 1000
RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "edge_relativo_v2.py"


def kline(i, *, close, qv="100", intervalo_horas=4):
    c = Decimal(str(close))
    paso = intervalo_horas * HORA
    t0 = i * paso
    return [
        t0, str(c), str(c + Decimal("1")), str(c - Decimal("1")), str(c),
        "10", t0 + paso - 1, str(qv), 100, "0", "0", "0",
    ]


def serie(symbol_idx: int, n=70, *, spike_actual=False):
    factor = Decimal("1") + (Decimal(symbol_idx) / Decimal("1000"))
    filas = []
    for i in range(n):
        qv = "1000" if spike_actual and i == 42 else "100"
        filas.append(kline(i, close=Decimal("100") * (factor ** i), qv=qv))
    return velas_desde_klines(filas)


def universo(n=MIN_SYMBOLS_POR_TIMESTAMP_V2):
    return {
        f"S{i:02d}USDT": serie(i, spike_actual=(i == n - 1))
        for i in range(n)
    }


def primer_grupo(observaciones):
    ts = min(o.estado.timestamp_ms for o in observaciones)
    return tuple(o for o in observaciones if o.estado.timestamp_ms == ts)


def test_descarta_timestamp_completo_si_hay_menos_de_15_simbolos():
    obs = construir_observaciones_relativas_v2(universo(14))
    assert obs == ()


def test_features_son_ranks_cross_sectional_y_volumen_excluye_barra_actual():
    obs = construir_observaciones_relativas_v2(universo())
    grupo = primer_grupo(obs)
    assert len(grupo) == MIN_SYMBOLS_POR_TIMESTAMP_V2

    lider = next(o for o in grupo if o.estado.symbol == "S14USDT")
    rezagado = next(o for o in grupo if o.estado.symbol == "S00USDT")
    assert lider.estado.rank_retorno_4h == Decimal("1")
    assert lider.estado.rank_retorno_24h == Decimal("1")
    assert lider.estado.rank_sorpresa_volumen_4h == Decimal("1")
    assert rezagado.estado.rank_retorno_4h == Decimal("0")
    assert Decimal("0") <= lider.estado.mediana_retorno_24h_mercado


def test_cambiar_futuro_no_contamina_features_del_timestamp_actual():
    base = universo()
    alterado = dict(base)
    filas = []
    for i in range(70):
        close = Decimal("100") * ((Decimal("1.014")) ** i)
        if i == 50:
            close = Decimal("9999")
        filas.append(kline(i, close=close, qv="1000" if i == 42 else "100"))
    alterado["S14USDT"] = velas_desde_klines(filas)

    a = primer_grupo(construir_observaciones_relativas_v2(base))
    b = primer_grupo(construir_observaciones_relativas_v2(alterado))
    estados_a = {o.estado.symbol: o.estado for o in a}
    estados_b = {o.estado.symbol: o.estado for o in b}
    assert estados_a == estados_b


@pytest.mark.parametrize("kwargs", [
    {"intervalo_horas": 0},
    {"intervalo_horas": 5},
    {"min_symbols_por_timestamp": 1},
    {"barras_baseline_volumen": 0},
])
def test_parametros_invalidos_fallan_cerrado(kwargs):
    with pytest.raises(ValueError):
        construir_observaciones_relativas_v2(universo(), **kwargs)


def test_modulo_no_importa_red_trading_llm_ni_bd():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    prohibidos = (
        "requests", "sqlalchemy", "openai", "binance", "scanner",
        "MotorRiesgo", "SessionLocal", "real_trading",
    )
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto
