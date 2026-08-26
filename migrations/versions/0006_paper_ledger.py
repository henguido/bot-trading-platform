"""ledger PAPER persistente y separado de LIVE

Release PAPER v1. Crea dos tablas nuevas, sin alterar ni reescribir ninguna
fila existente:

- paper_ledgers: capital inicial de un libro PAPER por usuario;
- paper_operaciones: journal append-only de fills simulados con fee/slippage.

El capital, las posiciones y el P&L se reconstruyen desde el journal; no se
persisten saldos derivados que puedan divergir. PAPER no reutiliza
`transacciones`, reservada al ledger confirmado de LIVE.

Compatible con SQLite y PostgreSQL: solo tipos y restricciones genericas.

Revision ID: 0006_paper_ledger
Revises: 0005_telemetria_http
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_paper_ledger"
down_revision = "0005_telemetria_http"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_ledgers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("initial_capital_usd", sa.Float(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", name="uq_paper_ledger_usuario"),
    )
    op.create_index("ix_paper_ledgers_id", "paper_ledgers", ["id"])
    op.create_index("ix_paper_ledgers_usuario_id", "paper_ledgers", ["usuario_id"])

    op.create_table(
        "paper_operaciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ledger_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("reference_price", sa.Float(), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=False),
        sa.Column("base_quantity", sa.Float(), nullable=False),
        sa.Column("quote_gross", sa.Float(), nullable=False),
        sa.Column("fee_usd", sa.Float(), nullable=False),
        sa.Column("quote_net", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("fee_taker_bps", sa.Float(), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=True),
        sa.Column("expected_edge_bps", sa.Float(), nullable=True),
        sa.Column("expected_cost_bps", sa.Float(), nullable=True),
        sa.Column("expected_net_bps", sa.Float(), nullable=True),
        sa.Column("creada_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ledger_id"], ["paper_ledgers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_operaciones_id", "paper_operaciones", ["id"])
    op.create_index("ix_paper_operaciones_ledger_id", "paper_operaciones", ["ledger_id"])
    op.create_index("ix_paper_operaciones_symbol", "paper_operaciones", ["symbol"])
    op.create_index("ix_paper_operaciones_creada_en", "paper_operaciones", ["creada_en"])


def downgrade() -> None:
    op.drop_table("paper_operaciones")
    op.drop_table("paper_ledgers")
