"""Independent device-key authenticated VPN requests and administrator grants."""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vpn_enrollments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('device_id', sa.String(36), sa.ForeignKey('devices.id'), unique=True, nullable=False),
        sa.Column('installation_id', sa.String(36), sa.ForeignKey('installations.id'), nullable=False),
        sa.Column('key_id', sa.String(36), sa.ForeignKey('device_keys.id'), nullable=False),
        sa.Column('public_key', sa.String(44), unique=True, nullable=False),
        sa.Column('request', sa.JSON(), nullable=False),
        sa.Column('registration', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','ARCHIVED')"))


def downgrade():
    op.drop_table('vpn_enrollments')
