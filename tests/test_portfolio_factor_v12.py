from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.momentum_semanal_v11 import EstadoMomentumV11, ObservacionMomentumV11
from backend.economia.portfolio_factor_v12 import evaluar_portfolios_v12
from backend.economia.protocolo_portfolio_v12 import (
    CLASE_PORTFOLIO_PROMETEDOR_V12,
    CLASE_PORTFOLIO_SIN_SENAL_V12,
    HORIZONTE_HORAS_V12,
)


def _obs(ts_ms: int, symbol: str, rank: int, retorno_bps: Decimal):
    valor = Decimal(rank)
    return ObservacionMomentumV11(
        estado=EstadoMomentumV11(
            symbol=symbol,
            timestamp_ms=ts_ms,
            close=Decimal("100"),
            mom1=valor,
            mom2=valor,
            mom3=valor,
            rmom1=valor,
            rmom2=valor,
            rmom3=valor,
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=HORIZONTE_HORAS_V12,
            retorno_cierre=Decimal(retorno_bps) / Decimal("10000"),
            mfe=max(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
            mae=min(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
        ),),
    )


def _anio(year: int, *, alpha: bool, retorno_uniforme_bps: Decimal = Decimal("100")):
    salida = []
    # 52 semanas distribuidas por todo el año para cubrir los 12 meses y 4 folds.
    inicio = datetime(year, 1, 2, 23, 59, 59, tzinfo=timezone.utc)
    for semana in range(52):
        ts_ms = int((inicio + timedelta(days=7 * semana)).timestamp() * 1000)
        for rank in range(20):
            if alpha:
                # Los 5 valores de factor más altos ganan +100 bps; el resto 0.
                retorno = Decimal("100") if rank >= 15 else Decimal("0")
            else:
                # Basket y benchmark ganan lo mismo: rentable, pero sin alpha.
                retorno = retorno_uniforme_bps
            salida.append(_obs(ts_ms, f"S{rank:02d}USDT", rank, retorno))
    return salida


def _clasificacion(resultado, factor="mom1"):
    return next(c for c in resultado.clasificaciones if c.factor == factor)


def _anual(resultado, year: int, factor="mom1"):
    return next(r for r in resultado.anuales if r.factor == factor and r.year == year)


def test_basket_rentable_sin_exceso_no_se_declara_alpha():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, alpha=False))
    r = evaluar_portfolios_v12(obs)
    anual = _anual(r, 2025)
    assert anual.retorno_portfolio_neto_medio_bps == Decimal("75")
    assert anual.retorno_benchmark_neto_medio_bps == Decimal("75")
    assert anual.exceso_medio_bps == Decimal("0")
    assert anual.portfolio_apto
    assert not anual.exceso_apto
    assert not anual.apto
    assert "EXCESO_MEDIO_INSUFICIENTE" in anual.motivos_rechazo
    assert _clasificacion(r).clase == CLASE_PORTFOLIO_SIN_SENAL_V12


def test_top5_con_alpha_estable_pasa_en_cuatro_anios():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, alpha=True))
    r = evaluar_portfolios_v12(obs)
    anual = _anual(r, 2025)
    assert anual.n_semanas == 52
    assert anual.retorno_portfolio_neto_medio_bps == Decimal("75")
    assert anual.retorno_benchmark_neto_medio_bps == Decimal("0")
    assert anual.exceso_medio_bps == Decimal("75")
    assert anual.fraccion_portfolio_neto_positivo == Decimal("1")
    assert anual.fraccion_exceso_positivo == Decimal("1")
    assert anual.meses_portfolio_netos_positivos == 12
    assert anual.folds_portfolio_netos_positivos == 4
    assert anual.meses_exceso_positivos == 12
    assert anual.folds_exceso_positivos == 4
    assert anual.apto
    c = _clasificacion(r)
    assert c.anios_aptos == 4
    assert c.clase == CLASE_PORTFOLIO_PROMETEDOR_V12


def test_factor_que_solo_funciona_dos_de_cuatro_anios_no_sobrevive():
    obs = []
    obs.extend(_anio(2022, alpha=True))
    obs.extend(_anio(2023, alpha=True))
    obs.extend(_anio(2024, alpha=False))
    obs.extend(_anio(2025, alpha=False))
    r = evaluar_portfolios_v12(obs)
    c = _clasificacion(r)
    assert c.anios_aptos == 2
    assert c.clase == CLASE_PORTFOLIO_SIN_SENAL_V12
    assert "mom1" not in r.factores_prometedores


def test_hurdle_se_aplica_al_basket_y_benchmark_y_se_cancela_en_exceso():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, alpha=True))
    anual = _anual(evaluar_portfolios_v12(obs), 2022)
    # Top gross 100 - 25 = 75. Mercado gross 25 - 25 = 0. Exceso = 75.
    assert anual.retorno_portfolio_neto_medio_bps == Decimal("75")
    assert anual.retorno_benchmark_neto_medio_bps == Decimal("0")
    assert anual.exceso_medio_bps == Decimal("75")
