"""Baseline matching the Foundation v0.1 businesses table."""
from alembic import op
import sqlalchemy as sa
revision='0001_baseline'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('businesses',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('name',sa.String(200),nullable=False),
        sa.Column('website',sa.String(2048),nullable=False),
        sa.Column('domain',sa.String(253),nullable=True,unique=True),
        sa.Column('industry',sa.String(120),nullable=False),
        sa.Column('location',sa.String(200),nullable=False),
        sa.Column('source',sa.String(2048),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('report',sa.Text(),nullable=False),
        sa.Column('researched_at',sa.DateTime(timezone=True),nullable=True))

def downgrade():
    raise RuntimeError('Baseline downgrade is disabled: it would delete business data. Restore a verified backup instead.')
