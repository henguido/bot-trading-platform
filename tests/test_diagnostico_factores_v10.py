from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.diagnostico_factores_v10 import diagnosticar_factores_v10
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.factores_v10 import EstadoFactoresV10, ObservacionFactoresV10
from backend.economia.protocolo_edge_v10 import (
    CLASE_ALTA,
    CLASE_BAJA,
    CLASE_SIN_SENAL,
    FACTOR_MAXRET_4H,
    FACTOR_POSICION_RANGO,
    FACTOR_RAM_24H,
    FACTOR_TAKER_BUY,
)


def cierre_dia_ms(year: int, month: int, day: int) -> int:
    inicio = datetime(year, month, day, tzinfo=timezone.utc)
    return int((inicio + timedelta(days=1)).timestamp() * 1000) - 1


def observacion(ts: int, i: int, *, regimen_positivo=True, retorno_futuro_bps=None):
    futuro = Decimal(str(
        retorno_futuro_bps if retorno_futuro_bps is not None else (i - 7) * 30
    ))
    return ObservacionFactoresV10(
        estado=EstadoFactoresV10(
            symbol=f"A{i:02d}USDT",
            timestamp_ms=ts,
            close=Decimal("100"),
            retorno_24h=Decimal("0.01") if regimen_positivo else Decimal("-0.01"),
            volatilidad_realizada_24h=Decimal("0.02"),
            # Alto RAM -> alto retorno futuro.
            momentum_ajustado_riesgo_24h=Decimal(i),
            # Factor plano: no puede tener señal monotónica.
            max_retorno_4h_24h=Decimal("0.01"),
            posicion_cierre_rango_24h=Decimal("0.5"),
            # Bajo taker-share -> alto retorno futuro.
            taker_buy_share_24h=Decimal(14 - i) / Decimal("14"),
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=24,
            retorno_cierre=futuro / Decimal("10000"),
            mfe=max(Decimal("0"), futuro / Decimal("10000")),
            mae=min(Decimal("0"), futuro / Decimal("10000")),
        ),),
    )


def dataset_anual():
    salida = []
    # 10 timestamps por mes, 15 activos contemporáneos -> 120 señales top-1.
    for mes in range(1, 13):
        for dia in range(1, 11):
            ts = cierre_dia_ms(2025, mes, dia)
            salida.extend(observacion(ts, i) for i in range(15))
    return salida


def clases(resultado):
    return {c.factor: c for c in resultado.clasificaciones}


def test_v10_detecta_alta_y_baja_cuando_son_estables_y_economicas():
    r = diagnosticar_factores_v10(dataset_anual())
    cs = clases(r)

    assert r.n_timestamps_regimen_no_negativo == 120
    assert len(r.resultados) == 8  # 4 factores x 2 orientaciones

    assert cs[FACTOR_RAM_24H].clase == CLASE_ALTA
    assert cs[FACTOR_RAM_24H].orientacion_apta == "ALTA"

    assert cs[FACTOR_TAKER_BUY].clase == CLASE_BAJA
    assert cs[FACTOR_TAKER_BUY].orientacion_apta == "BAJA"

    assert cs[FACTOR_MAXRET_4H].clase == CLASE_SIN_SENAL
    assert cs[FACTOR_POSICION_RANGO].clase == CLASE_SIN_SENAL


def test_v10_factor_alto_tiene_ic_spread_y_top1_coherentes():
    r = diagnosticar_factores_v10(dataset_anual())
    x = next(x for x in r.resultados if x.factor == FACTOR_RAM_24H and x.orientacion == "ALTA")

    assert x.apta
    assert x.ic_spearman_medio == Decimal("1")
    assert x.spread_orientado_medio_bps > Decimal("25")
    assert x.fraccion_timestamps_spread_signo_correcto == Decimal("1")
    assert x.n_senales_top1 == 120
    assert x.retorno_top1_neto_medio_bps > 0
    assert x.fraccion_top1_neto_positivo == Decimal("1")
    assert x.meses_top1_netos_positivos == 12
    assert x.folds_top1_netos_positivos == 4


def test_dias_de_regimen_negativo_se_excluyen_sin_usar_futuro():
    datos = dataset_anual()
    # 10 días extra de mercado negativo con retornos futuros enormes e inversos.
    for dia in range(11, 21):
        ts = cierre_dia_ms(2025, 1, dia)
        datos.extend(
            observacion(ts, i, regimen_positivo=False,
                        retorno_futuro_bps=(7 - i) * 1000)
            for i in range(15)
        )

    r = diagnosticar_factores_v10(datos)
    assert r.n_timestamps_regimen_no_negativo == 120
    assert clases(r)[FACTOR_RAM_24H].clase == CLASE_ALTA


def test_timestamps_con_menos_de_15_activos_no_entran():
    datos = dataset_anual()
    ts = cierre_dia_ms(2025, 12, 20)
    datos.extend(observacion(ts, i) for i in range(14))
    r = diagnosticar_factores_v10(datos)
    assert r.n_timestamps_regimen_no_negativo == 120
