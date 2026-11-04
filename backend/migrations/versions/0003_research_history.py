"""Retain research history and copy all legacy reports without modifying them."""
from alembic import op
import sqlalchemy as sa
import uuid
revision='0003_research_history'
down_revision='0002_duplicate_reviews'
branch_labels=None
depends_on=None

def upgrade():
    history=op.create_table('research_history',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=False),
        sa.Column('report',sa.Text(),nullable=False),
        sa.Column('collected_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False))
    op.create_index('ix_research_history_business_id','research_history',['business_id'])
    businesses=sa.table('businesses',sa.column('id',sa.String),sa.column('report',sa.Text),sa.column('researched_at',sa.DateTime(timezone=True)),sa.column('created_at',sa.DateTime(timezone=True)))
    rows=op.get_bind().execute(sa.select(businesses.c.id,businesses.c.report,businesses.c.researched_at,businesses.c.created_at).where(businesses.c.report!='')).all()
    for row in rows:
        op.get_bind().execute(history.insert().values(id=str(uuid.uuid4()),business_id=row.id,report=row.report,collected_at=row.researched_at or row.created_at,kind='legacy'))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM research_history')).scalar():
        raise RuntimeError('Cannot downgrade: research history would be lost. Back up and retain it first.')
    op.drop_index('ix_research_history_business_id',table_name='research_history')
    op.drop_table('research_history')
