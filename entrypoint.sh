#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
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

# ---- Seed de DEMOS (solo si SEED_DEMO=1 y no se hizo antes) ----
SEED_FLAG="${SEED_DEMO:-0}"
FIX_DIR="${DEMO_FIXTURES_DIR:-cloudapi/fixtures}"
SENTINEL="${SEED_SENTINEL_PATH:-/app/.seeded_demo}"

if [[ "$SEED_FLAG" = "1" ]]; then
  if [[ -f "$SENTINEL" ]]; then
    echo "[seed] Ya aplicado previamente (marcado por $SENTINEL)"
  else
    echo "[seed] Cargando fixtures desde $FIX_DIR ..."
    shopt -s nullglob
    for f in "$FIX_DIR"/*.json; do
      echo "[seed] loaddata $(basename "$f")"
      python manage.py loaddata "$f"
    done
    touch "$SENTINEL"
    echo "[seed] Listo. Marcado con $SENTINEL"
  fi
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3