"""reconciliacion conservadora: contador de intentos persistido

P0-17. Para poder decidir si los intentos automaticos de reconciliacion se
agotaron, el contador debe sobrevivir a un reinicio del proceso: si viviera en
memoria, reiniciar reabriria intentos indefinidamente y la orden nunca llegaria
a marcarse como RECONCILIACION_MANUAL_REQUERIDA.

Solo AGREGA columnas nullable / con default. No altera ni borra datos.

Revision ID: 0003_reconciliacion
Revises: 0002_ordenes
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_reconciliacion"
down_revision = "0002_ordenes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ordenes") as batch:
        batch.add_column(sa.Column("intentos_reconciliacion", sa.Integer(),
                                   nullable=False, server_default="0"))
        batch.add_column(sa.Column("ultimo_intento_en", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ordenes") as batch:
        batch.drop_column("ultimo_intento_en")
        batch.drop_column("intentos_reconciliacion")
