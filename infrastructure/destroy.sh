#!/usr/bin/env bash
set -euo pipefail

doctl auth init --context workshop
doctl auth switch --context workshop

cd infrastructure/
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/config/workshop.env}"
[[ -r "$CONFIG_FILE" ]] || {
  echo "ERROR: Cannot read $CONFIG_FILE" >&2
  exit 1
}
source "$CONFIG_FILE"

DROPLET_IDS=$(doctl compute droplet list \
  --tag-name "$PARTICIPANT_TAG" \
  --format ID --no-header | tr '\n' ' ')

if [ -n "${DROPLET_IDS// }" ]; then
  doctl compute droplet delete $DROPLET_IDS --force
fi

shred -u participant-config/cloud-init-*.yml 2>/dev/null || true
shred -u participant-config/access-details.csv 2>/dev/null || true
shred -u participant-config/dsi-*-ssh 2>/dev/null || true
rm -f participant-config/dsi-*-ssh.pub
