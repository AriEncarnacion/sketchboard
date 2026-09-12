#!/usr/bin/env bash
# Sketchboard: manage the Gemma-on-Lambda box.
#
#   lambda/lambdactl.sh check        verify API key works
#   lambda/lambdactl.sh types        instance types that have capacity right now
#   lambda/lambdactl.sh keys         SSH keys registered in Lambda Cloud
#   lambda/lambdactl.sh add-key      upload $LAMBDA_SSH_KEY_FILE as $LAMBDA_SSH_KEY_NAME
#   lambda/lambdactl.sh launch       launch a GPU box, install Ollama + Gemma via cloud-init
#   lambda/lambdactl.sh list         all instances in the workspace
#   lambda/lambdactl.sh status       the instance we launched (from lambda/.instance)
#   lambda/lambdactl.sh wait         block until the box is up and the model is loaded
#   lambda/lambdactl.sh ssh [cmd]    ssh into the box
#   lambda/lambdactl.sh logs         tail cloud-init + model download logs on the box
#   lambda/lambdactl.sh health       hit /healthz and /readyz over the public IP
#   lambda/lambdactl.sh chat [text]  send a test prompt through the OpenAI-compatible endpoint
#   lambda/lambdactl.sh sketch <img> send an image + prompt straight to Gemma (no harness)
#   lambda/lambdactl.sh deploy       rsync server/ to the box and (re)install the harness
#   lambda/lambdactl.sh mockup <img> [notes]  full harness round trip, streams events
#   lambda/lambdactl.sh edit "<instruction>"  follow-up edit on the last mockup's session
#   lambda/lambdactl.sh terminate    terminate the instance (asks for confirmation)
#
# Config lives in lambda/.env (see lambda/.env.example). Needs curl + jq.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/.env"
STATE_FILE="$HERE/.instance"
API="https://cloud.lambda.ai/api/v1"
PORT=8080

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing '$1' (brew install $1)"; }
need curl; need jq

[[ -f "$ENV_FILE" ]] || die "no $ENV_FILE. Run: cp lambda/.env.example lambda/.env  and fill in LAMBDA_API_KEY"
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
[[ -n "${LAMBDA_API_KEY:-}" ]] || die "LAMBDA_API_KEY is empty in $ENV_FILE"

LAMBDA_SSH_KEY_NAME="${LAMBDA_SSH_KEY_NAME:-sketchboard}"
LAMBDA_SSH_KEY_FILE="${LAMBDA_SSH_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
LAMBDA_SSH_KEY_FILE="${LAMBDA_SSH_KEY_FILE/#\~/$HOME}"
LAMBDA_SSH_KEY_FILE="$(eval echo "$LAMBDA_SSH_KEY_FILE")"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:26b}"
LAMBDA_INSTANCE_PREFS="${LAMBDA_INSTANCE_PREFS:-gpu_1x_h100_sxm5,gpu_1x_h100_pcie,gpu_1x_a100_sxm4,gpu_1x_a100,gpu_1x_a6000,gpu_1x_a10}"
LAMBDA_REGION="${LAMBDA_REGION:-}"
# Regions to prefer when several have capacity, in order. Others are used only as a fallback.
LAMBDA_REGION_PREFS="${LAMBDA_REGION_PREFS:-us-west-1,us-west-2,us-west-3,us-east-1,us-east-2,us-east-3,us-midwest-1,us-south-1,us-south-2,us-south-3,us-southeast-1}"

# --- API helper ---------------------------------------------------------------
# api METHOD PATH [JSON_BODY]  -> prints the response body, fails on non-2xx
api() {
  local method="$1" path="$2" body="${3:-}" out code
  out="$(mktemp)"
  if [[ -n "$body" ]]; then
    code="$(curl -sS -m 30 --retry 2 --retry-connrefused -o "$out" -w '%{http_code}' -X "$method" "$API$path" \
      -H "Authorization: Bearer $LAMBDA_API_KEY" \
      -H "Content-Type: application/json" \
      --data-binary "$body")"
  else
    code="$(curl -sS -m 30 --retry 2 --retry-connrefused -o "$out" -w '%{http_code}' -X "$method" "$API$path" \
      -H "Authorization: Bearer $LAMBDA_API_KEY")"
  fi
  if [[ "$code" != 2* ]]; then
    echo "Lambda API $method $path -> HTTP $code" >&2
    jq -r '.error | "  \(.code): \(.message)\n  hint: \(.suggestion // "-")"' "$out" 2>/dev/null >&2 || cat "$out" >&2
    rm -f "$out"; return 1
  fi
  cat "$out"; rm -f "$out"
}

# --- state ----------------------------------------------------------------------
save_state() { jq -n --arg id "$1" --arg region "$2" --arg type "$3" \
  '{id:$id, region:$region, instance_type:$type}' > "$STATE_FILE"; }
state_id()   { [[ -f "$STATE_FILE" ]] && jq -r .id "$STATE_FILE" || true; }
instance_json() {
  local id; id="$(state_id)"
  [[ -n "$id" ]] || die "no instance recorded in $STATE_FILE. Run: lambda/lambdactl.sh launch"
  api GET "/instances/$id" | jq .data
}
instance_ip() { instance_json | jq -r '.ip // empty'; }

# --- commands -------------------------------------------------------------------
cmd_check() {
  api GET /ssh-keys >/dev/null && echo "API key OK (workspace reachable)"
}

cmd_types() {
  api GET /instance-types | jq -r '
    .data | to_entries[]
    | select((.value.regions_with_capacity_available | length) > 0)
    | .value as $v
    | "\(.key)\t$\(($v.instance_type.price_cents_per_hour / 100) | tostring)/hr\t\($v.instance_type.gpu_description)\t\($v.regions_with_capacity_available | map(.name) | join(","))"
  ' | sort | column -t -s $'\t' || echo "(nothing has capacity right now; retry in a minute)"
}

cmd_keys() {
  api GET /ssh-keys | jq -r '.data[] | "\(.name)\t\(.public_key[0:40])..."' | column -t -s $'\t'
}

cmd_add_key() {
  [[ -f "$LAMBDA_SSH_KEY_FILE" ]] || die "public key not found: $LAMBDA_SSH_KEY_FILE"
  if api GET /ssh-keys | jq -e --arg n "$LAMBDA_SSH_KEY_NAME" '.data[] | select(.name==$n)' >/dev/null; then
    echo "SSH key '$LAMBDA_SSH_KEY_NAME' already registered"; return
  fi
  local body
  body="$(jq -n --arg n "$LAMBDA_SSH_KEY_NAME" --rawfile k "$LAMBDA_SSH_KEY_FILE" \
    '{name:$n, public_key:($k | rtrimstr("\n"))}')"
  api POST /ssh-keys "$body" | jq -r '"registered SSH key \(.data.name)"'
}

# Pick first instance type from prefs that has capacity (optionally in LAMBDA_REGION).
# Prints "type<TAB>region<TAB>gpu_gb".
pick_instance() {
  local types; types="$(api GET /instance-types)"
  local t
  IFS=',' read -ra PREFS <<< "$LAMBDA_INSTANCE_PREFS"
  for t in "${PREFS[@]}"; do
    t="${t// /}"
    local hit
    hit="$(jq -r --arg t "$t" --arg r "$LAMBDA_REGION" --arg prefs "$LAMBDA_REGION_PREFS" '
      ($prefs | split(",") | map(select(length > 0))) as $order
      | .data[$t] // empty
      | . as $v
      | [$v.regions_with_capacity_available[] | select($r == "" or .name == $r)]
      | sort_by(.name as $n | ($order | index($n)) // 999)
      | first // empty
      | "\($t)\t\(.name)\t\($v.instance_type.gpu_description | capture("(?<gb>[0-9]+) ?GB").gb // "0")"
    ' <<< "$types")"
    if [[ -n "$hit" ]]; then echo "$hit"; return 0; fi
  done
  return 1
}

# Ensure a per-region firewall ruleset opening $PORT exists; print its id.
ensure_ruleset() {
  local region="$1" name="sketchboard-gemma-$region" id
  id="$(api GET /firewall-rulesets | jq -r --arg n "$name" '.data[] | select(.name==$n) | .id' | head -n1)"
  if [[ -n "$id" ]]; then echo "$id"; return; fi
  local body
  body="$(jq -n --arg n "$name" --arg r "$region" --argjson p "$PORT" '{
    name: $n, region: $r,
    rules: [
      {protocol:"tcp", port_range:[22,22],  source_network:"0.0.0.0/0", description:"ssh"},
      {protocol:"tcp", port_range:[$p,$p], source_network:"0.0.0.0/0", description:"gemma gateway (bearer token)"}
    ]}')"
  api POST /firewall-rulesets "$body" | jq -r '.data.id'
}

ensure_token() {
  if [[ -z "${GEMMA_TOKEN:-}" ]]; then
    GEMMA_TOKEN="$(openssl rand -hex 24)"
    if grep -q '^GEMMA_TOKEN=' "$ENV_FILE"; then
      sed -i '' "s|^GEMMA_TOKEN=.*|GEMMA_TOKEN=$GEMMA_TOKEN|" "$ENV_FILE"
    else
      echo "GEMMA_TOKEN=$GEMMA_TOKEN" >> "$ENV_FILE"
    fi
    echo "generated GEMMA_TOKEN and saved it to $ENV_FILE"
  fi
}

cmd_launch() {
  if [[ -n "$(state_id)" ]]; then
    local st; st="$(api GET "/instances/$(state_id)" 2>/dev/null | jq -r '.data.status // "gone"')"
    [[ "$st" == "terminated" || "$st" == "gone" ]] || die "instance $(state_id) is already $st. Terminate it first or delete $STATE_FILE"
  fi
  cmd_add_key
  ensure_token

  local pick; pick="$(pick_instance)" || die "none of [$LAMBDA_INSTANCE_PREFS] has capacity${LAMBDA_REGION:+ in $LAMBDA_REGION}. Run 'types' to see what does, then edit LAMBDA_INSTANCE_PREFS."
  local itype region gb
  IFS=$'\t' read -r itype region gb <<< "$pick"

  local model="$OLLAMA_MODEL"
  if (( gb > 0 && gb < 40 )) && [[ "$model" == gemma4:31b || "$model" == gemma4:26b ]]; then
    model="gemma4:12b"
    echo "note: $itype has ${gb} GB VRAM; using $model instead of $OLLAMA_MODEL"
  fi

  local ruleset; ruleset="$(ensure_ruleset "$region")"
  local user_data
  user_data="$(sed -e "s|__OLLAMA_MODEL__|$model|g" -e "s|__GEMMA_TOKEN__|$GEMMA_TOKEN|g" "$HERE/cloud-init.yaml")"

  local body
  body="$(jq -n --arg r "$region" --arg t "$itype" --arg k "$LAMBDA_SSH_KEY_NAME" \
    --arg ud "$user_data" --arg fw "$ruleset" '{
      region_name: $r, instance_type_name: $t, ssh_key_names: [$k],
      name: "sketchboard-gemma", hostname: "sketchboard-gemma",
      user_data: $ud, firewall_rulesets: [{id: $fw}],
      tags: [{key:"project", value:"sketchboard"}]
    }')"

  echo "launching $itype in $region with $model ..."
  local id; id="$(api POST /instance-operations/launch "$body" | jq -r '.data.instance_ids[0]')"
  save_state "$id" "$region" "$itype"
  echo "instance id: $id  (saved to $STATE_FILE)"
  echo "next: lambda/lambdactl.sh wait"
}

cmd_list() {
  api GET /instances | jq -r '
    .data[] | "\(.id)\t\(.name // "-")\t\(.status)\t\(.ip // "-")\t\(.instance_type.name)\t\(.region.name)"
  ' | column -t -s $'\t'
}

cmd_status() { instance_json | jq '{id, name, status, ip, instance_type: .instance_type.name, region: .region.name}'; }

cmd_wait() {
  local ip="" st
  echo -n "waiting for instance to become active"
  local started=$SECONDS
  while :; do
    local j
    if ! j="$(instance_json 2>/dev/null)"; then echo -n "!"; sleep 10; continue; fi   # transient API error
    st="$(jq -r .status <<< "$j")"; ip="$(jq -r '.ip // empty' <<< "$j")"
    if [[ "$st" == "active" && -n "$ip" ]]; then echo " $ip"; break; fi
    [[ "$st" == "terminated" ]] && die "instance is terminated"
    [[ "$st" == "unhealthy" ]] && die "Lambda marked the instance unhealthy (provisioning failed). Run 'terminate' then 'launch' again, ideally in another region."
    if (( SECONDS - started > 1500 )); then die "still '$st' after 25 min. Lambda boots occasionally hang; terminate and relaunch."; fi
    echo -n "."; sleep 10
  done
  echo -n "waiting for gateway on :$PORT"
  until curl -fsS -m 3 "http://$ip:$PORT/healthz" >/dev/null 2>&1; do echo -n "."; sleep 10; done
  echo " up"
  echo -n "waiting for $OLLAMA_MODEL download + load (this is the slow part)"
  until curl -fsS -m 3 "http://$ip:$PORT/readyz" >/dev/null 2>&1; do echo -n "."; sleep 15; done
  echo " ready"
  echo
  echo "GEMMA_BASE_URL=http://$ip:$PORT/v1"
  echo "GEMMA_TOKEN=$GEMMA_TOKEN"
  echo
  echo "smoke test:  lambda/lambdactl.sh chat 'say hi'"
}

cmd_ssh() {
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  local key="${LAMBDA_SSH_KEY_FILE%.pub}"
  exec ssh -o StrictHostKeyChecking=accept-new -i "$key" "ubuntu@$ip" "$@"
}

cmd_logs() {
  cmd_ssh 'sudo tail -n 40 /var/log/cloud-init-output.log; echo; echo "--- warm ---"; sudo tail -n 20 /var/log/sketchboard-warm.log 2>/dev/null || echo "(model pull not started yet)"'
}

cmd_health() {
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  echo -n "healthz: "; curl -sS -m 5 "http://$ip:$PORT/healthz" || echo "(down)"
  echo -n "readyz:  "; curl -sS -m 5 "http://$ip:$PORT/readyz" || echo "(model not loaded yet)"
  echo -n "models:  "; curl -sS -m 5 -H "Authorization: Bearer $GEMMA_TOKEN" "http://$ip:$PORT/v1/models" | jq -c '[.data[].id]' || echo "(auth or ollama down)"
}

cmd_chat() {
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  local prompt="${*:-Reply with one short sentence: what are you?}"
  jq -n --arg m "$OLLAMA_MODEL" --arg p "$prompt" \
    '{model:$m, messages:[{role:"user", content:$p}], max_tokens: 200}' \
  | curl -sS -m 120 "http://$ip:$PORT/v1/chat/completions" \
      -H "Authorization: Bearer $GEMMA_TOKEN" -H "Content-Type: application/json" --data-binary @- \
  | jq -r '.choices[0].message.content // .'
}

# sketch <image.jpg|png> [prompt]  -- same shape of request the iPad app will send
cmd_sketch() {
  local img="${1:-}"; shift || true
  [[ -f "$img" ]] || die "usage: sketch <image file> [prompt]"
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  local mime="image/jpeg"; [[ "$img" == *.png ]] && mime="image/png"
  local prompt="${*:-This is a hand-drawn sketch of a mobile app screen. Describe the UI it depicts as a structured list of components, then output a single self-contained HTML page that implements it. Output only the HTML.}"
  local b64; b64="$(base64 < "$img" | tr -d '\n')"
  jq -n --arg m "$OLLAMA_MODEL" --arg p "$prompt" --arg u "data:$mime;base64,$b64" '{
      model: $m, max_tokens: 4000,
      messages: [{role:"user", content:[
        {type:"text", text:$p},
        {type:"image_url", image_url:{url:$u}}
      ]}]}' \
  | curl -sS -m 600 "http://$ip:$PORT/v1/chat/completions" \
      -H "Authorization: Bearer $GEMMA_TOKEN" -H "Content-Type: application/json" --data-binary @- \
  | jq -r '.choices[0].message.content // .'
}

# deploy: rsync ../server to the box and run its install.sh there.
cmd_deploy() {
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  [[ -n "${GEMMA_TOKEN:-}" ]] || die "GEMMA_TOKEN is empty in $ENV_FILE"
  local key="${LAMBDA_SSH_KEY_FILE%.pub}" src="$HERE/../server/"
  local sshopts=(-i "$key" -o StrictHostKeyChecking=accept-new)
  echo "syncing server/ -> ubuntu@$ip:sketchboard-server/"
  rsync -az --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude '*.pyc' \
    -e "ssh ${sshopts[*]}" "$src" "ubuntu@$ip:sketchboard-server/"
  ssh "${sshopts[@]}" "ubuntu@$ip" "GEMMA_TOKEN='$GEMMA_TOKEN' OLLAMA_MODEL='$OLLAMA_MODEL' NANGO_SECRET_KEY='${NANGO_SECRET_KEY:-}' bash ~/sketchboard-server/install.sh"
  echo; echo "public check:"; cmd_health
}

# mockup <image> [description]  -- full harness round trip, prints each streamed event
cmd_mockup() {
  local img="${1:-}"; shift || true
  [[ -f "$img" ]] || die "usage: mockup <image file> [description]"
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  local mime="image/jpeg"; [[ "$img" == *.png ]] && mime="image/png"
  # Env overrides: MODEL=gemma4:26b ITER=1 DEBUG=1
  local desc="${*:-}" out="$HERE/.last-mockup.html"
  jq -n --arg m "$mime" --arg d "$desc" --arg model "${MODEL:-}" --arg iter "${ITER:-}" --arg dbg "${DEBUG:-}" \
    --rawfile b64 <(base64 < "$img" | tr -d '\n') \
    '{image_base64:$b64, mime:$m, description:$d}
     + (if $model != "" then {model:$model} else {} end)
     + (if $iter != "" then {max_iterations:($iter|tonumber)} else {} end)
     + (if $dbg != "" then {debug:true} else {} end)' \
  | curl -sS -N -m 900 "http://$ip:$PORT/api/v1/mockup" \
      -H "Authorization: Bearer $GEMMA_TOKEN" -H "Content-Type: application/json" --data-binary @- \
  | print_events
}

# edit "<instruction>" [session_id]  -- follow-up on the last mockup (session saved by `mockup`)
cmd_edit() {
  local instruction="${1:-}"; [[ -n "$instruction" ]] || die "usage: edit \"make the button green\" [session_id]"
  local sid="${2:-$(cat "$HERE/.last-session" 2>/dev/null || true)}"
  [[ -n "$sid" ]] || die "no session: run 'mockup' first or pass a session id"
  local ip; ip="$(instance_ip)"; [[ -n "$ip" ]] || die "instance has no IP yet"
  jq -n --arg s "$sid" --arg i "$instruction" '{session_id:$s, instruction:$i}' \
  | curl -sS -N -m 900 "http://$ip:$PORT/api/v1/edit" \
      -H "Authorization: Bearer $GEMMA_TOKEN" -H "Content-Type: application/json" --data-binary @- \
  | print_events
}

print_events() {
  local out="$HERE/.last-mockup.html"
  while IFS= read -r line; do
      if ! jq -e .type <<< "$line" >/dev/null 2>&1; then echo "[raw] $line"; continue; fi
      if [[ "$line" == *'"draft_partial"'* ]]; then
        # One updating line while the model writes; the partial doc lands in a file to open in a browser.
        printf '\r[partial %s] %s chars, %s' "$(jq -r .iteration <<< "$line")" "$(jq -r .chars <<< "$line")" "$(date +%T)"
        jq -r .html <<< "$line" > "$HERE/.last-mockup-partial.html"
        partial_line=1
        continue
      fi
      [[ -n "${partial_line:-}" ]] && { echo; partial_line=; }
      jq -r '
        if .type == "session" then "[session] \(.session_id)"
        elif .type == "draft" then "[draft \(.iteration)] \(.seconds)s, \(.tokens) tokens, \(.html | length) chars\n  \(.notes | split("\n") | map("  " + .) | join("\n"))"
        elif .type == "final" then "[final] chose draft \(.chosen) (score \(.score // "-")), approved=\(.approved), \(.iterations) judged"
        elif .type == "checks" then "[checks \(.iteration)] \(if .clean then "clean" else "problems:\n" + .problems end)"
        elif .type == "verdict" then "[verdict \(.iteration)] \(.seconds)s, problems:\n\(.problems | split("\n") | map("  " + .) | join("\n"))"
        elif .type == "approved" then "[approved \(.iteration)] \(.seconds)s"
        elif .type == "patch" then "[patch] \(.hunks) hunk(s) in \(.seconds)s: \(.note)"
        else "[\(.type)] \(.message // .iteration // "")" end' <<< "$line"
      html="$(jq -r 'select(.type=="final") | .html' <<< "$line")"
      [[ -n "$html" ]] && printf '%s' "$html" > "$out" && echo "saved final HTML to $out (open it in a browser)"
      sid="$(jq -r 'select(.type=="session") | .session_id' <<< "$line")"
      [[ -n "$sid" ]] && printf '%s' "$sid" > "$HERE/.last-session"
      png="$(jq -r 'select(.type=="checks") | .png_base64 // empty' <<< "$line")"
      [[ -n "$png" ]] && base64 -d <<< "$png" > "$HERE/.last-render-$(jq -r .iteration <<< "$line").png"
    done
}

cmd_terminate() {
  local id; id="$(state_id)"; [[ -n "$id" ]] || die "nothing recorded in $STATE_FILE"
  echo "about to terminate $id:"; cmd_status
  read -r -p "type 'yes' to terminate: " ans
  [[ "$ans" == "yes" ]] || { echo "aborted"; exit 0; }
  api POST /instance-operations/terminate "$(jq -n --arg id "$id" '{instance_ids:[$id]}')" \
    | jq -r '.data.terminated_instances[] | "terminated \(.id) (\(.status))"'
  rm -f "$STATE_FILE"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  check)     cmd_check ;;
  types)     cmd_types ;;
  keys)      cmd_keys ;;
  add-key)   cmd_add_key ;;
  launch)    cmd_launch ;;
  list)      cmd_list ;;
  status)    cmd_status ;;
  wait)      cmd_wait ;;
  ssh)       cmd_ssh "$@" ;;
  logs)      cmd_logs ;;
  health)    cmd_health ;;
  chat)      cmd_chat "$@" ;;
  sketch)    cmd_sketch "$@" ;;
  deploy)    cmd_deploy ;;
  mockup)    cmd_mockup "$@" ;;
  edit)      cmd_edit "$@" ;;
  terminate) cmd_terminate ;;
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
