"""Add a non-destructive duplicate review queue."""
from alembic import op
import sqlalchemy as sa
revision='0002_duplicate_reviews'
down_revision='0001_baseline'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('duplicate_reviews',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('incoming',sa.Text(),nullable=False),
        sa.Column('matches',sa.Text(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('resolved_at',sa.DateTime(timezone=True),nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM duplicate_reviews')).scalar():
        raise RuntimeError('Cannot downgrade: duplicate review records would be lost. Back up and retain them first.')
    op.drop_table('duplicate_reviews')
