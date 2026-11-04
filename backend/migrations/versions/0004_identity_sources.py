"""Add non-unique domain links, provenance, import history and explicit decisions.
The legacy unique businesses.domain column remains untouched for compatibility.
"""
from alembic import op
import sqlalchemy as sa
import uuid
import urllib.parse
revision='0004_identity_sources'
down_revision='0003_research_history'
branch_labels=None
depends_on=None

def upgrade():
    guard=op.create_table('identity_guard',sa.Column('id',sa.String(20),primary_key=True),sa.Column('counter',sa.Integer(),nullable=False))
    op.get_bind().execute(guard.insert().values(id='global',counter=0))
    domains=op.create_table('business_domains',
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id'),primary_key=True),
        sa.Column('domain',sa.String(253),nullable=False))
    op.create_index('ix_business_domains_domain','business_domains',['domain'],unique=False)
    batches=op.create_table('import_batches',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('original_csv',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('import_candidates',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('batch_id',sa.String(36),sa.ForeignKey('import_batches.id'),nullable=False),
        sa.Column('row_number',sa.Integer(),nullable=False),
        sa.Column('raw_data',sa.Text(),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=True),
        sa.Column('review_id',sa.String(36),sa.ForeignKey('duplicate_reviews.id'),nullable=True),
        sa.Column('error',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    sources=op.create_table('business_sources',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=False),
        sa.Column('source',sa.String(2048),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('candidate_id',sa.String(36),sa.ForeignKey('import_candidates.id'),nullable=True),
        sa.Column('review_id',sa.String(36),sa.ForeignKey('duplicate_reviews.id'),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('business_relationships',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('subject_business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=False),
        sa.Column('related_business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=False),
        sa.Column('relation',sa.String(32),nullable=False),
        sa.Column('review_id',sa.String(36),sa.ForeignKey('duplicate_reviews.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('review_resolutions',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('review_id',sa.String(36),sa.ForeignKey('duplicate_reviews.id'),nullable=False),
        sa.Column('decision',sa.String(32),nullable=False),
        sa.Column('matched_business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=True),
        sa.Column('result_business_id',sa.String(36),sa.ForeignKey('businesses.id'),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    businesses=sa.table('businesses',sa.column('id',sa.String),sa.column('domain',sa.String),sa.column('website',sa.String),sa.column('source',sa.String),sa.column('created_at',sa.DateTime(timezone=True)))
    for row in op.get_bind().execute(sa.select(businesses)).all():
        # Copy legacy values. Keep the original record and source unchanged.
        domain=row.domain
        if not domain and row.website:
            try:
                host=urllib.parse.urlsplit(row.website).hostname
                if host:
                    domain=host.lower().rstrip('.').encode('idna').decode('ascii')
                    if domain.startswith('www.'): domain=domain[4:]
                    if len(domain)>253: domain=None
            except (ValueError,UnicodeError): domain=None
        if domain: op.get_bind().execute(domains.insert().values(business_id=row.id,domain=domain))
        op.get_bind().execute(sources.insert().values(id=str(uuid.uuid4()),business_id=row.id,source=row.source or 'Legacy source not provided',kind='legacy',candidate_id=None,review_id=None,created_at=row.created_at))

def downgrade():
    for table in ('review_resolutions','business_relationships','business_sources','import_candidates','import_batches','business_domains'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar():
            raise RuntimeError('Cannot downgrade: domain, provenance, review or import history would be lost.')
    for table in ('review_resolutions','business_relationships','business_sources','import_candidates','import_batches'):
        op.drop_table(table)
    op.drop_index('ix_business_domains_domain',table_name='business_domains')
    op.drop_table('business_domains')
    op.drop_table('identity_guard')
