from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


def database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if os.getenv("APP_ENV", "development").lower() == "production":
        if not configured or not (configured.startswith("postgres://") or configured.startswith("postgresql://") or configured.startswith("postgresql+psycopg://")):
            raise RuntimeError("Production requires DATABASE_URL for PostgreSQL; SQLite is supported only for local/test use")
    url = configured or "sqlite:///./.data/dz_luncher.db"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    resolved = url or database_url()
    kwargs = {"pool_pre_ping": True, "echo": echo}
    if resolved.startswith("sqlite:"):
        if resolved in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["poolclass"] = StaticPool
        else:
            # Ensure the local database parent exists without silently changing its path.
            path = resolved.removeprefix("sqlite:///")
            if path != ":memory:":
                Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(resolved, **kwargs)

    if resolved.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        # SQLite is the single-node pilot adapter. BEGIN IMMEDIATE serializes
        # quota/reward writes so a read-then-write cannot overbook a campaign.
        @event.listens_for(engine, "begin")
        def sqlite_begin_immediate(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def initialize_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
