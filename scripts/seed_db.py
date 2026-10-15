"""Rebuild the GovernIQ database from the synthetic seed data.

Run from the project folder:  python scripts/seed_db.py
Warning: this deletes the existing database tables and stored evidence files first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governiq.config import DB_PATH  # noqa: E402
from governiq.db import make_engine  # noqa: E402
from governiq.demo import rebuild_demo_data  # noqa: E402


def main() -> None:
    counts = rebuild_demo_data(make_engine())
    print(f"Database rebuilt at {DB_PATH}")
    for name, count in counts.items():
        print(f"  {name:<17} {count}")


if __name__ == "__main__":
    main()
