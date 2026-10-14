"""Database connection. Every other module gets its database session from here."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from governiq.config import DB_PATH


class Base(DeclarativeBase):
    """Parent class for every table in GovernIQ."""


@event.listens_for(Engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _record):
    # SQLite ignores foreign keys unless this is switched on for each connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str | None = None) -> Engine:
    """Create a database engine. Tests pass their own temporary database URL."""
    return create_engine(url or f"sqlite:///{DB_PATH}")


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_tables(engine: Engine, reset: bool = False) -> None:
    """Create every table. With reset=True, delete all tables first (used by the seed script)."""
    from governiq import models  # noqa: F401  (importing registers the tables)

    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)