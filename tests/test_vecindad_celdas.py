"""La enumeración optimizada debe ser idéntica al filtro brute-force."""
from itertools import product

import pytest

from backend.economia.edge_celdas import (
    DiscretizacionFeature,
    _claves_en_radio,
    _distancia_manhattan_celda,
)


def discretizaciones(n_bins=6):
    # n_bins celdas => n_bins-1 cortes => índices 0..n_bins-1.
    cortes = tuple(float(i) for i in range(1, n_bins))
    return tuple(
        DiscretizacionFeature(f"f{i}", 0.0, float(n_bins), cortes)
        for i in range(4)
    )


@pytest.mark.parametrize("clave", [(0, 0, 0, 0), (2, 3, 1, 4), (5, 5, 5, 5)])
@pytest.mark.parametrize("radio", [0, 1, 2])
def test_enumeracion_coincide_exactamente_con_bruteforce(clave, radio):
    ds = discretizaciones(6)
    todas = tuple(product(range(6), repeat=4))
    esperadas = tuple(sorted(
        k for k in todas if _distancia_manhattan_celda(clave, k) <= radio
    ))
    assert _claves_en_radio(clave, radio, ds) == esperadas


def test_radio_dos_en_celda_interior_es_pequeno_frente_a_todo_el_mapa():
    ds = discretizaciones(6)
    vecinas = _claves_en_radio((2, 2, 2, 2), 2, ds)
    assert len(vecinas) == 41
    assert len(vecinas) < 6 ** 4 / 20


@pytest.mark.parametrize("radio", [-1, 1.5, True])
def test_radio_invalido_falla_cerrado(radio):
    with pytest.raises(ValueError):
        _claves_en_radio((1, 1, 1, 1), radio, discretizaciones())
