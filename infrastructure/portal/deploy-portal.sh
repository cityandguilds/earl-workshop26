#!/usr/bin/env bash
# ==============================================================================
# EARL Workshop Portal: local DigitalOcean deployment orchestrator
# Run on your workstation, not on the Droplet.
# ============================================================================== 
set -Eeuo pipefail
umask 077
trap 'echo "ERROR: deployment failed at line ${LINENO}" >&2' ERR

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/deployment.env}"
[[ -r "$CONFIG_FILE" ]] || { echo "ERROR: Cannot read $CONFIG_FILE" >&2; exit 1; }
# shellcheck source=/dev/null
source "$CONFIG_FILE"

for command in doctl ssh ssh-keygen openssl curl dig awk grep sort seq base64 python3; do
  command -v "$command" >/dev/null || { echo "ERROR: $command is not installed." >&2; exit 1; }
done

: "${DOCTL_CONTEXT:=workshop}"
: "${DOMAIN:=earl.sjp-analytics.co.uk}"
: "${DNS_RECORD_NAME:=workshop}"
: "${SERVER_NAME:=${DNS_RECORD_NAME}.${DOMAIN}}"
: "${DROPLET_NAME:=workshop}"
: "${REGION:?Missing REGION}"
: "${SIZE:?Missing SIZE}"
: "${IMAGE:=ubuntu-24-04-x64}"
: "${SSH_KEY_NAME:?Missing SSH_KEY_NAME}"
: "${WORKSHOP_PASSWORD_HASH:?Missing WORKSHOP_PASSWORD_HASH}"
: "${CERTBOT_EMAIL:?Missing CERTBOT_EMAIL}"
: "${REPOSITORY_URL:=https://github.com/cityandguilds/earl-workshop26.git}"
: "${REPOSITORY_REF:=main}"
: "${FIREWALL_NAME:=earl-workshop-web}"
: "${PROJECT_NAME:=}"
: "${VPC_NAME:=}"
: "${CERTBOT_STAGING:=false}"
: "${DNS_TTL:=300}"
[[ "$CERTBOT_STAGING" =~ ^(true|false)$ ]] || { echo "ERROR: CERTBOT_STAGING must be true or false" >&2; exit 1; }
[[ "$SERVER_NAME" == "${DNS_RECORD_NAME}.${DOMAIN}" ]] || { echo "ERROR: SERVER_NAME does not match DNS settings" >&2; exit 1; }

doctl auth switch --context "$DOCTL_CONTEXT"
SSH_KEY_ID=$(doctl compute ssh-key list --format ID,Name --no-header | awk -v name="$SSH_KEY_NAME" '$2 == name {print $1; exit}')
[[ -n "$SSH_KEY_ID" ]] || { echo "ERROR: DigitalOcean SSH key not found: $SSH_KEY_NAME" >&2; exit 1; }
doctl compute domain get "$DOMAIN" >/dev/null 2>&1 || { echo "ERROR: $DOMAIN is not configured in DigitalOcean DNS." >&2; exit 1; }

PRIVATE_KEY="${SCRIPT_DIR}/${DROPLET_NAME}-ssh"
PUBLIC_KEY="${PRIVATE_KEY}.pub"
ACCESS_FILE="${SCRIPT_DIR}/access-details.env"
if [[ ! -f "$PRIVATE_KEY" ]]; then
  ssh-keygen -t ed25519 -a 100 -N '' -C "${DROPLET_NAME}-deployment" -f "$PRIVATE_KEY"
fi
chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"
SSH_PUBLIC_KEY=$(cat "$PUBLIC_KEY")
SESSION_SECRET=$(openssl rand -base64 48 | tr -d '\n')
VM_ENCRYPTION_KEY=$(python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)

existing_id=$(doctl compute droplet list --format ID,Name --no-header | awk -v name="$DROPLET_NAME" '$2 == name {print $1; exit}')
[[ -z "$existing_id" ]] || { echo "ERROR: Droplet $DROPLET_NAME already exists as $existing_id." >&2; exit 1; }

CLOUD_INIT=$(mktemp)
trap 'rm -f "$CLOUD_INIT"' EXIT
{
  echo '#!/usr/bin/env bash'
  printf 'export SSH_PUBLIC_KEY=%q\n' "$SSH_PUBLIC_KEY"
  printf 'export WORKSHOP_PASSWORD_HASH=%q\n' "$WORKSHOP_PASSWORD_HASH"
  printf 'export EARL_WORKSHOP_SESSION_SECRET=%q\n' "$SESSION_SECRET"
  printf 'export EARL_WORKSHOP_VM_ENCRYPTION_KEY=%q\n' "$VM_ENCRYPTION_KEY"
  printf 'export SERVER_NAME=%q\n' "$SERVER_NAME"
  printf 'export REPOSITORY_URL=%q\n' "$REPOSITORY_URL"
  printf 'export REPOSITORY_REF=%q\n' "$REPOSITORY_REF"
  cat "${SCRIPT_DIR}/provision-portal.sh"
} > "$CLOUD_INIT"
chmod 600 "$CLOUD_INIT"

create_args=(compute droplet create "$DROPLET_NAME" --region "$REGION" --size "$SIZE" --image "$IMAGE" --ssh-keys "$SSH_KEY_ID" --enable-monitoring --user-data-file "$CLOUD_INIT" --wait)
if [[ -n "$VPC_NAME" ]]; then
  VPC_UUID=$(doctl vpcs list --format ID,Name --no-header | awk -v name="$VPC_NAME" '$2 == name {print $1; exit}')
  [[ -n "$VPC_UUID" ]] || { echo "ERROR: VPC not found: $VPC_NAME" >&2; exit 1; }
  create_args+=(--vpc-uuid "$VPC_UUID")
fi
doctl "${create_args[@]}"

droplet_id=$(doctl compute droplet list --format ID,Name --no-header | awk -v name="$DROPLET_NAME" '$2 == name {print $1; exit}')
public_ip=$(doctl compute droplet get "$droplet_id" --format PublicIPv4 --no-header)
[[ -n "$public_ip" ]] || { echo "ERROR: Droplet has no public IPv4 address." >&2; exit 1; }

if [[ -n "$PROJECT_NAME" ]]; then
  PROJECT_ID=$(doctl projects list --format ID,Name --no-header | awk -v name="$PROJECT_NAME" '$2 == name {print $1; exit}')
  [[ -n "$PROJECT_ID" ]] || { echo "ERROR: Project not found: $PROJECT_NAME" >&2; exit 1; }
  doctl projects resources assign "$PROJECT_ID" --resource "do:droplet:${droplet_id}"
fi

INBOUND='protocol:tcp,ports:22,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:80,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:443,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0'
OUTBOUND='protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0'
firewall_id=$(doctl compute firewall list --format ID,Name --no-header | awk -v name="$FIREWALL_NAME" '$2 == name {print $1; exit}')
if [[ -n "$firewall_id" ]]; then
  doctl compute firewall update "$firewall_id" --name "$FIREWALL_NAME" --droplet-ids "$droplet_id" --inbound-rules "$INBOUND" --outbound-rules "$OUTBOUND"
else
  doctl compute firewall create --name "$FIREWALL_NAME" --droplet-ids "$droplet_id" --inbound-rules "$INBOUND" --outbound-rules "$OUTBOUND"
fi

dns_record_id=$(doctl compute domain records list "$DOMAIN" --format ID,Type,Name,Data --no-header | awk -v name="$DNS_RECORD_NAME" '$2 == "A" && $3 == name {print $1; exit}')
if [[ -n "$dns_record_id" ]]; then
  doctl compute domain records update "$DOMAIN" --record-id "$dns_record_id" --record-type A --record-name "$DNS_RECORD_NAME" --record-data "$public_ip" --record-ttl "$DNS_TTL"
else
  doctl compute domain records create "$DOMAIN" --record-type A --record-name "$DNS_RECORD_NAME" --record-data "$public_ip" --record-ttl "$DNS_TTL"
fi

SSH_OPTIONS=(-i "$PRIVATE_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ConnectionAttempts=1)
for attempt in $(seq 1 60); do
  ssh "${SSH_OPTIONS[@]}" "workshop@${public_ip}" true 2>/dev/null && break
  [[ "$attempt" -lt 60 ]] || { echo "ERROR: SSH did not become ready." >&2; exit 1; }
  sleep 10
done
for attempt in $(seq 1 120); do
  ssh "${SSH_OPTIONS[@]}" "workshop@${public_ip}" 'test -f /etc/earl-workshop/provisioning-complete' 2>/dev/null && break
  [[ "$attempt" -lt 120 ]] || { ssh "${SSH_OPTIONS[@]}" "workshop@${public_ip}" 'sudo tail -n 200 /var/log/cloud-init-output.log' >&2 || true; exit 1; }
  sleep 10
done
for attempt in $(seq 1 60); do
  dig +short A "$SERVER_NAME" | sort -u | grep -Fxq "$public_ip" && break
  [[ "$attempt" -lt 60 ]] || { echo "ERROR: DNS did not resolve to $public_ip." >&2; exit 1; }
  sleep 10
done
for attempt in $(seq 1 60); do
  curl --silent --show-error --fail --connect-timeout 5 --max-time 15 "http://${SERVER_NAME}/healthz" >/dev/null && break
  [[ "$attempt" -lt 60 ]] || { echo "ERROR: HTTP health check failed." >&2; exit 1; }
  sleep 5
done

certbot_options=(--nginx --domain "$SERVER_NAME" --email "$CERTBOT_EMAIL" --agree-tos --non-interactive --redirect --keep-until-expiring)
if [[ "$CERTBOT_STAGING" == true ]]; then
  certbot_options+=(--staging --config-dir /etc/letsencrypt-staging --work-dir /var/lib/letsencrypt-staging --logs-dir /var/log/letsencrypt-staging)
fi
printf -v certbot_command '%q ' sudo certbot "${certbot_options[@]}"
ssh "${SSH_OPTIONS[@]}" "workshop@${public_ip}" "$certbot_command"

curl_options=(--silent --show-error --fail --max-time 15)
[[ "$CERTBOT_STAGING" == true ]] && curl_options+=(--insecure)
[[ "$(curl "${curl_options[@]}" "https://${SERVER_NAME}/healthz")" == '{"status":"ok"}' ]] || { echo "ERROR: HTTPS health response was unexpected." >&2; exit 1; }

cat > "$ACCESS_FILE" <<EOF
DROPLET_ID=${droplet_id}
PUBLIC_IP=${public_ip}
SERVER_NAME=${SERVER_NAME}
SSH_USER=workshop
SSH_PRIVATE_KEY=${PRIVATE_KEY}
EOF
chmod 600 "$ACCESS_FILE"
echo "Ready: https://${SERVER_NAME}/"
echo "SSH: ssh -i ${PRIVATE_KEY} workshop@${SERVER_NAME}"
echo "Create portal admin: ssh -t -i ${PRIVATE_KEY} workshop@${SERVER_NAME} 'sudo earl-workshop-init create-admin'"
