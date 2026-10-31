"""Customer contacts and reversible record archival; preserve existing bindings."""
import sqlalchemy as sa
from alembic import op
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customers',sa.Column('contact_name',sa.String(200),nullable=True))
    op.add_column('customers',sa.Column('email',sa.String(254),nullable=True))
    op.add_column('customers',sa.Column('phone',sa.String(40),nullable=True))
    op.add_column('customers',sa.Column('email_verified',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('customers',sa.Column('archived_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('devices',sa.Column('display_name',sa.String(120),nullable=True))
    op.add_column('devices',sa.Column('notes',sa.Text(),nullable=True))
    op.add_column('devices',sa.Column('archived_at',sa.DateTime(timezone=True),nullable=True))


def downgrade():
    for name in ['archived_at','notes','display_name']:
        op.drop_column('devices',name)
    for name in ['archived_at','email_verified','phone','email','contact_name']:
        op.drop_column('customers',name)
