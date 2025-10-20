FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /srv/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /srv/app/requirements.txt

RUN pip install --no-cache-dir -r /srv/app/requirements.txt

COPY . /srv/app

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /srv/app

USER appuser

EXPOSE 8181

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://127.0.0.1:8181/ || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8181", "--workers", "1"]