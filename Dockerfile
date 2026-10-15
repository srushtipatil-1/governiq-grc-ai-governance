# GovernIQ container: synthetic demo data is created on first start.
# Build:  docker build -t governiq .
# Run:    docker run -p 8501:8501 governiq   then open http://localhost:8501
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Run as an unprivileged user that owns only the data folder.
RUN useradd --create-home --uid 10001 governiq && mkdir -p data/evidence && chown -R governiq:governiq data
USER governiq

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "app/Home.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
