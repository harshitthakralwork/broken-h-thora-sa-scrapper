"""Shared crawler leases and persistent per-host pacing; no existing data changes."""
from alembic import op
import sqlalchemy as sa
revision='0005_crawler_safety'
down_revision='0004_identity_sources'
branch_labels=None
depends_on=None

def upgrade():
    control=op.create_table('crawler_control',sa.Column('id',sa.String(20),primary_key=True),sa.Column('counter',sa.Integer(),nullable=False))
    op.get_bind().execute(control.insert().values(id='global',counter=0))
    op.create_table('crawler_leases',sa.Column('id',sa.String(36),primary_key=True),sa.Column('expires_at',sa.Float(),nullable=False))
    op.create_table('crawler_host_limits',sa.Column('host',sa.String(253),primary_key=True),sa.Column('next_allowed',sa.Float(),nullable=False),sa.Column('owner',sa.String(36),nullable=True),sa.Column('active_until',sa.Float(),nullable=False))

def downgrade():
    for table in ('crawler_leases','crawler_host_limits'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar():
            raise RuntimeError('Cannot downgrade: crawler coordination state would be lost.')
    op.drop_table('crawler_host_limits')
    op.drop_table('crawler_leases')
    op.drop_table('crawler_control')
