"""baseline: esquema existente previo al sistema de ordenes

Representa EXACTAMENTE el esquema que las bases actuales ya tienen, creado en su
dia por models.Base.metadata.create_all(). Escrita a mano, no autogenerada, para
que coincida con lo que hay en disco y no con lo que los modelos digan manana.

USO
  BD existente que ya coincide con este esquema:
      alembic stamp 0001_baseline
      alembic upgrade head
      (stamp SOLO de esta revision; nunca `stamp head`, que saltaria 0002)

  BD nueva y vacia:
      alembic upgrade head

Revision ID: 0001_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        sa.Column("tipo_cuenta", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usuarios_id", "usuarios", ["id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "activos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("simbolo", sa.String(), nullable=True),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("tipo", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activos_id", "activos", ["id"])
    op.create_index("ix_activos_simbolo", "activos", ["simbolo"], unique=True)

    op.create_table(
        "portafolios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("tipo_activo", sa.String(), nullable=False),
        sa.Column("balance_inicial", sa.Float(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portafolios_id", "portafolios", ["id"])

    op.create_table(
        "transacciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portafolio_id", sa.Integer(), nullable=True),
        sa.Column("activo_id", sa.Integer(), nullable=True),
        sa.Column("tipo_operacion", sa.String(), nullable=True),
        sa.Column("cantidad", sa.Float(), nullable=True),
        sa.Column("precio", sa.Float(), nullable=True),
        sa.Column("fecha_operacion", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["activo_id"], ["activos.id"]),
        sa.ForeignKeyConstraint(["portafolio_id"], ["portafolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transacciones_id", "transacciones", ["id"])

    op.create_table(
        "decision_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("sentimiento", sa.String(), nullable=True),
        sa.Column("noticias", sa.Text(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("decision_gpt", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_audit_id", "decision_audit", ["id"])
    op.create_index("ix_decision_audit_symbol", "decision_audit", ["symbol"])


def downgrade() -> None:
    op.drop_table("decision_audit")
    op.drop_table("transacciones")
    op.drop_table("portafolios")
    op.drop_table("activos")
    op.drop_table("usuarios")
