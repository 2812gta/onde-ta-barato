# NOT YET VALIDATED: Docker is not installed on the dev machine (ADR 0001).
# The first real build happens in CI (job "build") and on the VPS.
#
# GDAL/GEOS/PROJ are added in M2, together with the first geo model.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app

FROM base AS dev
COPY backend/requirements /app/requirements
RUN pip install -r requirements/dev.txt
COPY backend/ /app/
USER app
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS prod
COPY backend/requirements /app/requirements
RUN pip install -r requirements/prod.txt
COPY backend/ /app/
ENV DJANGO_SETTINGS_MODULE=config.settings.production
USER app
EXPOSE 8000
# Static files collection and migrations run as explicit deploy steps, not on container start.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
