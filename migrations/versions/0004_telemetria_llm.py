"""telemetria de llamadas al LLM

Fase BOT 2.0-01. Tabla independiente de decision_audit: una llamada al LLM
analiza N activos y produce N decisiones, asi que la cardinalidad no coincide.
Ademas aqui no se guarda contenido, solo magnitudes.

Solo AGREGA una tabla. No altera ni borra nada existente.
Compatible con SQLite y PostgreSQL: tipos genericos, sin extensiones.

Revision ID: 0004_telemetria
Revises: 0003_reconciliacion
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_telemetria"
down_revision = "0003_reconciliacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_call_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("proveedor", sa.String(length=32), nullable=False),
        sa.Column("operacion", sa.String(length=64), nullable=False),
        sa.Column("modelo_solicitado", sa.String(length=128), nullable=True),
        sa.Column("modelo_respuesta", sa.String(length=128), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("exito", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tipo_error", sa.String(length=128), nullable=True),
        sa.Column("latencia_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_chars", sa.Integer(), nullable=True),
        sa.Column("respuesta_chars", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("n_activos", sa.Integer(), nullable=True),
        sa.Column("n_market_pairs", sa.Integer(), nullable=True),
        sa.Column("n_noticias", sa.Integer(), nullable=True),
        sa.Column("ciclo", sa.Integer(), nullable=True),
        # NULL cuando no se puede calcular. Nunca 0.0 por desconocimiento.
        sa.Column("costo_usd", sa.Float(), nullable=True),
        sa.Column("costo_status", sa.String(length=24), nullable=False,
                  server_default="NO_DISPONIBLE"),
        sa.Column("costo_detalle", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_call_audit_id", "llm_call_audit", ["id"])
    op.create_index("ix_llm_call_audit_call_id", "llm_call_audit",
                    ["call_id"], unique=True)
    op.create_index("ix_llm_call_audit_timestamp", "llm_call_audit", ["timestamp"])
    op.create_index("ix_llm_call_audit_operacion", "llm_call_audit", ["operacion"])
    op.create_index("ix_llm_call_audit_ciclo", "llm_call_audit", ["ciclo"])


def downgrade() -> None:
    op.drop_table("llm_call_audit")
