# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so editing code does not invalidate the install layer.
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip uninstall -y jobhunter-api

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Non-root. The drafts directory is a mounted volume, so it must be writable
# by this user.
RUN useradd --create-home --uid 10001 jobhunter \
 && mkdir -p /data/drafts \
 && chown -R jobhunter:jobhunter /app /data
USER jobhunter

EXPOSE 8000

# One image, three roles. Compose overrides the command for the migrate and
# worker services; shipping a single image keeps their dependencies provably
# identical.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
