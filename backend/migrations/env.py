from alembic import context
from sqlalchemy import engine_from_config, pool
from app.main import Base, DATABASE_URL
config = context.config
config.set_main_option('sqlalchemy.url', DATABASE_URL.replace('%', '%%'))
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle':'named'})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        sqlite = connection.dialect.name == 'sqlite'
        if sqlite:
            # sqlite3 otherwise may run DDL without a physical transaction. Ensure a
            # failed multi-revision upgrade/downgrade cannot leave half-applied DDL.
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=sqlite, transactional_ddl=True if sqlite else None)
        try:
            with context.begin_transaction(): context.run_migrations()
            if sqlite: connection.commit()
        except Exception:
            if sqlite: connection.rollback()
            raise
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
