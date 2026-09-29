FROM python:3.12-slim@sha256:9c4b3a7e8f1d2c6b5a0e9f4d3c8b2a7e6f1d0c5b4a9e8f3d2c7b6a1e5f0d9c4b

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .
RUN useradd -r sprint
USER sprint
