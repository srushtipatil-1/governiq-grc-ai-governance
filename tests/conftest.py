"""Shared test fixtures: every test gets its own fresh, seeded database."""

import pytest

from governiq.db import create_tables, make_engine, make_session_factory
from governiq.seed import seed


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    """A seeded temporary database. The app is pointed at it through GOVERNIQ_DB_URL."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = make_engine(url)
    create_tables(engine)
    with make_session_factory(engine)() as db:
        seed(db)
    monkeypatch.setenv("GOVERNIQ_DB_URL", url)
    return url


@pytest.fixture
def session(db_url):
    with make_session_factory(make_engine(db_url))() as db:
        yield db
