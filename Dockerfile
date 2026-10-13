FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MIA_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY THIRD_PARTY_NOTICES.md ./
COPY THIRD_PARTY_LICENSES ./THIRD_PARTY_LICENSES
COPY mia ./mia
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 mia \
    && mkdir -p /data \
    && chown -R mia:mia /data /app

USER mia
EXPOSE 8123
CMD ["uvicorn", "mia.app:app", "--host", "0.0.0.0", "--port", "8123"]

