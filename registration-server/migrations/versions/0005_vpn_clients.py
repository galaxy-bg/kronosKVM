"""Desktop peers with public metadata only; keys generated in browser."""
import sqlalchemy as sa
from alembic import op
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vpn_clients',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('name',sa.String(120),nullable=False),
        sa.Column('owner_name',sa.String(200),nullable=True),
        sa.Column('email',sa.String(254),nullable=True),
        sa.Column('platform',sa.String(16),nullable=False),
        sa.Column('customer_id',sa.String(36),sa.ForeignKey('customers.id'),nullable=True),
        sa.Column('public_key',sa.String(44),unique=True,nullable=False),
        sa.Column('request',sa.JSON(),nullable=False),
        sa.Column('registration',sa.JSON(),nullable=True),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','DELETED')"),
        sa.CheckConstraint("platform IN ('WINDOWS','MACOS','LINUX','OTHER')"))


def downgrade():
    op.drop_table('vpn_clients')
