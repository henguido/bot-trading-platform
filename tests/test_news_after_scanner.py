"""Guardas de arquitectura para noticias/contexto del ciclo de trading.

Las noticias no participan en elegibilidad ni scanner. Solo se consultan cuando
ya existen finalistas para el motor de decision, evitando trafico externo inutil
en ciclos que terminan antes del LLM.
"""
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1] / "backend" / "main.py"


def test_noticias_se_consultan_despues_de_confirmar_finalistas():
    fuente = MAIN.read_text(encoding="utf-8")

    scanner = fuente.index("activos_para_gpt = scanner.aplicar(")
    sin_candidatos = fuente.index("if not activos_para_gpt:", scanner)
    consulta_noticias = fuente.index(
        "news_connector.obtener_noticias_combinadas(6, medidor=medidor)",
        sin_candidatos,
    )
    decision = fuente.index("decision_engine.decidir(", consulta_noticias)

    assert scanner < sin_candidatos < consulta_noticias < decision


def test_no_hay_consulta_de_noticias_antes_del_scanner():
    fuente = MAIN.read_text(encoding="utf-8")
    scanner = fuente.index("activos_para_gpt = scanner.aplicar(")
    prefijo = fuente[:scanner]

    assert "news_connector.obtener_noticias_combinadas" not in prefijo


def test_contexto_degradado_sigue_siendo_explicito_si_no_hay_noticias():
    fuente = MAIN.read_text(encoding="utf-8")

    assert 'noticias_str = "\\n".join(textos) if textos else "No hay noticias disponibles"' in fuente
    assert 'sentimiento = "NO DISPONIBLE"' in fuente
