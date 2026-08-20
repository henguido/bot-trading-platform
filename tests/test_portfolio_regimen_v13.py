from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.momentum_semanal_v11 import EstadoMomentumV11, ObservacionMomentumV11
from backend.economia.portfolio_regimen_v13 import evaluar_portfolios_regimen_v13
from backend.economia.protocolo_portfolio_v13 import (
    CLASE_FACTOR_PROMETEDOR_V13,
    CLASE_FACTOR_SIN_SENAL_V13,
    CLASE_GATE_PROMETEDOR_V13,
    HORIZONTE_HORAS_V13,
)


def _obs(ts_ms: int, symbol: str, rank: int, *, regime_on: bool, retorno_bps: Decimal):
    factor = Decimal(rank + 1)
    mom3 = factor if regime_on else -factor
    return ObservacionMomentumV11(
        estado=EstadoMomentumV11(
            symbol=symbol,
            timestamp_ms=ts_ms,
            close=Decimal("100"),
            mom1=factor,
            mom2=factor,
            mom3=mom3,
            rmom1=factor,
            rmom2=factor,
            rmom3=factor,
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=HORIZONTE_HORAS_V13,
            retorno_cierre=Decimal(retorno_bps) / Decimal("10000"),
            mfe=max(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
            mae=min(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
        ),),
    )


def _anio(year: int, *, alpha: bool):
    salida = []
    inicio = datetime(year, 1, 2, 23, 59, 59, tzinfo=timezone.utc)
    for semana in range(52):
        regime_on = semana % 2 == 0  # 26 semanas activas, repartidas por todo el año.
        ts_ms = int((inicio + timedelta(days=7 * semana)).timestamp() * 1000)
        for rank in range(20):
            if regime_on:
                if alpha:
                    retorno = Decimal("150") if rank >= 15 else Decimal("50")
                else:
                    retorno = Decimal("100")
            else:
                retorno = Decimal("-500")
            salida.append(_obs(ts_ms, f"S{rank:02d}USDT", rank, regime_on=regime_on, retorno_bps=retorno))
    return salida


def _gate(r, year=2025):
    return next(x for x in r.gate_anual if x.year == year)


def _factor(r, factor="mom1", year=2025):
    return next(x for x in r.factores_anuales if x.factor == factor and x.year == year)


def _clasificacion(r, factor="mom1"):
    return next(x for x in r.clasificaciones if x.factor == factor)


def test_gate_evade_semanas_bajistas_y_pasa_estable():
    obs = []
    for y in (2022, 2023, 2024, 2025):
        obs.extend(_anio(y, alpha=False))
    r = evaluar_portfolios_regimen_v13(obs)
    g = _gate(r)
    assert g.n_semanas_total == 52
    assert g.n_semanas_activas == 26
    assert g.retorno_activo_medio_bps == Decimal("75")
    assert g.retorno_calendar_medio_bps == Decimal("37.5")
    assert g.fraccion_activa_neta_positiva == Decimal("1")
    assert g.n_meses_activos == 12
    assert g.n_folds_activos == 4
    assert g.apto
    assert r.gate_anios_aptos == 4
    assert r.gate_clase == CLASE_GATE_PROMETEDOR_V13


def test_basket_rentable_bajo_gate_pero_sin_alpha_sigue_fallando():
    obs = []
    for y in (2022, 2023, 2024, 2025):
        obs.extend(_anio(y, alpha=False))
    r = evaluar_portfolios_regimen_v13(obs)
    f = _factor(r)
    assert f.retorno_portfolio_activo_medio_bps == Decimal("75")
    assert f.retorno_portfolio_calendar_medio_bps == Decimal("37.5")
    assert f.exceso_activo_medio_bps == Decimal("0")
    assert f.portfolio_apto
    assert not f.exceso_apto
    assert not f.apto
    assert "EXCESO_MEDIO_INSUFICIENTE" in f.motivos_rechazo
    assert _clasificacion(r).clase == CLASE_FACTOR_SIN_SENAL_V13


def test_top5_con_alpha_estable_bajo_gate_pasa_cuatro_anios():
    obs = []
    for y in (2022, 2023, 2024, 2025):
        obs.extend(_anio(y, alpha=True))
    r = evaluar_portfolios_regimen_v13(obs)
    f = _factor(r)
    # Top gross 150-25=125; mercado gross 75-25=50; exceso=75.
    assert f.retorno_portfolio_activo_medio_bps == Decimal("125")
    assert f.retorno_portfolio_calendar_medio_bps == Decimal("62.5")
    assert f.exceso_activo_medio_bps == Decimal("75")
    assert f.fraccion_portfolio_activo_positivo == Decimal("1")
    assert f.fraccion_exceso_positivo == Decimal("1")
    assert f.apto
    c = _clasificacion(r)
    assert c.anios_aptos == 4
    assert c.clase == CLASE_FACTOR_PROMETEDOR_V13


def test_mediana_mom3_igual_a_cero_es_cash():
    year = 2025
    inicio = datetime(year, 1, 5, 23, 59, 59, tzinfo=timezone.utc)
    obs = []
    for semana in range(52):
        ts_ms = int((inicio + timedelta(days=7 * semana)).timestamp() * 1000)
        for rank in range(20):
            # Valores simétricos -9.5..+9.5 => mediana exactamente 0.
            mom3 = Decimal(rank) - Decimal("9.5")
            factor = Decimal(rank + 1)
            obs.append(ObservacionMomentumV11(
                estado=EstadoMomentumV11(
                    symbol=f"S{rank:02d}USDT", timestamp_ms=ts_ms, close=Decimal("100"),
                    mom1=factor, mom2=factor, mom3=mom3,
                    rmom1=factor, rmom2=factor, rmom3=factor,
                ),
                etiquetas=(EtiquetaHorizonte(
                    horizonte_horas=HORIZONTE_HORAS_V13,
                    retorno_cierre=Decimal("0.10"), mfe=Decimal("0.10"), mae=Decimal("0"),
                ),),
            ))
    r = evaluar_portfolios_regimen_v13(obs)
    g = _gate(r)
    assert g.n_semanas_activas == 0
    assert g.retorno_calendar_medio_bps == Decimal("0")
    assert not g.apto
