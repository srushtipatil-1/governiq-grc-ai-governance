"""Rebuild the GovernIQ database from the synthetic seed data.

Run from the project folder:  python scripts/seed_db.py
Warning: this deletes the existing database tables first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governiq.config import DB_PATH  # noqa: E402
from governiq.db import create_tables, make_engine, make_session_factory  # noqa: E402
from governiq.seed import seed  # noqa: E402
from governiq.seed_assurance import seed_assurance  # noqa: E402


def main() -> None:
    engine = make_engine()
    create_tables(engine, reset=True)
    with make_session_factory(engine)() as session:
        counts = seed(session)
        counts.update(seed_assurance(session))
    print(f"Database rebuilt at {DB_PATH}")
    for name, count in counts.items():
        print(f"  {name:<17} {count}")


if __name__ == "__main__":
    main()
