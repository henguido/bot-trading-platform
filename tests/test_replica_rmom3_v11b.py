"""Tests de réplica temporal RMOM3 BOT 2.0-04B-v11b."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.momentum_semanal_v11 import EstadoMomentumV11, ObservacionMomentumV11
from backend.economia.replica_rmom3_v11b import replicar_rmom3_v11b


def _obs(ts: int, i: int, retorno_bps: int, senal: Decimal):
    return ObservacionMomentumV11(
        estado=EstadoMomentumV11(
            symbol=f"A{i:02d}USDT", timestamp_ms=ts, close=Decimal("100"),
            mom1=Decimal("0"), mom2=Decimal("0"), mom3=Decimal("0"),
            rmom1=Decimal("0"), rmom2=Decimal("0"), rmom3=senal,
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=168,
            retorno_cierre=Decimal(retorno_bps) / Decimal("10000"),
            mfe=max(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
            mae=min(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
        ),),
    )


def _anio(year: int, *, invertido=False):
    inicio = datetime(year, 1, 3 if year == 2022 else (2 if year == 2023 else 1), tzinfo=timezone.utc)
    # Normaliza al primer lunes del año.
    while inicio.weekday() != 0:
        inicio += timedelta(days=1)
    salida = []
    for semana in range(50):
        limite = inicio + timedelta(days=7 * semana)
        ts = int(limite.timestamp() * 1000) - 1
        for i in range(20):
            base = -50 + i * 15
            retorno = -base if invertido else base
            salida.append(_obs(ts, i, retorno, Decimal(i)))
    return salida


def test_tres_anios_con_senal_hacen_replica_consistente():
    datos = tuple(_anio(2022) + _anio(2023) + _anio(2024))
    r = replicar_rmom3_v11b(datos)
    assert r.anios_aptos == 3
    assert r.replica_consistente is True
    assert all(x.apto for x in r.anuales)


def test_un_anio_malo_aun_cumple_regla_2_de_3():
    datos = tuple(_anio(2022) + _anio(2023) + _anio(2024, invertido=True))
    r = replicar_rmom3_v11b(datos)
    assert r.anios_aptos == 2
    assert r.replica_consistente is True


def test_dos_anios_malos_falsan_replica():
    datos = tuple(_anio(2022) + _anio(2023, invertido=True) + _anio(2024, invertido=True))
    r = replicar_rmom3_v11b(datos)
    assert r.anios_aptos == 1
    assert r.replica_consistente is False
