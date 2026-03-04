#!/usr/bin/env bash
set -euo pipefail

# Deploy Calendar Primary Dashboard to VPS
# Default URL: https://hariclaw.com/calendar-primary
# Optional: --mode subdomain to use calendar.hariclaw.com

MODE="path"
VPS_HOST="openclaw@162.212.153.134"
REMOTE_DIR="/home/openclaw/calendar"
SERVICE_NAME="calendar-dashboard.service"
HARICLAW_CONF="/etc/nginx/sites-available/hariclaw"
CERTBOT_EMAIL=""
LOCAL_SERVICE_FILE="/home/openclaw/calendar-dashboard.service"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --host)
      VPS_HOST="${2:-}"
      shift 2
      ;;
    --certbot-email)
      CERTBOT_EMAIL="${2:-}"
      shift 2
      ;;
    --service-file)
      LOCAL_SERVICE_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--mode path|subdomain] [--host user@host] [--certbot-email you@example.com] [--service-file /path/to/calendar-dashboard.service]"
      exit 1
      ;;
  esac
done

if [[ "$MODE" != "path" && "$MODE" != "subdomain" ]]; then
  echo "Invalid --mode: $MODE (expected path or subdomain)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$LOCAL_SERVICE_FILE" ]]; then
  echo "Local service file not found at $LOCAL_SERVICE_FILE"
  echo "Create it first (expected path: /home/openclaw/calendar-dashboard.service)."
  exit 1
fi

echo "==> Syncing calendar app to $VPS_HOST:$REMOTE_DIR"
rsync -az --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$SCRIPT_DIR/" "$VPS_HOST:$REMOTE_DIR/"

echo "==> Uploading systemd unit"
rsync -az "$LOCAL_SERVICE_FILE" "$VPS_HOST:/home/openclaw/calendar-dashboard.service"

echo "==> Installing and restarting systemd service"
ssh "$VPS_HOST" "
  set -euo pipefail
  sudo install -m 644 /home/openclaw/calendar-dashboard.service /etc/systemd/system/$SERVICE_NAME
  sudo systemctl daemon-reload
  sudo systemctl enable $SERVICE_NAME
  sudo systemctl restart $SERVICE_NAME
  sudo systemctl --no-pager --full status $SERVICE_NAME | sed -n '1,20p'
"

if [[ "$MODE" == "path" ]]; then
  echo "==> Configuring nginx path route: /calendar-primary/"
  ssh "$VPS_HOST" "
    set -euo pipefail
    sudo install -m 644 /home/openclaw/calendar/nginx-calendar-primary-location.conf /etc/nginx/snippets/calendar-primary.conf

    sudo python3 - <<'PY'
from pathlib import Path
cfg = Path('/etc/nginx/sites-available/hariclaw')
include_line = '    include /etc/nginx/snippets/calendar-primary.conf;\n'
text = cfg.read_text()
if include_line not in text:
    marker = '    listen 443 ssl;'
    if marker not in text:
        raise SystemExit('Could not find insertion marker in /etc/nginx/sites-available/hariclaw')
    text = text.replace(marker, include_line + marker, 1)
    cfg.write_text(text)
    print('Inserted include for calendar-primary snippet.')
else:
    print('Include already present; no config change needed.')
PY

    sudo nginx -t
    sudo systemctl reload nginx

    if [[ -f /etc/letsencrypt/live/hariclaw.com/fullchain.pem ]]; then
      echo 'SSL ready via existing hariclaw.com certificate.'
    else
      echo 'WARNING: Existing hariclaw.com cert not found. Run certbot before using HTTPS.'
    fi
  "

  echo "✅ Deployed. URL: https://hariclaw.com/calendar-primary/"
else
  echo "==> Configuring nginx subdomain: calendar.hariclaw.com"
  ssh "$VPS_HOST" "
    set -euo pipefail
    sudo install -m 644 /home/openclaw/calendar/nginx-calendar.hariclaw.com.conf /etc/nginx/sites-available/calendar.hariclaw.com
    sudo ln -sfn /etc/nginx/sites-available/calendar.hariclaw.com /etc/nginx/sites-enabled/calendar.hariclaw.com
    sudo nginx -t
    sudo systemctl reload nginx
  "

  if [[ -n "$CERTBOT_EMAIL" ]]; then
    echo "==> Requesting/expanding SSL cert for calendar.hariclaw.com"
    ssh "$VPS_HOST" "
      set -euo pipefail
      sudo certbot --nginx -d calendar.hariclaw.com --agree-tos --non-interactive -m '$CERTBOT_EMAIL' --redirect
      sudo nginx -t
      sudo systemctl reload nginx
    "
    echo "✅ Deployed. URL: https://calendar.hariclaw.com/"
  else
    cat <<'EOF'
⚠️ Subdomain configured on HTTP only.
To enable HTTPS, rerun with:
  ./deploy-dashboard.sh --mode subdomain --certbot-email you@example.com
EOF
  fi
fi

echo "==> Done"
