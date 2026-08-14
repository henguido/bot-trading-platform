"""ciclo de vida de ordenes: ordenes, fills y trazabilidad

Anade el sistema que cierra P0-10 (estados inciertos), P0-11 (identidad e
idempotencia) y P0-14 (reconciliacion).

Solo AGREGA: dos tablas nuevas y una columna nullable en transacciones. No
altera ni borra datos existentes, asi que es segura sobre bases con historico.

Revision ID: 0002_ordenes
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_ordenes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ordenes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("decision_audit_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("requested_base_quantity", sa.Float(), nullable=True),
        sa.Column("requested_quote_amount", sa.Float(), nullable=True),
        sa.Column("executed_base_quantity", sa.Float(), nullable=False,
                  server_default="0"),
        sa.Column("executed_quote_amount", sa.Float(), nullable=False,
                  server_default="0"),
        sa.Column("estado", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creada_en", sa.DateTime(), nullable=False),
        sa.Column("actualizada_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["decision_audit_id"], ["decision_audit.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ordenes_id", "ordenes", ["id"])
    # La identidad de la orden. Sin esto no hay idempotencia posible.
    op.create_index("ix_ordenes_client_order_id", "ordenes",
                    ["client_order_id"], unique=True)
    op.create_index("ix_ordenes_broker_order_id", "ordenes", ["broker_order_id"])
    op.create_index("ix_ordenes_symbol", "ordenes", ["symbol"])
    op.create_index("ix_ordenes_estado", "ordenes", ["estado"])
    op.create_index("ix_ordenes_usuario_id", "ordenes", ["usuario_id"])

    op.create_table(
        "fills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_id", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("commission_asset", sa.String(length=16), nullable=True),
        sa.Column("registrado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["orden_id"], ["ordenes.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Identidad externa del fill: reconciliar 100 veces deja una sola fila.
        sa.UniqueConstraint("broker", "symbol", "trade_id", name="uq_fill_externo"),
    )
    op.create_index("ix_fills_id", "fills", ["id"])
    op.create_index("ix_fills_orden_id", "fills", ["orden_id"])

    # Enlace fill -> transaccion. Nullable por las transacciones legacy; UNIQUE
    # para que un fill no pueda generar dos apuntes contables.
    with op.batch_alter_table("transacciones") as batch:
        batch.add_column(sa.Column("fill_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_transacciones_fill", "fills", ["fill_id"], ["id"])
        batch.create_unique_constraint("uq_transacciones_fill", ["fill_id"])


def downgrade() -> None:
    with op.batch_alter_table("transacciones") as batch:
        batch.drop_constraint("uq_transacciones_fill", type_="unique")
        batch.drop_constraint("fk_transacciones_fill", type_="foreignkey")
        batch.drop_column("fill_id")
    op.drop_table("fills")
    op.drop_table("ordenes")
