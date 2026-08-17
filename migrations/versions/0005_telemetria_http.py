"""telemetria HTTP del ciclo de mercado

Fase BOT 2.0-02A. Una sola migracion para los dos cambios de esquema que pide
la fase, porque forman una unidad funcional: sin la correlacion por `ciclo_id`
en `llm_call_audit` no se puede cruzar el gasto del LLM con el trafico HTTP del
mismo recorrido del bucle, que es justamente lo que 02A existe para medir.

  1. Crea `ciclo_http_audit`  (agregado por ciclo_id + proveedor + operacion).
  2. Amplia `llm_call_audit`  (correlacion, x-request-id, error.type/code y
     cabeceras x-ratelimit-*). Todas las columnas nuevas son NULLABLE, asi que
     las filas escritas por 02-01 siguen siendo validas sin tocarlas.

Solo AGREGA. No altera ni borra nada existente: ninguna columna cambia de tipo,
ningun dato se reescribe.

Compatible con SQLite y PostgreSQL: tipos genericos, sin extensiones.
`status_counts` es Text con JSON serializado y no JSONB por ese mismo motivo.

Revision ID: 0005_telemetria_http
Revises: 0004_telemetria
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_telemetria_http"
down_revision = "0004_telemetria"
branch_labels = None
depends_on = None


# Columnas anadidas a llm_call_audit. Todas nullable y sin server_default: un
# valor por defecto fabricaria informacion que esas filas nunca tuvieron.
COLUMNAS_LLM = (
    ("ciclo_id", sa.String(length=64)),
    ("x_request_id", sa.String(length=64)),
    # error.message NO se guarda NUNCA: puede citar el prompt.
    ("error_type", sa.String(length=64)),
    ("error_code", sa.String(length=64)),
    ("rl_limit_requests", sa.Integer()),
    ("rl_limit_tokens", sa.Integer()),
    ("rl_remaining_requests", sa.Integer()),
    ("rl_remaining_tokens", sa.Integer()),
    # Los `reset` llegan como duracion ("6ms", "1m0s"): literales, sin parsear.
    ("rl_reset_requests", sa.String(length=32)),
    ("rl_reset_tokens", sa.String(length=32)),
)


def upgrade() -> None:
    op.create_table(
        "ciclo_http_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        # Identidad TELEMETRICA de la iteracion del bucle.
        sa.Column("ciclo_id", sa.String(length=64), nullable=False),
        # Contador legacy `ciclo`, solo diagnostico: se incrementa en varias
        # ramas y no identifica un recorrido de forma fiable.
        sa.Column("ciclo_num", sa.Integer(), nullable=True),
        sa.Column("proveedor", sa.String(length=32), nullable=False),
        sa.Column("operacion", sa.String(length=64), nullable=False),
        sa.Column("n_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latencia_total_ms", sa.Integer(), nullable=True),
        sa.Column("latencia_max_ms", sa.Integer(), nullable=True),
        # latencia_media_ms NO se persiste: derivable de las dos anteriores.
        sa.Column("duracion_ms", sa.Integer(), nullable=True),
        sa.Column("n_elementos", sa.Integer(), nullable=True),
        # JSON serializado; Text para que el esquema valga igual en SQLite y
        # en PostgreSQL.
        sa.Column("status_counts", sa.Text(), nullable=True),
        sa.Column("inicio", sa.DateTime(), nullable=True),
        sa.Column("fin", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # La cardinalidad del contrato la impone la BASE, no la agregacion en
        # memoria: un volcado repetido o dos procesos midiendo el mismo ciclo
        # chocan aqui en vez de duplicar metricas. UNIQUE multicolumna es
        # portable entre SQLite y PostgreSQL, sin extensiones.
        sa.UniqueConstraint("ciclo_id", "proveedor", "operacion",
                            name="uq_ciclo_http_audit_ciclo_proveedor_operacion"),
    )
    op.create_index("ix_ciclo_http_audit_id", "ciclo_http_audit", ["id"])
    op.create_index("ix_ciclo_http_audit_ciclo_id", "ciclo_http_audit", ["ciclo_id"])
    op.create_index("ix_ciclo_http_audit_operacion", "ciclo_http_audit", ["operacion"])

    # ALTER TABLE ... ADD COLUMN es soportado nativamente por SQLite y
    # PostgreSQL. No se usa batch_alter_table aqui a proposito: en SQLite eso
    # RECREA la tabla, y recrear una tabla con historico para solo anadir
    # columnas es un riesgo innecesario.
    for nombre, tipo in COLUMNAS_LLM:
        op.add_column("llm_call_audit", sa.Column(nombre, tipo, nullable=True))

    op.create_index("ix_llm_call_audit_ciclo_id", "llm_call_audit", ["ciclo_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_audit_ciclo_id", table_name="llm_call_audit")
    # SQLite no soporta DROP COLUMN en versiones antiguas: en el camino de
    # vuelta si compensa el modo batch, que recrea la tabla.
    with op.batch_alter_table("llm_call_audit") as batch:
        for nombre, _ in COLUMNAS_LLM:
            batch.drop_column(nombre)

    op.drop_table("ciclo_http_audit")
