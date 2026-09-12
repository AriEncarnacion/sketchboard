#!/usr/bin/env bash
# Runs ON the Lambda box. Idempotent. Invoked by lambda/lambdactl.sh deploy-slack after
# rsyncing slack/ to ~/sketchboard-slack.
#
# Env: SLACK_BOT_TOKEN (xoxb-…), SLACK_APP_TOKEN (xapp-…), optional SLACK_REQUIRE_MENTION=1

set -euo pipefail
: "${SLACK_BOT_TOKEN:?SLACK_BOT_TOKEN is required}"
: "${SLACK_APP_TOKEN:?SLACK_APP_TOKEN is required}"
SRC="$HOME/sketchboard-slack"
APP=/opt/sketchboard-slack

echo "== sync $SRC -> $APP"
sudo mkdir -p "$APP"
sudo chown "$USER":"$USER" "$APP"
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache "$SRC/" "$APP/"
cd "$APP"

echo "== python env"
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== runtime env"
cat > .env <<EOF
SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN
SLACK_APP_TOKEN=$SLACK_APP_TOKEN
SLACK_REQUIRE_MENTION=${SLACK_REQUIRE_MENTION:-0}
HARNESS_URL=http://127.0.0.1:8000
MAX_ITERATIONS=${MAX_ITERATIONS:-2}
EOF
chmod 600 .env

echo "== systemd"
sudo cp sketchboard-slack.service /etc/systemd/system/sketchboard-slack.service
sudo systemctl daemon-reload
sudo systemctl enable --now sketchboard-slack
sudo systemctl restart sketchboard-slack

sleep 3
if systemctl is-active --quiet sketchboard-slack; then
  echo "bot running:"; sudo journalctl -u sketchboard-slack -n 3 --no-pager | cut -c1-160
else
  echo "bot failed to start:" >&2
  sudo journalctl -u sketchboard-slack -n 30 --no-pager >&2
  exit 1
fi
