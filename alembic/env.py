from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project root to sys.path to allow for absolute imports
# This assumes env.py is in alembic/ directory directly under project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import project-specific modules
from user_auth.orm_models import Base as UserAuthBase  # Target metadata for user_auth
from config import get_config # For database URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = UserAuthBase.metadata # Use UserAuthBase.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Configure sqlalchemy.url from config.py
# This will override the sqlalchemy.url from alembic.ini
app_config = get_config()
# Ensure forward slashes for URL, especially on Windows
normalized_db_path = app_config.STATE_DB_PATH.replace('\\', '/')
db_url = f"sqlite:///{normalized_db_path}"
if config.get_main_option('sqlalchemy.url') != db_url:
    config.set_main_option('sqlalchemy.url', db_url)
    if config.config_file_name: # Only log if ini file is actually being used
        print(f"Overriding sqlalchemy.url in env.py with: {db_url} (from config.py)")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # url = config.get_main_option("sqlalchemy.url") # Original line, url is now set globally
    context.configure(
        url=db_url, # Use the db_url derived from config.py
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # connectable = engine_from_config( # Original block
    #     config.get_section(config.config_ini_section, {}),
    #     prefix="sqlalchemy.",
    #     poolclass=pool.NullPool,
    # )
    
    # New block to use the db_url from config.py directly
    from sqlalchemy import create_engine
    connectable = create_engine(db_url, poolclass=pool.NullPool)


    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
