"""Retired VPN generations for bidirectional deletion and fresh enrollment."""
import sqlalchemy as sa
from alembic import op
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vpn_deletions',
        sa.Column('request_id',sa.String(36),primary_key=True),
        sa.Column('device_id',sa.String(36),sa.ForeignKey('devices.id'),nullable=False),
        sa.Column('installation_id',sa.String(36),sa.ForeignKey('installations.id'),nullable=False),
        sa.Column('key_id',sa.String(36),sa.ForeignKey('device_keys.id'),nullable=False),
        sa.Column('public_key',sa.String(44),nullable=False),
        sa.Column('request',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_vpn_deletions_device_id','vpn_deletions',['device_id'])
    op.create_index('ix_vpn_deletions_public_key','vpn_deletions',['public_key'])


def downgrade():
    op.drop_table('vpn_deletions')
