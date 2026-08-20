from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.basis_spot_v17 import ObservacionBasisV17
from backend.economia.evaluacion_basis_v17 import evaluar_basis_v17
from backend.economia.protocolo_basis_v17 import CLASE_BASIS_PROMETEDOR_V17, CLASE_BASIS_SIN_SENAL_V17

DIA = 86_400_000


def _ts(year, d):
    return int((datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=d)).timestamp() * 1000)


def _anio(year, modo="alpha", dias=340):
    out = []
    for d in range(dias):
        ts = _ts(year, d)
        for i in range(20):
            basis = Decimal(i)
            if modo == "alpha":
                ret = Decimal("0.012") if i >= 15 else (Decimal("-0.004") if i < 5 else Decimal("0.002"))
            elif modo == "market_only":
                ret = Decimal("0.01")
            elif modo == "invertido":
                ret = Decimal("-0.01") if i >= 15 else Decimal("0.01")
            else:
                raise ValueError(modo)
            out.append(ObservacionBasisV17(
                symbol=f"S{i:02d}USDT", timestamp_signal_ms=ts,
                basis_perp=basis, timestamp_entrada_ms=ts + DIA,
                retorno_spot_siguiente=ret,
            ))
    return out


def test_top_basis_estable_pasa():
    obs = []
    for y in (2022, 2023, 2024, 2025): obs.extend(_anio(y, "alpha"))
    r = evaluar_basis_v17(tuple(obs))
    assert r.clase == CLASE_BASIS_PROMETEDOR_V17
    assert r.anios_aptos == 4


def test_mercado_sube_igual_pero_basis_no_agrega_alpha():
    obs = []
    for y in (2022, 2023, 2024, 2025): obs.extend(_anio(y, "market_only"))
    r = evaluar_basis_v17(tuple(obs))
    assert r.clase == CLASE_BASIS_SIN_SENAL_V17
    assert r.anios_aptos == 0
    assert all(a.exceso_medio_bps == 0 for a in r.anuales)


def test_direccion_contraria_falla_sin_invertirse_automaticamente():
    obs = []
    for y in (2022, 2023, 2024, 2025): obs.extend(_anio(y, "invertido"))
    r = evaluar_basis_v17(tuple(obs))
    assert r.clase == CLASE_BASIS_SIN_SENAL_V17
    assert r.anios_aptos == 0
    assert all(a.retorno_low5_neto_medio_bps < 0 for a in r.anuales)
