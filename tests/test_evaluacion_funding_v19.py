from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.evaluacion_funding_v19 import evaluar_funding_v19
from backend.economia.funding_spot_v19 import ObservacionFundingSpotV19
from backend.economia.protocolo_funding_v19 import (
    CLASE_FUNDING_PROMETEDOR_V19,
    CLASE_FUNDING_SIN_SENAL_V19,
)

DIA_MS = 86_400_000


def _ts(year, day):
    return int((datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)).timestamp() * 1000)


def _anio(year, modo="alpha", dias=340):
    out = []
    for d in range(dias):
        ts = _ts(year, d)
        for i in range(20):
            if modo == "alpha":
                ret = Decimal("0.012") if i < 5 else (Decimal("-0.004") if i >= 15 else Decimal("0.002"))
            elif modo == "market_only":
                ret = Decimal("0.01")
            elif modo == "invertido":
                ret = Decimal("-0.01") if i < 5 else Decimal("0.01")
            else:
                raise ValueError(modo)
            out.append(ObservacionFundingSpotV19(
                symbol=f"S{i:02d}USDT",
                timestamp_signal_ms=ts,
                funding_suma_dia=Decimal(i - 10) / Decimal("100000"),
                n_settlements=3,
                timestamp_entrada_ms=ts + DIA_MS,
                retorno_spot_siguiente=ret,
            ))
    return out


def test_funding_mas_negativo_con_alpha_estable_pasa_4_de_4():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "alpha"))
    r = evaluar_funding_v19(tuple(obs))
    assert r.clase == CLASE_FUNDING_PROMETEDOR_V19
    assert r.anios_aptos == 4
    assert all(a.apto for a in r.anuales)
    assert all(a.retorno_bottom5_neto_medio_bps > 0 for a in r.anuales)
    assert all(a.exceso_medio_bps > 0 for a in r.anuales)
    assert all(a.spread_bottom5_top5_medio_bps > 0 for a in r.anuales)


def test_mercado_sube_igual_para_todos_no_es_alpha():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "market_only"))
    r = evaluar_funding_v19(tuple(obs))
    assert r.clase == CLASE_FUNDING_SIN_SENAL_V19
    assert r.anios_aptos == 0
    assert all(a.exceso_medio_bps == 0 for a in r.anuales)
    assert all("EXCESO_MEDIO_NO_POSITIVO" in a.motivos_rechazo for a in r.anuales)


def test_si_signo_real_fuera_contrario_no_se_autoinvierte():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "invertido"))
    r = evaluar_funding_v19(tuple(obs))
    assert r.clase == CLASE_FUNDING_SIN_SENAL_V19
    assert r.anios_aptos == 0
    assert all(a.spread_bottom5_top5_medio_bps < 0 for a in r.anuales)


def test_solo_dos_anios_buenos_no_promociona():
    obs = []
    obs.extend(_anio(2022, "alpha")); obs.extend(_anio(2023, "alpha"))
    obs.extend(_anio(2024, "invertido")); obs.extend(_anio(2025, "invertido"))
    r = evaluar_funding_v19(tuple(obs))
    assert r.anios_aptos == 2
    assert r.clase == CLASE_FUNDING_SIN_SENAL_V19


def test_menos_de_330_dias_no_pasa():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "alpha", dias=329))
    r = evaluar_funding_v19(tuple(obs))
    assert r.anios_aptos == 0
    assert all("DIAS_INSUFICIENTES" in a.motivos_rechazo for a in r.anuales)


def test_orden_de_entrada_no_cambia_resultado():
    obs = tuple(_anio(2022, "alpha"))
    assert evaluar_funding_v19(obs).anuales[0] == evaluar_funding_v19(tuple(reversed(obs))).anuales[0]
