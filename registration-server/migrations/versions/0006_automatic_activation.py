"""Explicit administrator approval for activation on the next signed device sync."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "activation_tokens",
        sa.Column("automatic_activation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("activation_tokens", "automatic_activation")
