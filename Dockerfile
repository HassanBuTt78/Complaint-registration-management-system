# ---------------------------------------------------------------------------
# Online Complaint Registration & Management System
#
# Built entirely from free, open-source images and packages. The container is
# optional: the project also runs with plain `python manage.py runserver`.
# ---------------------------------------------------------------------------
FROM python:3.13-slim

LABEL org.opencontainers.image.title="OCR Portal" \
      org.opencontainers.image.description="Online Complaint Registration & Management System" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# curl is used by the compose healthcheck; nothing else is needed because the
# MySQL driver (PyMySQL) is pure Python - no build toolchain required.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Git on Windows does not always preserve the execute bit, so set it here.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Run as an unprivileged user and give it ownership of the writable paths.
RUN useradd --create-home --shell /usr/sbin/nologin portal \
    && mkdir -p /app/media /app/staticfiles /app/logs \
    && chown -R portal:portal /app

# Collect static assets at build time so the image is ready to serve.
# A throwaway key is used because collectstatic must not need real secrets.
RUN SECRET_KEY=k7xQ2mP9vL4wR8tY1nJ6sD3fH0aZ5bU7eC9gK2mN4pS6qV8xW1yT3rB5uF7jD9L \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    SECURE_SSL_REDIRECT=False \
    python manage.py collectstatic --noinput

USER portal

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/accounts/login/ || exit 1

# entrypoint.sh applies migrations, then hands over to gunicorn.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
