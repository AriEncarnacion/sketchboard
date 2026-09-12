#!/usr/bin/env bash
# Runs ON the Lambda box. Idempotent. Invoked by lambda/lambdactl.sh deploy-discord after
# rsyncing discordbot/ to ~/sketchboard-discord.
#
# Env: DISCORD_BOT_TOKEN (required), optional DISCORD_REQUIRE_MENTION=1

set -euo pipefail
: "${DISCORD_BOT_TOKEN:?DISCORD_BOT_TOKEN is required}"
SRC="$HOME/sketchboard-discord"
APP=/opt/sketchboard-discord

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
DISCORD_BOT_TOKEN=$DISCORD_BOT_TOKEN
DISCORD_REQUIRE_MENTION=${DISCORD_REQUIRE_MENTION:-0}
HARNESS_URL=http://127.0.0.1:8000
MAX_ITERATIONS=${MAX_ITERATIONS:-2}
EOF
chmod 600 .env

echo "== systemd"
sudo cp sketchboard-discord.service /etc/systemd/system/sketchboard-discord.service
sudo systemctl daemon-reload
sudo systemctl enable --now sketchboard-discord
sudo systemctl restart sketchboard-discord

sleep 4
if systemctl is-active --quiet sketchboard-discord; then
  echo "bot running:"; sudo journalctl -u sketchboard-discord -n 3 --no-pager | cut -c1-160
else
  echo "bot failed to start:" >&2
  sudo journalctl -u sketchboard-discord -n 30 --no-pager >&2
  exit 1
fi
