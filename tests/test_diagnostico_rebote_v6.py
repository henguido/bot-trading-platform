from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.economia.diagnostico_rebote_v6 import (
    STOP,
    TARGET,
    TIME,
    evaluar_rebote_v6,
)
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_relativo_v2 import EstadoRelativoV2, ObservacionRelativaV2
from backend.economia.evaluacion_cost_aware import SenalCostAware


def ts(fecha: str) -> int:
    return int(datetime.fromisoformat(fecha).replace(tzinfo=timezone.utc).timestamp() * 1000)


def obs(timestamp_ms: int, symbol: str = "BTCUSDT", *, retorno_bps=0,
        mfe_bps=0, mae_bps=0):
    return ObservacionRelativaV2(
        estado=EstadoRelativoV2(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            close=Decimal("100"),
            rank_retorno_4h=Decimal("0.5"),
            rank_retorno_24h=Decimal("0.5"),
            rank_sorpresa_volumen_4h=Decimal("0.5"),
            mediana_retorno_24h_mercado=Decimal("-0.01"),
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=8,
            retorno_cierre=Decimal(str(retorno_bps)) / Decimal("10000"),
            mfe=Decimal(str(mfe_bps)) / Decimal("10000"),
            mae=Decimal(str(mae_bps)) / Decimal("10000"),
        ),),
    )


def senal(timestamp_ms: int, symbol: str = "BTCUSDT"):
    return SenalCostAware(
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        predicho_bps=Decimal("30"),
        real_bruto_bps=Decimal("0"),
        real_neto_bps=Decimal("-20"),
        real_neto_despues_margen_bps=Decimal("-25"),
        baseline_bruto_bps=Decimal("0"),
        uplift_bruto_bps=Decimal("0"),
    )


def test_stop_tiene_prioridad_si_stop_y_target_fueron_tocados():
    t = ts("2025-01-15T00:00:00")
    r = evaluar_rebote_v6(
        [senal(t)],
        [obs(t, mfe_bps=200, mae_bps=-60)],
    )
    x = r.resultados[0]
    assert x.salida == STOP
    assert x.stop_y_target_tocados
    assert x.bruto_salida_bps == Decimal("-50")
    assert x.neto_despues_hurdle_bps == Decimal("-75")


def test_target_aplica_si_no_toco_stop():
    t = ts("2025-01-15T00:00:00")
    r = evaluar_rebote_v6(
        [senal(t)],
        [obs(t, mfe_bps=200, mae_bps=-20)],
    )
    x = r.resultados[0]
    assert x.salida == TARGET
    assert not x.stop_y_target_tocados
    assert x.bruto_salida_bps == Decimal("175")
    assert x.neto_despues_hurdle_bps == Decimal("150")


def test_time_exit_resta_hurdle_si_no_hay_toques():
    t = ts("2025-01-15T00:00:00")
    r = evaluar_rebote_v6(
        [senal(t)],
        [obs(t, retorno_bps=40, mfe_bps=100, mae_bps=-20)],
    )
    x = r.resultados[0]
    assert x.salida == TIME
    assert x.bruto_salida_bps == Decimal("40")
    assert x.neto_despues_hurdle_bps == Decimal("15")


def test_senal_sin_observacion_falla_cerrado():
    t = ts("2025-01-15T00:00:00")
    with pytest.raises(ValueError, match="senal sin observacion"):
        evaluar_rebote_v6([senal(t)], [])


def _serie_anual(*, target: bool):
    senales = []
    observaciones = []
    # 10 timestamps por mes => 120 senales. Todos caen dentro de los 4 folds 2025.
    for mes in range(1, 13):
        for dia in range(1, 11):
            t = ts(f"2025-{mes:02d}-{dia:02d}T00:00:00")
            symbol = "BTCUSDT"
            senales.append(senal(t, symbol))
            if target:
                observaciones.append(obs(t, symbol, mfe_bps=200, mae_bps=-20))
            else:
                observaciones.append(obs(t, symbol, mfe_bps=20, mae_bps=-60))
    return senales, observaciones


def test_diagnostico_apto_exige_estabilidad_y_muestras_suficientes():
    senales, observaciones = _serie_anual(target=True)
    r = evaluar_rebote_v6(senales, observaciones)
    assert r.n_senales == 120
    assert r.n_target == 120
    assert r.retorno_neto_despues_hurdle_medio_bps == Decimal("150")
    assert r.fraccion_resultados_positivos == Decimal("1")
    assert r.n_meses_con_senal == 12
    assert r.meses_netos_positivos == 12
    assert r.n_folds_con_senal == 4
    assert r.folds_netos_positivos == 4
    assert r.apto_diagnostico
    assert r.motivos_rechazo == ()


def test_diagnostico_rechaza_payoff_negativo_estable():
    senales, observaciones = _serie_anual(target=False)
    r = evaluar_rebote_v6(senales, observaciones)
    assert r.n_stop == 120
    assert r.retorno_neto_despues_hurdle_medio_bps == Decimal("-75")
    assert not r.apto_diagnostico
    assert "RETORNO_NETO_NO_POSITIVO" in r.motivos_rechazo
    assert "RESULTADOS_POSITIVOS_INSUFICIENTES" in r.motivos_rechazo
    assert "ESTABILIDAD_MENSUAL_INSUFICIENTE" in r.motivos_rechazo
    assert "ESTABILIDAD_FOLDS_INSUFICIENTE" in r.motivos_rechazo
