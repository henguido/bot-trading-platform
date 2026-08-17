from sqlalchemy import (Column, Integer, String, Float, ForeignKey, DateTime,
                        Boolean, UniqueConstraint)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base
from sqlalchemy import Text

class User(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    tipo_cuenta = Column(String, default="free")

    portafolios = relationship("Portfolio", back_populates="usuario")

class Portfolio(Base):
    __tablename__ = "portafolios"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    nombre = Column(String, nullable=False)
    tipo_activo = Column(String, nullable=False)
    balance_inicial = Column(Float, default=0.0)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("User", back_populates="portafolios")
    transacciones = relationship("Transaction", back_populates="portafolio")

class Asset(Base):
    __tablename__ = "activos"
    id = Column(Integer, primary_key=True, index=True)
    simbolo = Column(String, unique=True, index=True)
    nombre = Column(String)
    tipo = Column(String)

class Transaction(Base):
    __tablename__ = "transacciones"
    id = Column(Integer, primary_key=True, index=True)
    portafolio_id = Column(Integer, ForeignKey("portafolios.id"))
    activo_id = Column(Integer, ForeignKey("activos.id"))
    tipo_operacion = Column(String)  # Compra o Venta
    cantidad = Column(Float)
    precio = Column(Float)
    fecha_operacion = Column(DateTime, default=datetime.utcnow)
    # Origen economico de la transaccion. UNIQUE para que un mismo fill no
    # pueda generar dos apuntes. NULL en las transacciones legacy, anteriores
    # al sistema de ordenes; UNIQUE admite multiples NULL.
    fill_id = Column(Integer, ForeignKey("fills.id"), unique=True, nullable=True)

    portafolio = relationship("Portfolio", back_populates="transacciones")
    activo = relationship("Asset")  # ✅ Añadir esta línea

class Orden(Base):
    """
    Intencion de operar. Se persiste ANTES de enviar nada al broker (P0-11).

    Es la unica forma de poder preguntar despues "que paso con ESTA orden"
    cuando se pierde la respuesta. `client_order_id` es UNIQUE: dos procesos no
    pueden registrar la misma orden, y reintentar no crea una segunda.
    """
    __tablename__ = "ordenes"

    id = Column(Integer, primary_key=True, index=True)
    client_order_id = Column(String(64), unique=True, nullable=False, index=True)
    broker = Column(String(32), nullable=False, default="binance")
    broker_order_id = Column(String(64), nullable=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    decision_audit_id = Column(Integer, ForeignKey("decision_audit.id"), nullable=True)

    symbol = Column(String(32), nullable=False, index=True)
    side = Column(String(8), nullable=False)          # BUY | SELL

    requested_base_quantity = Column(Float, nullable=True)
    requested_quote_amount = Column(Float, nullable=True)
    executed_base_quantity = Column(Float, nullable=False, default=0.0)
    executed_quote_amount = Column(Float, nullable=False, default=0.0)

    estado = Column(String(32), nullable=False, index=True)
    error = Column(Text, nullable=True)

    # Persistido a proposito: si viviera en memoria, reiniciar el proceso
    # reabriria los intentos y la orden nunca alcanzaria el estado de
    # reconciliacion manual (P0-17).
    intentos_reconciliacion = Column(Integer, default=0, nullable=False)
    ultimo_intento_en = Column(DateTime, nullable=True)
    creada_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    actualizada_en = Column(DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)

    fills = relationship("Fill", back_populates="orden")


class Fill(Base):
    """
    Ejecucion parcial o total confirmada por el broker.

    La identidad externa (broker, symbol, trade_id) es UNIQUE: procesar el mismo
    fill cien veces deja una sola fila. Es lo que hace idempotente al
    reconciliador a nivel de BASE DE DATOS, no solo de codigo Python.
    """
    __tablename__ = "fills"
    __table_args__ = (
        UniqueConstraint("broker", "symbol", "trade_id", name="uq_fill_externo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=False, index=True)

    broker = Column(String(32), nullable=False, default="binance")
    symbol = Column(String(32), nullable=False)
    trade_id = Column(String(64), nullable=False)

    price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    # Tal cual lo informa el broker. Nunca se deduce una tasa.
    commission = Column(Float, nullable=True)
    commission_asset = Column(String(16), nullable=True)

    registrado_en = Column(DateTime, default=datetime.utcnow, nullable=False)

    orden = relationship("Orden", back_populates="fills")


class LlmCallAudit(Base):
    """
    Metricas de UNA llamada al LLM. Tabla propia y no DecisionAudit porque la
    cardinalidad no coincide: una llamada analiza N activos y produce N
    decisiones. Ademas aqui NO se guarda contenido -ni prompt, ni respuesta, ni
    cabeceras, ni claves-, solo magnitudes.
    """
    __tablename__ = "llm_call_audit"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    proveedor = Column(String(32), nullable=False)
    operacion = Column(String(64), nullable=False, index=True)
    modelo_solicitado = Column(String(128))
    modelo_respuesta = Column(String(128))

    http_status = Column(Integer)
    exito = Column(Boolean, nullable=False, default=False)
    tipo_error = Column(String(128))
    latencia_ms = Column(Integer)

    prompt_chars = Column(Integer)
    respuesta_chars = Column(Integer)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)

    n_activos = Column(Integer)
    n_market_pairs = Column(Integer)
    n_noticias = Column(Integer)
    ciclo = Column(Integer, index=True)

    # NULL cuando no hay tarifas configuradas o falta usage. Nunca 0.0 por
    # desconocimiento. La tarifa aplicada se guarda para que el calculo siga
    # siendo auditable aunque el proveedor la cambie despues.
    costo_usd = Column(Float)
    costo_status = Column(String(24), nullable=False, default="NO_DISPONIBLE")
    costo_detalle = Column(String(255))

    # ── Fase BOT 2.0-02A · correlacion y diagnostico ─────────────────────────
    # Todas nullable: las filas escritas por 02-01 no las tienen y siguen
    # siendo validas.
    #
    # Permite cruzar el gasto del LLM con el trafico HTTP del MISMO recorrido
    # del bucle. `ciclo` (entero) no sirve para eso: se incrementa en cinco
    # ramas distintas y un recorrido puede incrementarlo varias veces o
    # ninguna.
    ciclo_id = Column(String(64), index=True)

    # Identificador que devuelve el proveedor. Es lo que hay que citar en una
    # reclamacion de soporte, y no revela nada del contenido.
    x_request_id = Column(String(64))

    # `error.type` / `error.code` del cuerpo de la respuesta. Distinguen un
    # 429 por cuota agotada de uno por exceso de ritmo, cosa que el codigo HTTP
    # por si solo no permite.
    #
    # 🔒 `error.message` NO se guarda NUNCA: puede citar el prompt.
    error_type = Column(String(64))
    error_code = Column(String(64))

    # Cabeceras x-ratelimit-*. Sin ellas, un 429 no dice si el limite es de
    # peticiones o de tokens, ni cuando se recupera.
    # Los limites y restantes son enteros documentados; se parsean de forma
    # defensiva y quedan a NULL si no lo son (desconocido no es cero).
    # Los `reset` llegan como duracion ("6ms", "1m0s"): se guardan literales
    # para no perder informacion al interpretarlos.
    rl_limit_requests = Column(Integer)
    rl_limit_tokens = Column(Integer)
    rl_remaining_requests = Column(Integer)
    rl_remaining_tokens = Column(Integer)
    rl_reset_requests = Column(String(32))
    rl_reset_tokens = Column(String(32))


class CicloHttpAudit(Base):
    """
    Trafico HTTP de UN ciclo, agregado por (ciclo_id, proveedor, operacion).

    Por que agregado y no por peticion: a ~1.895 peticiones por ciclo serian
    ~4,1 M de filas al ano frente a ~15 k agregadas, para responder exactamente
    a las mismas preguntas.

    Por que tabla propia y no `llm_call_audit`: aquella mide UNA llamada al
    LLM; esta mide N peticiones de mercado que ni siquiera tienen por que
    terminar en una llamada al LLM.

    NO se guarda ninguna URL, cabecera, cuerpo ni credencial: solo contadores,
    tiempos y codigos de estado.
    """
    __tablename__ = "ciclo_http_audit"

    # La cardinalidad del contrato -una fila por (ciclo_id, proveedor,
    # operacion)- la impone la BASE DE DATOS, no la agregacion en memoria. Si
    # un medidor se volcara dos veces, o dos procesos midieran el mismo ciclo,
    # el segundo INSERT se rechaza en vez de duplicar metricas. Portable:
    # SQLite y PostgreSQL soportan UNIQUE multicolumna sin extensiones.
    __table_args__ = (
        UniqueConstraint("ciclo_id", "proveedor", "operacion",
                         name="uq_ciclo_http_audit_ciclo_proveedor_operacion"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Identidad TELEMETRICA de la iteracion. No participa en ninguna decision.
    ciclo_id = Column(String(64), nullable=False, index=True)
    # Contador legacy, solo diagnostico. No es una identidad fiable.
    ciclo_num = Column(Integer)

    proveedor = Column(String(32), nullable=False)
    operacion = Column(String(64), nullable=False, index=True)

    n_requests = Column(Integer, nullable=False, default=0)
    n_ok = Column(Integer, nullable=False, default=0)
    n_error = Column(Integer, nullable=False, default=0)

    latencia_total_ms = Column(Integer)
    latencia_max_ms = Column(Integer)
    # `latencia_media_ms` NO se persiste: es derivable de las dos anteriores y
    # duplicar estado invita a inconsistencias.

    # Tiempo de PARED de la operacion. Puede diferir de la suma de latencias:
    # esta ignora el trabajo local entre peticiones.
    duracion_ms = Column(Integer)

    # Significado dependiente de la operacion; ver telemetria_http.
    n_elementos = Column(Integer)

    # JSON serializado, p.ej. {"200": 488, "429": 2}. Text y no JSONB para que
    # el mismo esquema valga en SQLite y en PostgreSQL sin extensiones.
    status_counts = Column(Text)

    inicio = Column(DateTime)
    fin = Column(DateTime)


class DecisionAudit(Base):
    __tablename__ = "decision_audit"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    quantity = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sentimiento = Column(String)
    noticias = Column(Text)
    risk_score = Column(Float)
    decision_gpt = Column(Text)  # JSON como texto por simplicidad
