from decimal import Decimal

import pytest

from backend.economia.edge_historico import Vela
from backend.economia.edge_selector_v8 import (
    EstadoSelectorV8,
    construir_observaciones_selector_v8,
    vector_selector_v8,
)

H4_MS = 4 * 60 * 60 * 1000


def _velas(symbol_idx: int, n: int = 60):
    salida = []
    precio = Decimal("100") + Decimal(symbol_idx)
    for i in range(n):
        # Trayectorias distintas pero deterministas; solo datos hasta t participan
        # en las features. El volumen tambien varia por simbolo y barra.
        cambio = Decimal((i + symbol_idx) % 7 - 3) / Decimal("1000")
        close = precio * (Decimal("1") + cambio)
        high = max(precio, close) * Decimal("1.002")
        low = min(precio, close) * Decimal("0.998")
        open_ms = i * H4_MS
        salida.append(Vela(
            open_time_ms=open_ms,
            open=precio,
            high=high,
            low=low,
            close=close,
            volume=Decimal("1000") + Decimal(i + symbol_idx),
            close_time_ms=open_ms + H4_MS - 1,
            quote_volume=(Decimal("1000") + Decimal(i + symbol_idx)) * close,
            trades=100 + i,
        ))
        precio = close
    return tuple(salida)


def _dataset(n_symbols: int = 15):
    return {f"S{i:02d}USDT": _velas(i) for i in range(n_symbols)}


def test_v8_construye_cinco_features_y_dispersion_no_negativa():
    obs = construir_observaciones_selector_v8(_dataset())
    assert obs
    primero = obs[0]
    vector = vector_selector_v8(primero.estado)
    assert len(vector) == 5
    assert 0 <= vector[0] <= 1
    assert 0 <= vector[1] <= 1
    assert 0 <= vector[2] <= 1
    assert primero.estado.dispersion_iqr_retorno_24h_mercado >= 0


def test_v8_descarta_timestamp_si_no_hay_15_simbolos():
    obs = construir_observaciones_selector_v8(_dataset(14))
    assert obs == ()


def test_vector_rechaza_dispersion_negativa():
    estado = EstadoSelectorV8(
        symbol="BTCUSDT",
        timestamp_ms=1,
        close=Decimal("1"),
        rank_retorno_4h=Decimal("0.5"),
        rank_retorno_24h=Decimal("0.5"),
        rank_sorpresa_volumen_4h=Decimal("0.5"),
        mediana_retorno_24h_mercado=Decimal("0"),
        dispersion_iqr_retorno_24h_mercado=Decimal("-0.01"),
    )
    with pytest.raises(ValueError, match="dispersion v8 negativa"):
        vector_selector_v8(estado)


def test_cambiar_futuro_no_cambia_features_del_mismo_timestamp():
    series = _dataset()
    obs_a = construir_observaciones_selector_v8(series)
    objetivo = obs_a[len(obs_a) // 3]
    ts = objetivo.estado.timestamp_ms
    symbol = objetivo.estado.symbol

    modificadas = dict(series)
    velas = list(modificadas[symbol])
    # Solo alteramos una vela estrictamente posterior al timestamp objetivo.
    idx_futuro = next(i for i, v in enumerate(velas) if v.close_time_ms > ts)
    v = velas[idx_futuro]
    velas[idx_futuro] = Vela(
        open_time_ms=v.open_time_ms,
        open=v.open,
        high=v.high * Decimal("2"),
        low=v.low,
        close=v.close * Decimal("1.5"),
        volume=v.volume,
        close_time_ms=v.close_time_ms,
        quote_volume=v.quote_volume,
        trades=v.trades,
    )
    modificadas[symbol] = tuple(velas)
    obs_b = construir_observaciones_selector_v8(modificadas)

    a = next(o for o in obs_a if o.estado.timestamp_ms == ts and o.estado.symbol == symbol)
    b = next(o for o in obs_b if o.estado.timestamp_ms == ts and o.estado.symbol == symbol)
    assert vector_selector_v8(a.estado) == vector_selector_v8(b.estado)
