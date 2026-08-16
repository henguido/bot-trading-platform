"""
Telemetria de llamadas al LLM  (Fase BOT 2.0-01).

Mide, no optimiza. Esta fase no cambia decisiones de trading, ni el prompt de
negocio, ni el modelo.

PRINCIPIO DE ROBUSTEZ
    Un fallo de telemetria NUNCA puede convertirse en una operacion de trading.
    `registrar_llamada` no propaga excepciones: si la persistencia falla, lo
    registra por consola y sigue. Y no devuelve ningun valor del que dependa
    una decision, precisamente para que no pueda influir en ella.

PRIVACIDAD
    NO se almacena el prompt, ni la respuesta, ni cabeceras, ni API keys.
    Solo tamanos en caracteres y contadores de tokens. DecisionAudit ya
    conserva el contexto de negocio; duplicarlo aqui seria crear una segunda
    fuga de informacion.

COSTO
    Ver `calcular_costo_usd`. No hay tarifas hardcodeadas.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


def nuevo_call_id() -> str:
    """Identificador unico de llamada, para correlacionar sin exponer nada."""
    return f"llm-{uuid.uuid4().hex}"


@dataclass
class MetricasLlamadaLLM:
    """Todo lo que se mide de una llamada. Sin contenido, solo magnitudes."""

    operacion: str                       # origen: analyze_multiple_assets, ...
    proveedor: str = "openai"
    modelo_solicitado: Optional[str] = None
    modelo_respuesta: Optional[str] = None

    call_id: str = field(default_factory=nuevo_call_id)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    http_status: Optional[int] = None
    exito: bool = False
    tipo_error: Optional[str] = None     # clase de la excepcion o motivo corto
    latencia_ms: Optional[int] = None

    prompt_chars: Optional[int] = None
    respuesta_chars: Optional[int] = None

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    n_activos: Optional[int] = None
    n_market_pairs: Optional[int] = None
    n_noticias: Optional[int] = None
    ciclo: Optional[int] = None          # permite agregar por ciclo

    def aplicar_usage(self, data) -> None:
        """
        Extrae `usage` de la respuesta si viene. Si no viene, los contadores
        quedan en None: desconocido no es cero.
        """
        if not isinstance(data, dict):
            return
        self.modelo_respuesta = data.get("model") or self.modelo_respuesta
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        for destino, clave in (("prompt_tokens", "prompt_tokens"),
                               ("completion_tokens", "completion_tokens"),
                               ("total_tokens", "total_tokens")):
            valor = usage.get(clave)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            setattr(self, destino, int(valor))


# ─────────────────────────────────────────────────────────────────────────────
# COSTO
#
# Las tarifas de los proveedores cambian y dependen del modelo. Hardcodearlas
# significaria que el costo historico se recalcula solo -y mal- cada vez que el
# proveedor ajusta precios, sin que quede rastro de que tarifa se aplico.
#
# Por eso:
#   - Si NO hay tarifas configuradas, el costo es NO_DISPONIBLE, nunca 0.0.
#   - Si las hay, se aplican y se PERSISTEN junto a la fila, de modo que el
#     calculo queda auditable aunque la tarifa cambie despues.
#
# Configuracion (USD por MILLON de tokens):
#   LLM_PRECIO_INPUT_USD_POR_1M
#   LLM_PRECIO_OUTPUT_USD_POR_1M
# ─────────────────────────────────────────────────────────────────────────────
def calcular_costo_usd(prompt_tokens, completion_tokens, *,
                       precio_input_por_1m=None, precio_output_por_1m=None):
    """
    Devuelve (costo_usd, estado, detalle).

    costo_usd es None -y estado NO_DISPONIBLE- si faltan tokens o tarifas.
    Nunca devuelve 0.0 por desconocimiento.
    """
    if precio_input_por_1m is None or precio_output_por_1m is None:
        return None, NO_DISPONIBLE, (
            "sin tarifas configuradas (LLM_PRECIO_INPUT_USD_POR_1M / "
            "LLM_PRECIO_OUTPUT_USD_POR_1M)")
    if prompt_tokens is None or completion_tokens is None:
        return None, NO_DISPONIBLE, "la respuesta no informo usage de tokens"

    costo = (prompt_tokens / 1_000_000.0) * float(precio_input_por_1m) \
        + (completion_tokens / 1_000_000.0) * float(precio_output_por_1m)
    detalle = (f"in={precio_input_por_1m}/1M out={precio_output_por_1m}/1M")
    return costo, DISPONIBLE, detalle


def registrar_llamada(metricas: MetricasLlamadaLLM, *, session_factory=None,
                      config=None) -> bool:
    """
    Persiste las metricas. Devuelve True si se guardo, False si no.

    NUNCA lanza. Un fallo de telemetria no puede alterar el comportamiento de
    trading: se registra el problema y se continua. El valor devuelto es
    informativo y ningun camino de decision debe depender de el.
    """
    try:
        if config is None:
            from backend.config import settings as config
        if session_factory is None:
            from backend.app.database import SessionLocal as session_factory

        from backend.app import models

        costo, estado_costo, detalle = calcular_costo_usd(
            metricas.prompt_tokens, metricas.completion_tokens,
            precio_input_por_1m=getattr(config, "LLM_PRECIO_INPUT_USD_POR_1M", None),
            precio_output_por_1m=getattr(config, "LLM_PRECIO_OUTPUT_USD_POR_1M", None),
        )

        fila = models.LlmCallAudit(
            call_id=metricas.call_id, timestamp=metricas.timestamp,
            proveedor=metricas.proveedor, operacion=metricas.operacion,
            modelo_solicitado=metricas.modelo_solicitado,
            modelo_respuesta=metricas.modelo_respuesta,
            http_status=metricas.http_status, exito=bool(metricas.exito),
            tipo_error=metricas.tipo_error, latencia_ms=metricas.latencia_ms,
            prompt_chars=metricas.prompt_chars,
            respuesta_chars=metricas.respuesta_chars,
            prompt_tokens=metricas.prompt_tokens,
            completion_tokens=metricas.completion_tokens,
            total_tokens=metricas.total_tokens,
            n_activos=metricas.n_activos, n_market_pairs=metricas.n_market_pairs,
            n_noticias=metricas.n_noticias, ciclo=metricas.ciclo,
            costo_usd=costo, costo_status=estado_costo, costo_detalle=detalle,
        )
        with session_factory() as db:
            db.add(fila)
            db.commit()
        return True
    except Exception as e:
        # Deliberadamente amplio: la telemetria jamas debe tumbar el bot ni
        # cambiar una decision. Se informa y se sigue.
        print(f"[TELEMETRIA] No se pudo registrar la llamada al LLM "
              f"({type(e).__name__}: {e}). El comportamiento de trading no cambia.")
        return False
