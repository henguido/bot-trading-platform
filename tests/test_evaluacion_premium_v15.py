from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.evaluacion_premium_v15 import evaluar_premium_v15
from backend.economia.premium_spot_v15 import ObservacionPremiumSpotV15
from backend.economia.protocolo_premium_v15 import (
    CLASE_PREMIUM_PROMETEDOR_V15,
    CLASE_PREMIUM_SIN_SENAL_V15,
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
                if i < 5:
                    ret = Decimal("0.012")
                elif i >= 15:
                    ret = Decimal("-0.004")
                else:
                    ret = Decimal("0.002")
            elif modo == "market_only":
                ret = Decimal("0.01")
            elif modo == "invertido":
                ret = Decimal("-0.01") if i < 5 else Decimal("0.01")
            else:
                raise ValueError(modo)
            out.append(ObservacionPremiumSpotV15(
                symbol=f"S{i:02d}USDT",
                timestamp_signal_ms=ts,
                premium_close=Decimal(i),
                timestamp_entrada_ms=ts + DIA_MS,
                retorno_spot_siguiente=ret,
            ))
    return out


def test_premium_bajo_con_alpha_estable_pasa_4_de_4():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "alpha"))
    r = evaluar_premium_v15(tuple(obs))
    assert r.clase == CLASE_PREMIUM_PROMETEDOR_V15
    assert r.anios_aptos == 4
    assert all(a.apto for a in r.anuales)
    assert all(a.retorno_low5_neto_medio_bps > 0 for a in r.anuales)
    assert all(a.exceso_medio_bps > 0 for a in r.anuales)
    assert all(a.spread_low5_high5_medio_bps > 0 for a in r.anuales)


def test_mercado_sube_pero_selector_no_agrega_alpha_falla():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "market_only"))
    r = evaluar_premium_v15(tuple(obs))
    assert r.clase == CLASE_PREMIUM_SIN_SENAL_V15
    assert r.anios_aptos == 0
    assert all(a.retorno_low5_neto_medio_bps > 0 for a in r.anuales)
    assert all(a.exceso_medio_bps == 0 for a in r.anuales)
    assert all("EXCESO_MEDIO_NO_POSITIVO" in a.motivos_rechazo for a in r.anuales)
    assert all("SPREAD_MEDIO_NO_POSITIVO" in a.motivos_rechazo for a in r.anuales)


def test_solo_dos_anios_buenos_no_promociona():
    obs = []
    obs.extend(_anio(2022, "alpha"))
    obs.extend(_anio(2023, "alpha"))
    obs.extend(_anio(2024, "invertido"))
    obs.extend(_anio(2025, "invertido"))
    r = evaluar_premium_v15(tuple(obs))
    assert r.anios_aptos == 2
    assert r.clase == CLASE_PREMIUM_SIN_SENAL_V15


def test_menos_de_330_dias_falla_aunque_alpha_sea_perfecto():
    obs = []
    for year in (2022, 2023, 2024, 2025):
        obs.extend(_anio(year, "alpha", dias=329))
    r = evaluar_premium_v15(tuple(obs))
    assert r.anios_aptos == 0
    assert all("DIAS_INSUFICIENTES" in a.motivos_rechazo for a in r.anuales)


def test_orden_de_observaciones_no_cambia_resultado():
    obs = tuple(_anio(2022, "alpha"))
    a = evaluar_premium_v15(obs).anuales[0]
    b = evaluar_premium_v15(tuple(reversed(obs))).anuales[0]
    assert a == b
