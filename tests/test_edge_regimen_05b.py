from backend.economia.edge_empirico import VelaCerrada
from backend.economia.edge_regimen_05b import (
    MUESTRAS_INSUFICIENTES,
    REGIMEN_CONTINUACION,
    REGIMEN_PULLBACK,
    SIN_SENAL,
    estimar_edge_regimen,
)


def _velas(cierres):
    out = []
    for i, c in enumerate(cierres):
        open_ms = i * 3_600_000
        out.append(VelaCerrada(open_ms, open_ms + 3_599_999, float(c)))
    return out


def test_sin_senal_si_tendencia_24h_no_es_positiva():
    cierres = [100.0] * 80
    e = estimar_edge_regimen(_velas(cierres), muestras_minimas=1)
    assert e.estado == SIN_SENAL
    assert e.regimen is None


def test_identifica_continuacion_y_publica_p25():
    # Tendencia creciente persistente: todas las ocurrencias del regimen tienen
    # retorno futuro positivo. Se usa muestra minima baja para probar la logica,
    # no para cambiar el parametro de produccion.
    cierres = [100.0 + i for i in range(120)]
    e = estimar_edge_regimen(_velas(cierres), muestras_minimas=3)
    assert e.regimen == REGIMEN_CONTINUACION
    assert e.utilizable
    assert e.muestras >= 3
    assert e.edge_bruto_bps > 0
    assert e.retorno_p25_bps == e.edge_bruto_bps


def test_identifica_pullback_dentro_de_tendencia_24h():
    # Serie con escalones alcistas y retrocesos cortos. El ultimo punto queda
    # debajo de 6h atras pero por encima de 24h atras.
    cierres = []
    precio = 100.0
    for i in range(160):
        ciclo = i % 16
        if ciclo < 10:
            precio += 1.0
        else:
            precio -= 0.7
        cierres.append(precio)
    # Fuerza un pullback actual sin romper la tendencia larga.
    cierres[-1] = cierres[-7] * 0.995
    assert cierres[-1] > cierres[-25]
    e = estimar_edge_regimen(_velas(cierres), muestras_minimas=1)
    assert e.regimen == REGIMEN_PULLBACK
    assert e.estado in {"APTO", MUESTRAS_INSUFICIENTES}


def test_no_convierte_muestras_insuficientes_en_edge():
    cierres = [100.0 + i * 0.1 for i in range(40)]
    e = estimar_edge_regimen(_velas(cierres), muestras_minimas=100)
    assert e.estado == MUESTRAS_INSUFICIENTES
    assert e.edge_bruto_bps is None
