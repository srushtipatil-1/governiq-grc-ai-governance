# Deploying GovernIQ

GovernIQ is a demo with synthetic data. Every deployment builds its own demo database on first start.

## Streamlit Community Cloud (free public link)

1. Sign in at share.streamlit.io with the GitHub account that owns the repository.
2. Create app, then choose the repository `governiq-grc-ai-governance`, branch `main`, main file `app/Home.py`.
3. Under Advanced settings choose Python 3.12. No secrets are needed.
4. Deploy. The first start takes a few minutes while packages install and the demo data is seeded.

The cloud file system is temporary: a reboot brings the demo back to its seed state. An Admin can also
reset it at any time from Audit trail & users.

## Docker

```
docker build -t governiq .
docker run -p 8501:8501 governiq
```

Then open http://localhost:8501. The container runs as a non-root user and reports health on
`/_stcore/health`.

## Settings (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOVERNIQ_DEMO_MODE` | `true` | `false` hides the one-click demo sign-in buttons. |
| `GOVERNIQ_DEMO_PASSWORD` | `governiq-demo-2026` | Password given to every seeded demo account. |
| `GOVERNIQ_DB_URL` | SQLite file in `data/` | Any SQLAlchemy database URL. |
| `GOVERNIQ_EVIDENCE_DIR` | `data/evidence` | Where uploaded evidence files are stored. |

## Continuous integration

`.github/workflows/ci.yml` runs on every push: ruff (lint and format), pytest on Python 3.12 and 3.13,
bandit (code security), pip-audit (known vulnerable dependencies) and a Docker build.
