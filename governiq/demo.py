"""Build or rebuild the synthetic Kshitij Finserv demo data: seed script, first start and admin reset."""

from sqlalchemy.engine import Engine

from governiq.assurance import evidence_dir
from governiq.db import create_tables, make_session_factory
from governiq.seed import seed
from governiq.seed_assurance import seed_assurance


def rebuild_demo_data(engine: Engine) -> dict[str, int]:
    """Drop every table, clear stored evidence files and load the seed data again."""
    folder = evidence_dir()
    if folder.exists():
        for file in folder.iterdir():
            if file.is_file():
                file.unlink()
    create_tables(engine, reset=True)
    with make_session_factory(engine)() as session:
        counts = seed(session)
        counts.update(seed_assurance(session))
    return counts
