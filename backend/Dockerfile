FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The build context is the repository root so the backend can load the
# shared prompts and validators under docs/ at runtime.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY backend/migrations /app/backend/migrations
COPY backend/prompts /app/backend/prompts
COPY backend/alembic.ini /app/backend/alembic.ini
COPY docs /app/docs

WORKDIR /app/backend
RUN python -m pip install .

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
