from datetime import date

from backend.economia.inventario_orderflow_v23b import (
    ArchivoObjetivoV23B,
    ListadoSymbolV23B,
    evaluar_plan_v23b,
    listar_symbol_v23b,
)
from backend.economia.protocolo_orderflow_v23b import (
    DESARROLLO_2026_ABIERTO_V23B,
    FECHAS_OBJETIVO_V23B,
    IMPUTACION_PERMITIDA_V23B,
    N_ARCHIVOS_OBJETIVO_V23B,
    N_FECHAS_OBJETIVO_V23B,
    TEST_MAY_JUL_ABIERTO_V23B,
    UNIVERSO_V23B,
    USA_CONTENIDO_TRADES_V23B,
    USA_GPT_V23B,
    USA_RETORNOS_V23B,
)


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def _xml(contents, *, truncated=False, token=None):
    rows = "".join(
        f"<Contents><Key>{key}</Key><Size>{size}</Size></Contents>" for key, size in contents
    )
    next_token = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    flag = "true" if truncated else "false"
    return f"<ListBucketResult>{rows}<IsTruncated>{flag}</IsTruncated>{next_token}</ListBucketResult>".encode()


def _listados_completos(size=1_000_000):
    return tuple(
        ListadoSymbolV23B(
            symbol=symbol,
            archivos=tuple(
                ArchivoObjetivoV23B(
                    symbol=symbol,
                    fecha=fecha,
                    key=f"data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-{fecha.isoformat()}.zip",
                    size=size,
                )
                for fecha in FECHAS_OBJETIVO_V23B
            ),
            completa=True,
            n_requests=3,
            error=None,
        )
        for symbol in UNIVERSO_V23B
    )


def test_v23b_calendario_y_candados_quedan_fijos():
    assert len(UNIVERSO_V23B) == 20
    assert len(FECHAS_OBJETIVO_V23B) == N_FECHAS_OBJETIVO_V23B == 96
    assert N_ARCHIVOS_OBJETIVO_V23B == 1920
    assert FECHAS_OBJETIVO_V23B[0] == date(2022, 1, 3)
    assert FECHAS_OBJETIVO_V23B[1] == date(2022, 1, 17)
    assert FECHAS_OBJETIVO_V23B[-2] == date(2025, 12, 1)
    assert FECHAS_OBJETIVO_V23B[-1] == date(2025, 12, 15)
    assert USA_RETORNOS_V23B is False
    assert USA_CONTENIDO_TRADES_V23B is False
    assert USA_GPT_V23B is False
    assert IMPUTACION_PERMITIDA_V23B is False
    assert DESARROLLO_2026_ABIERTO_V23B is False
    assert TEST_MAY_JUL_ABIERTO_V23B is False


def test_v23b_listado_s3_filtra_solo_fechas_objetivo_y_pagina():
    symbol = UNIVERSO_V23B[0]
    objetivo = f"data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-2022-01-03.zip"
    no_objetivo = f"data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-2022-01-04.zip"
    respuestas = iter([
        _Resp(_xml([(objetivo, 123), (no_objetivo, 456)], truncated=True, token="t2")),
        _Resp(_xml([], truncated=False)),
    ])
    llamadas = []

    def fake_get(url, *, params, timeout):
        llamadas.append((url, params, timeout))
        return next(respuestas)

    r = listar_symbol_v23b(symbol, http_get=fake_get)
    assert r.completa is True
    assert r.n_requests == 2
    assert len(r.archivos) == 1
    assert r.archivos[0].fecha == date(2022, 1, 3)
    assert r.archivos[0].size == 123
    assert llamadas[1][1]["continuation-token"] == "t2"


def test_v23b_plan_completo_entra_en_ci():
    r = evaluar_plan_v23b(_listados_completos(size=1_000_000))
    assert r.resultado == "PLAN_TRANSFERENCIA_APTO_CI_V23B"
    assert r.apto is True
    assert r.entra_ci is True
    assert r.archivos_presentes == 1920
    assert r.fechas_aptas == 96
    assert r.minimo_simbolos_fecha == 20
    assert r.motivos_rechazo == ()


def test_v23b_plan_valido_puede_exceder_ci_sin_cambiar_calendario():
    r = evaluar_plan_v23b(_listados_completos(size=10_000_000))
    assert r.resultado == "PLAN_TRANSFERENCIA_APTO_FUERA_CI_V23B"
    assert r.apto is True
    assert r.entra_ci is False
    assert r.archivos_presentes == 1920
    assert r.fechas_aptas == 96


def test_v23b_rechaza_una_fecha_con_menos_de_15_simbolos_aunque_cobertura_global_sea_alta():
    fecha_problem = FECHAS_OBJETIVO_V23B[10]
    listados = []
    for i, listado in enumerate(_listados_completos()):
        archivos = listado.archivos
        if i < 6:
            archivos = tuple(a for a in archivos if a.fecha != fecha_problem)
        listados.append(
            ListadoSymbolV23B(listado.symbol, archivos, True, listado.n_requests, None)
        )
    r = evaluar_plan_v23b(tuple(listados))
    assert r.apto is False
    assert r.minimo_simbolos_fecha == 14
    assert "COBERTURA_CROSS_SECTION_FECHAS_INSUFICIENTE" in r.motivos_rechazo
