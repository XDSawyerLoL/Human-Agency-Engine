from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base
from app import models  # noqa: F401
from app import world_models  # noqa: F401
from app import synthesis_models  # noqa: F401
from app import acquisition_models  # noqa: F401
from app import delegation_models  # noqa: F401
from app import execution_models  # noqa: F401
from app import adapter_models  # noqa: F401
from app import sandbox_models  # noqa: F401
from app import readiness_models  # noqa: F401
from app import market_models  # noqa: F401
from app import collective_models  # noqa: F401
from app import collective_offer_models  # noqa: F401
from app import quorum_models  # noqa: F401
from app import allocation_models  # noqa: F401
from app import acceptance_models  # noqa: F401
from app import settlement_models  # noqa: F401
from app import settlement_permit_models  # noqa: F401
from app import vault_models  # noqa: F401
from app import horizon_models  # noqa: F401
from app import horizon_cascade_models  # noqa: F401
from app import horizon_impact_models  # noqa: F401
from app import horizon_source_models  # noqa: F401
from app import horizon_reevaluation_models  # noqa: F401
from app import horizon_warning_models  # noqa: F401
from app import horizon_provisional_models  # noqa: F401
from app import horizon_materialization_models  # noqa: F401
from app import horizon_expiry_models  # noqa: F401
from app import horizon_backtest_models  # noqa: F401
from app import horizon_backfill_models  # noqa: F401
from app import horizon_weather_chain_models  # noqa: F401
from app import horizon_convergence_models  # noqa: F401
from app import horizon_event_graph_models  # noqa: F401
from app import horizon_collector_models  # noqa: F401
from app import horizon_corpus_models  # noqa: F401
from app import horizon_behavioral_warehouse_models  # noqa: F401

config = context.config
DATABASE_URL = settings.sqlalchemy_database_url
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
