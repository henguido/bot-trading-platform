from scripts.shadow_scanner_attribution_05d import spearman


def test_spearman_detecta_relacion_monotona_positiva():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0


def test_spearman_detecta_relacion_monotona_negativa():
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_spearman_maneja_empates_sin_inventar_orden():
    valor = spearman([1, 1, 2, 2], [10, 20, 30, 40])
    assert valor is not None
    assert 0 < valor < 1


def test_spearman_no_publica_correlacion_con_menos_de_tres_puntos():
    assert spearman([1, 2], [3, 4]) is None
