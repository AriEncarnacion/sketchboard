#!/usr/bin/env bash
# Runs ON the Lambda box (as ubuntu, with sudo). Idempotent.
# Invoked by lambda/lambdactl.sh deploy, which first rsyncs server/ to ~/sketchboard-server.
#
# Env: GEMMA_TOKEN (required), OLLAMA_MODEL (default gemma4:26b), NANGO_SECRET_KEY (optional)

set -euo pipefail
: "${GEMMA_TOKEN:?GEMMA_TOKEN is required}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:26b}"
SRC="$HOME/sketchboard-server"
APP=/opt/sketchboard

echo "== sync $SRC -> $APP"
sudo mkdir -p "$APP"
sudo chown "$USER":"$USER" "$APP"
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache "$SRC/" "$APP/"
cd "$APP"

echo "== python env"
if ! dpkg -s python3-venv >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv
fi
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== chromium for the render step"
if [[ ! -f .chromium-installed ]]; then
  sudo .venv/bin/playwright install-deps chromium
  .venv/bin/playwright install chromium
  touch .chromium-installed
fi

echo "== runtime env"
cat > .env <<EOF
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=$OLLAMA_MODEL
MAX_ITERATIONS=2
RENDER_ENABLED=1
NANGO_SECRET_KEY=${NANGO_SECRET_KEY:-}
NANGO_INTEGRATION_ID=${NANGO_INTEGRATION_ID:-github}
EOF

echo "== systemd"
sudo cp sketchboard.service /etc/systemd/system/sketchboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now sketchboard
sudo systemctl restart sketchboard

echo "== nginx: /api/ -> harness, /v1/ -> ollama, both behind the bearer token"
sudo tee /etc/nginx/sites-available/gemma >/dev/null <<EOF
server {
    listen 8080;
    client_max_body_size 50m;

    location = /healthz { default_type text/plain; return 200 "ok\n"; }
    location = /readyz  { proxy_pass http://127.0.0.1:8000/readyz; }

    location /api/ {
        if (\$http_authorization != "Bearer $GEMMA_TOKEN") { return 401; }
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
        proxy_buffering off;
        chunked_transfer_encoding on;
    }

    # Raw model access for experiments (OpenAI-compatible).
    location /v1/ {
        if (\$http_authorization != "Bearer $GEMMA_TOKEN") { return 401; }
        proxy_pass http://127.0.0.1:11434;
        proxy_http_version 1.1;
        # Ollama 403s any Host header that isn't localhost (DNS-rebinding guard).
        proxy_set_header Host 127.0.0.1:11434;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
    }

    location / { return 404; }
}
EOF
sudo ln -sf /etc/nginx/sites-available/gemma /etc/nginx/sites-enabled/gemma
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "== waiting for harness"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "harness up: $(curl -fsS http://127.0.0.1:8000/healthz)"
    exit 0
  fi
  sleep 1
done
echo "harness did not come up; last log lines:" >&2
sudo journalctl -u sketchboard -n 30 --no-pager >&2
exit 1
