from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.economia.diagnostico_factores_v9 import (
    _resumen_timestamp,
    diagnosticar_factores_v9,
)
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_selector_v8 import EstadoSelectorV8, ObservacionSelectorV8
from backend.economia.protocolo_edge_v9 import (
    CLASE_MOMENTUM,
    CLASE_REVERSION,
    CLASE_SIN_SENAL,
    ORIENTACION_ALTA,
    ORIENTACION_BAJA,
)


def _obs(symbol, ts, rank4, rank24, rankvol, retorno_bps):
    return ObservacionSelectorV8(
        estado=EstadoSelectorV8(
            symbol=symbol,
            timestamp_ms=ts,
            close=Decimal("100"),
            rank_retorno_4h=Decimal(str(rank4)),
            rank_retorno_24h=Decimal(str(rank24)),
            rank_sorpresa_volumen_4h=Decimal(str(rankvol)),
            mediana_retorno_24h_mercado=Decimal("0"),
            dispersion_iqr_retorno_24h_mercado=Decimal("0.02"),
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=24,
            retorno_cierre=Decimal(str(retorno_bps)) / Decimal("10000"),
            mfe=Decimal("0.03"),
            mae=Decimal("-0.02"),
        ),),
    )


def _ts_cierre_dia(dt):
    # cierre diario representado como 23:59:59.999; +1ms cae en múltiplo 24h.
    siguiente = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc) + timedelta(days=1)
    return int(siguiente.timestamp() * 1000) - 1


def test_resumen_timestamp_detecta_relacion_monotonica_perfecta():
    ts = _ts_cierre_dia(datetime(2025, 1, 1, tzinfo=timezone.utc))
    grupo = []
    for i in range(20):
        r = Decimal(i) / Decimal("19")
        retorno = Decimal("-100") + Decimal("300") * r
        grupo.append(_obs(f"S{i:02d}USDT", ts, r, 1-r, Decimal("0.5"), retorno))
    ic, spread, ret_alto, ret_bajo = _resumen_timestamp(grupo, "rank_retorno_4h")
    assert ic == pytest.approx(Decimal("1"))
    assert spread > Decimal("0")
    assert ret_alto > ret_bajo


def test_factor_desconocido_falla_cerrado():
    ts = _ts_cierre_dia(datetime(2025, 1, 1, tzinfo=timezone.utc))
    grupo = [_obs("BTCUSDT", ts, Decimal("0.5"), Decimal("0.5"), Decimal("0.5"), 10)] * 15
    with pytest.raises(ValueError, match="factor v9 desconocido"):
        _resumen_timestamp(grupo, "no_existe")


def test_diagnostico_completo_separa_momentum_reversion_y_ruido():
    datos = []
    dia = datetime(2025, 1, 1, tzinfo=timezone.utc)
    while dia.year == 2025:
        ts = _ts_cierre_dia(dia)
        for i in range(20):
            rank4 = Decimal(i) / Decimal("19")
            rank24 = Decimal("1") - rank4
            # Retorno futuro crece linealmente con rank4. El factor rank24 tiene
            # exactamente la orientación inversa. Volumen queda plano/ruidoso.
            retorno = Decimal("-100") + Decimal("300") * rank4
            datos.append(_obs(
                f"S{i:02d}USDT", ts,
                rank4, rank24, Decimal("0.5"), retorno,
            ))
        dia += timedelta(days=1)

    r = diagnosticar_factores_v9(datos)
    clases = {c.factor: c for c in r.clasificaciones}

    assert clases["rank_retorno_4h"].clase == CLASE_MOMENTUM
    assert clases["rank_retorno_4h"].orientacion_apta == ORIENTACION_ALTA
    assert clases["rank_retorno_24h"].clase == CLASE_REVERSION
    assert clases["rank_retorno_24h"].orientacion_apta == ORIENTACION_BAJA
    assert clases["rank_sorpresa_volumen_4h"].clase == CLASE_SIN_SENAL
    assert clases["rank_sorpresa_volumen_4h"].orientacion_apta is None

    momentum = next(
        x for x in r.resultados
        if x.factor == "rank_retorno_4h" and x.orientacion == ORIENTACION_ALTA
    )
    assert momentum.n_senales_top1 == 365
    assert momentum.retorno_top1_neto_medio_bps > 0
    assert momentum.fraccion_top1_neto_positivo == Decimal("1")
    assert momentum.n_meses_top1 == 12
    assert momentum.meses_top1_netos_positivos == 12
    assert momentum.n_folds_top1 == 4
    assert momentum.folds_top1_netos_positivos == 4
    assert momentum.apta
