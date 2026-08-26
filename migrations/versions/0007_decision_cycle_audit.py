"""auditoria agregada del embudo de decision por ciclo

Una fila por ciclo y usuario. No guarda prompts, noticias, respuestas del LLM
ni credenciales: solo un JSON de contadores/codigos de motivo ya derivados por
el bot. Permite explicar por que un ciclo termino en NO TRADE sin generar una
fila por cada simbolo descartado.

Revision ID: 0007_decision_cycle_audit
Revises: 0006_paper_ledger
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_decision_cycle_audit"
down_revision = "0006_paper_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_cycle_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("ciclo_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("modo", sa.String(length=16), nullable=False),
        sa.Column("decision_engine", sa.String(length=32), nullable=False),
        sa.Column("resumen_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ciclo_id", name="uq_decision_cycle_audit_ciclo_id"),
    )
    op.create_index("ix_decision_cycle_audit_id", "decision_cycle_audit", ["id"])
    op.create_index("ix_decision_cycle_audit_usuario_id", "decision_cycle_audit", ["usuario_id"])
    op.create_index("ix_decision_cycle_audit_ciclo_id", "decision_cycle_audit", ["ciclo_id"])
    op.create_index("ix_decision_cycle_audit_timestamp", "decision_cycle_audit", ["timestamp"])


def downgrade() -> None:
    op.drop_table("decision_cycle_audit")
