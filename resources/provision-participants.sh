#!/usr/bin/env bash
set -euo pipefail
umask 077

doctl auth init --context workshop
doctl auth switch --context workshop

# env
require_command() {
  command -v "$1" >/dev/null || {
    echo "ERROR: $1 is not installed."
    exit 1
  }
}

for command in \
  doctl ssh ssh-keygen openssl curl dig awk grep sort seq
do
  require_command "$command"
done

cd resources/

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/workshop.env}"
[[ -r "$CONFIG_FILE" ]] || {
  echo "ERROR: Cannot read $CONFIG_FILE" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$CONFIG_FILE"

: "${SSH_KEY_NAME:?Missing SSH_KEY_NAME}"
: "${VPC_NAME:?Missing VPC_NAME}"
: "${SNAPSHOT_NAME:?Missing SNAPSHOT_NAME}"
: "${PROJECT_NAME:?Missing PROJECT_NAME}"

: "${PARTICIPANT_COUNT:=9}"
: "${CREATE_DIGITALOCEAN_DNS:=true}"
: "${CERTBOT_STAGING:=false}" #! true for testing

TEMPLATE="${SCRIPT_DIR}/cloud-init.template.yml"
CONFIG_DIR="${SCRIPT_DIR}/../participant-config"
ACCESS_FILE="${CONFIG_DIR}/access-details.csv"

PYTHON="${SCRIPT_DIR}/.venv/bin/python"

SSH_KEY_ID=$(doctl compute ssh-key list \
  --format ID,Name --no-header \
  | awk -v name="$SSH_KEY_NAME" '$2 == name {print $1; exit}')

VPC_UUID=$(doctl vpcs list --format ID,Name --no-header \
  | awk -v name="$VPC_NAME" '$2 == name {print $1; exit}')

SNAPSHOT_ID=$(doctl compute image list-user \
  --format ID,Name,Type,Distribution,MinDisk --no-header \
  | awk -v name="$SNAPSHOT_NAME" \
      '$2 == name && $3 == "snapshot" {print $1; exit}')

PROJECT_ID=$(doctl projects list --format ID,Name --no-header \
  | awk -v name="$PROJECT_NAME" '$2 == name {print $1; exit}')

[[ "$CREATE_DIGITALOCEAN_DNS" =~ ^(true|false)$ ]] || {
  echo "ERROR: CREATE_DIGITALOCEAN_DNS must be true or false" >&2
  exit 1
}

[[ "$CERTBOT_STAGING" =~ ^(true|false)$ ]] || {
  echo "ERROR: CERTBOT_STAGING must be true or false" >&2
  exit 1
}

wait_for_ssh() {
  local ip=$1
  local private_key=$2

  for attempt in $(seq 1 60); do
    if ssh -i "$private_key" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=5 \
      "student@${ip}" true 2>/dev/null; then
      return 0
    fi
    sleep 10
  done

  echo "ERROR: SSH did not become available on ${ip}."
  return 1
}

wait_for_dns() {
  local hostname=$1
  local expected_ip=$2
  local resolved_ips

  for attempt in $(seq 1 60); do
    resolved_ips=$(dig +short A "$hostname" | sort -u)

    if grep -Fxq "$expected_ip" <<< "$resolved_ips"; then
      echo "DNS ready: ${hostname} -> ${expected_ip}"
      return 0
    fi

    echo "Waiting for DNS: ${hostname} (${attempt}/60)"
    sleep 10
  done

  echo "ERROR: ${hostname} did not resolve to ${expected_ip}." >&2
  return 1
}

[ -f "$TEMPLATE" ] || {
  echo "ERROR: Missing template: $TEMPLATE"
  exit 1
}

for variable in SSH_KEY_ID VPC_UUID SNAPSHOT_ID PROJECT_ID; do
  [[ -n "${!variable:-}" ]] || {
    echo "ERROR: Could not resolve $variable" >&2
    exit 1
  }
done

[[ -x "$PYTHON" ]] || {
  echo "ERROR: Python environment not found: $PYTHON" >&2
  echo "Run: python3 -m venv .venv && .venv/bin/python -m pip install PyYAML" >&2
  exit 1
}

"$PYTHON" -c 'import yaml' >/dev/null 2>&1 || {
  echo "ERROR: PyYAML is not installed in .venv" >&2
  exit 1
}

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
touch .gitignore
if ! grep -Fxq "${CONFIG_DIR}/" ../.gitignore; then
  printf '%s/\n' "$(basename "$CONFIG_DIR")" >> ../.gitignore
fi

if [[ ! -e "$ACCESS_FILE" ]]; then
  printf '%s\n' \
    "vm_name,droplet_id,public_ip,hostname,code_password,db_password,ssh_private_key" \
    > "$ACCESS_FILE"
fi
chmod 600 "$ACCESS_FILE"

if [ "$CREATE_DIGITALOCEAN_DNS" = true ]; then
  if ! doctl compute domain list --no-header \
      | grep -Fq "$DOMAIN"; then
    echo "ERROR: ${DOMAIN} is not configured in DigitalOcean DNS."
    exit 1
  fi
fi

# provisioning loop
for number in $(seq 1 "$PARTICIPANT_COUNT"); do
  participant_id=$(printf '%02d' "$number")
  vm_name="dsi-${participant_id}"
  participant_hostname="${vm_name}.${DOMAIN}"
  cloud_init="${CONFIG_DIR}/cloud-init-${participant_id}.yml"
  private_key="${CONFIG_DIR}/${vm_name}-ssh"
  public_key="${private_key}.pub"

  echo "Provisioning ${vm_name} as ${participant_hostname}"
  trap 'echo "Provisioning failed for $participant_id" >&2' ERR

  if [ ! -f "$private_key" ]; then
    ssh-keygen -t ed25519 -a 100 -N "" \
      -C "${vm_name}-workshop" -f "$private_key"
  fi
  chmod 600 "$private_key"
  chmod 644 "$public_key"

  participant_ssh_public_key=$(cat "$public_key")
  db_password=$(openssl rand -hex 24)
  code_password=$(openssl rand -hex 16)

  PARTICIPANT_ID="$participant_id" \
  PARTICIPANT_HOSTNAME="$participant_hostname" \
  PARTICIPANT_SSH_PUBLIC_KEY="$participant_ssh_public_key" \
  CODE_PASSWORD="$code_password" \
  DB_PASSWORD="$db_password" \
  TEMPLATE="$TEMPLATE" \
  OUTPUT="$cloud_init" \
  "$PYTHON" <<'PY'
import os
from pathlib import Path

template = Path(os.environ["TEMPLATE"]).read_text()
replacements = {
    "__PARTICIPANT_ID__": os.environ["PARTICIPANT_ID"],
    "__PARTICIPANT_HOSTNAME__": os.environ["PARTICIPANT_HOSTNAME"],
    "__PARTICIPANT_SSH_PUBLIC_KEY__": os.environ["PARTICIPANT_SSH_PUBLIC_KEY"],
    "__CODE_PASSWORD__": os.environ["CODE_PASSWORD"],
    "__DB_PASSWORD__": os.environ["DB_PASSWORD"],
}
for placeholder, value in replacements.items():
    template = template.replace(placeholder, value)
for placeholder in replacements:
    if placeholder in template:
        raise RuntimeError(f"Unresolved placeholder: {placeholder}")
Path(os.environ["OUTPUT"]).write_text(template)
PY

  "$PYTHON" - <<'PY' "$cloud_init"
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    yaml.safe_load(stream)
PY

  chmod 600 "$cloud_init"

  existing_id=$(doctl compute droplet list --format ID,Name --no-header \
    | awk -v name="$vm_name" '$2 == name {print $1; exit}')
  if [ -n "$existing_id" ]; then
    echo "ERROR: Droplet ${vm_name} already exists as ${existing_id}."
    exit 1
  fi

  doctl compute droplet create "$vm_name" \
    --region "$REGION" \
    --size "$PARTICIPANT_SIZE" \
    --image "$SNAPSHOT_ID" \
    --ssh-keys "$SSH_KEY_ID" \
    --vpc-uuid "$VPC_UUID" \
    --tag-names "$WORKSHOP_TAG,$PARTICIPANT_TAG" \
    --enable-monitoring \
    --user-data-file "$cloud_init" \
    --wait

  droplet_id=$(doctl compute droplet list --format ID,Name --no-header \
    | awk -v name="$vm_name" '$2 == name {print $1; exit}')
  test -n "$droplet_id"

  public_ip=$(doctl compute droplet get "$droplet_id" \
    --format PublicIPv4 --no-header)
  test -n "$public_ip"

  doctl projects resources assign "$PROJECT_ID" \
    --resource "do:droplet:${droplet_id}"

  if [ "$CREATE_DIGITALOCEAN_DNS" = true ]; then
    existing_record_id=$(doctl compute domain records list "$DOMAIN" \
      --format ID,Type,Name,Data --no-header \
      | awk -v name="$vm_name" \
          '$2 == "A" && $3 == name {print $1; exit}')

    if [ -n "$existing_record_id" ]; then
      echo "ERROR: DNS record ${participant_hostname} already exists."
      exit 1
    fi

    doctl compute domain records create "$DOMAIN" \
      --record-type A \
      --record-name "$vm_name" \
      --record-data "$public_ip" \
      --record-ttl 300
  else
    echo "Create an A record now: ${participant_hostname} -> ${public_ip}"
  fi

  wait_for_ssh "$public_ip" "$private_key"

  ssh -i "$private_key" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    "student@${public_ip}" \
    "timeout 900 sudo cloud-init status --wait"

  ssh -i "$private_key" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    "student@${public_ip}" \
    "test -f /etc/dsi/provisioning-complete"

  wait_for_dns "$participant_hostname" "$public_ip"

  curl --silent --show-error --fail --max-time 15 \
    "http://${participant_hostname}/healthz"

  certbot_options=(
    --nginx
    --domain "$participant_hostname"
    --email "$CERTBOT_EMAIL"
    --agree-tos
    --non-interactive
    --redirect
    --keep-until-expiring
  )

  if [[ "$CERTBOT_STAGING" == true ]]; then
    certbot_options+=(
        --staging
        --config-dir /etc/letsencrypt-staging
        --work-dir /var/lib/letsencrypt-staging
        --logs-dir /var/log/letsencrypt-staging
    )
  fi

  printf -v certbot_command '%q ' \
    sudo certbot "${certbot_options[@]}"

  ssh -i "$private_key" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    "student@${public_ip}" \
    "$certbot_command"

  https_curl_options=(
    --silent
    --show-error
    --fail
    --max-time 15
    )

  if [[ "$CERTBOT_STAGING" == true ]]; then
    https_curl_options+=(--insecure)
  fi

  test "$(
    curl "${https_curl_options[@]}" \
        "https://${participant_hostname}/healthz"
  )" = "ok"

  http_status=$(curl --silent --output /dev/null \
    --write-out '%{http_code}' \
    "http://${participant_hostname}/healthz")

  [[ "$http_status" =~ ^30[12378]$ ]]

  printf '%s,%s,%s,%s,%s,%s,%s\n' \
    "$vm_name" "$droplet_id" "$public_ip" \
    "$participant_hostname" "$code_password" "$db_password" \
    "$private_key" >> "$ACCESS_FILE"

  echo "Ready: https://${participant_hostname}/"
done

chmod 600 "$ACCESS_FILE"
echo "Access details: ${ACCESS_FILE}"
