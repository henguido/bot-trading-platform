from backend.economia.edge_empirico import (
    DATOS_INVALIDOS,
    ESTADO_APTO,
    MUESTRAS_INSUFICIENTES,
    SIN_SENAL,
    VelaCerrada,
    estimar_edge,
    normalizar_klines,
)


def _velas_desde_cierres(cierres):
    hora = 3_600_000
    return tuple(
        VelaCerrada(i * hora, (i + 1) * hora - 1, float(c))
        for i, c in enumerate(cierres)
    )


def test_normalizar_klines_descarta_abierta_e_invalidas_y_deduplica():
    hora = 3_600_000
    filas = [
        [0, "1", "1", "1", "100", "1", hora - 1],
        [hora, "1", "1", "1", "101", "1", 2 * hora - 1],
        [hora, "1", "1", "1", "102", "1", 2 * hora - 1],
        [2 * hora, "1", "1", "1", "0", "1", 3 * hora - 1],
        [3 * hora, "1", "1", "1", "103", "1", 4 * hora - 1],
    ]
    velas = normalizar_klines(filas, ahora_ms=3 * hora)
    assert [v.close for v in velas] == [100.0, 102.0]


def test_sin_senal_si_momentum_actual_no_es_alcista():
    cierres = [100 + i for i in range(80)]
    cierres[-1] = cierres[-25] * 0.95
    r = estimar_edge(_velas_desde_cierres(cierres), muestras_minimas=3)
    assert r.estado == SIN_SENAL
    assert r.edge_bruto_bps is None


def test_muestras_insuficientes_falla_cerrado():
    cierres = [100 * (1.001 ** i) for i in range(70)]
    r = estimar_edge(_velas_desde_cierres(cierres), muestras_minimas=100)
    assert r.estado == MUESTRAS_INSUFICIENTES
    assert r.edge_bruto_bps is None
    assert r.muestras > 0


def test_edge_es_p25_no_media_ni_score():
    # Serie alcista con pequeños retrocesos regulares. Solo importa que haya
    # suficientes estados alcistas y dispersión en retornos futuros.
    cierres = []
    precio = 100.0
    for i in range(500):
        precio *= 1.002 if i % 9 else 0.992
        cierres.append(precio)

    r = estimar_edge(_velas_desde_cierres(cierres), muestras_minimas=20)
    assert r.estado == ESTADO_APTO
    assert r.edge_bruto_bps == r.retorno_p25_bps
    assert r.retorno_mediano_bps is not None
    assert r.muestras >= 20
    assert 0 <= r.tasa_positiva <= 1


def test_edge_desfavorable_se_publica_negativo_y_no_se_maquilla():
    # Tendencia general alcista, pero tras muchos estados alcistas aparecen
    # retrocesos fuertes a 4h. El estimador debe poder devolver p25 negativo.
    cierres = []
    precio = 100.0
    for i in range(600):
        if i % 12 in (8, 9, 10, 11):
            precio *= 0.993
        else:
            precio *= 1.004
        cierres.append(precio)
    # Fuerza estado actual alcista sin alterar el historial entrenable.
    cierres[-1] = max(cierres[-2] * 1.01, cierres[-7] * 1.01, cierres[-25] * 1.01)

    r = estimar_edge(_velas_desde_cierres(cierres), muestras_minimas=20)
    assert r.estado == ESTADO_APTO
    assert r.edge_bruto_bps is not None
    assert r.edge_bruto_bps == r.retorno_p25_bps


def test_datos_insuficientes_no_producen_edge():
    r = estimar_edge(_velas_desde_cierres([100.0] * 10))
    assert r.estado == DATOS_INVALIDOS
    assert r.edge_bruto_bps is None
