#!/usr/bin/env bash
set -euo pipefail

echo "[init] Aplicando migraciones..."
python manage.py migrate --noinput

echo "[init] Collectstatic..."
python manage.py collectstatic --noinput || true

# ---- Superusuario opcional (solo si variables provistas) ----
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_EMAIL:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
python <<'PYCODE'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
u = os.environ["DJANGO_SUPERUSER_USERNAME"]
e = os.environ["DJANGO_SUPERUSER_EMAIL"]
p = os.environ["DJANGO_SUPERUSER_PASSWORD"]
if not User.objects.filter(username=u).exists():
    User.objects.create_superuser(u, e, p)
    print(f"[seed] Superuser creado: {u}")
else:
    print(f"[seed] Superuser ya existe: {u}")
PYCODE
fi

# --- Reset opcional (borra toda la base) ---
if [[ "${SEED_RESET:-0}" = "1" ]]; then
  echo "[seed] RESET activo: limpiando base de datos..."
  python manage.py flush --no-input
  python manage.py migrate --noinput
fi

# --- Carga de datos demo ---
if [[ "${SEED_DEMO:-0}" = "1" ]]; then
  echo "[seed] Cargando fixtures demo.json..."
  python manage.py loaddata cloudapi/fixtures/demo.json
fi

echo "[start] Iniciando servidor..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3