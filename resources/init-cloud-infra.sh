# init cloud infra
#!/usr/bin/env bash

# Authenticate doctl and Verify access
doctl auth init --context workshop

# Paste the PAT when prompted. Input may remain invisible while pasting.
# Activate that context:
doctl auth switch --context workshop

# verify
doctl auth list
doctl account get
doctl compute region list

# Define infrastructure variables
cd resources
chmod 600 workshop.env

CONFIG_FILE="${1:-./workshop.env}"

if [[ ! -r "$CONFIG_FILE" ]]; then
  printf 'Configuration file is not readable: %s\n' "$CONFIG_FILE" >&2
  exit 1
fi

source "$CONFIG_FILE"

required_variables=(
  PROJECT_NAME
  WORKSHOP_TAG
  REGION
  VPC_NAME
  VPC_RANGE
  BASE_IMAGE
  BUILDER_TAG
  BUILD_SIZE
  BUILDER_FIREWALL_NAME
  BUILD_DROPLET
  SNAPSHOT_NAME
  BOOTSTRAP_URL
  BOOTSTRAP_SHA256
  PARTICIPANT_TAG
  PARTICIPANT_SIZE
  PARTICIPANT_FIREWALL_NAME
  SSH_KEY_NAME
  SSH_PUBLIC_KEY_FILE
  ADMIN_CIDR
  VENUE_CIDR
  DOMAIN
  CERTBOT_EMAIL
)

for variable in "${required_variables[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    printf 'Missing required variable: %s\n' "$variable" >&2
    exit 1
  fi
done

# Check current availability before committing
doctl compute region list
doctl compute size list
doctl compute image list-distribution --public

# Create the administrator SSH key record
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/id_ed25519"
fi

if ! doctl compute ssh-key list --format Name --no-header \
    | grep -Fxq "$SSH_KEY_NAME"; then
  doctl compute ssh-key import "$SSH_KEY_NAME" \
    --public-key-file "$SSH_PUBLIC_KEY_FILE"
fi

SSH_KEY_ID=$(doctl compute ssh-key list \
  --format ID,Name --no-header \
  | awk -v name="$SSH_KEY_NAME" '$2 == name {print $1; exit}')

test -n "$SSH_KEY_ID"
echo "$SSH_KEY_ID"

# Create a Project
if ! doctl projects list --format Name --no-header \
    | grep -Fxq "$PROJECT_NAME"; then
  doctl projects create \
    --name "$PROJECT_NAME" \
    --description "DSI workshop infrastructure" \
    --purpose "Educational purposes"
fi

PROJECT_ID=$(doctl projects list --format ID,Name --no-header \
  | awk -v name="$PROJECT_NAME" '$2 == name {print $1; exit}')

test -n "$PROJECT_ID"
echo "$PROJECT_ID"

# Create the VPC
if ! doctl vpcs list --format Name --no-header | grep -Fxq "$VPC_NAME"; then
  doctl vpcs create \
    --name "$VPC_NAME" \
    --region "$REGION" \
    --ip-range "$VPC_RANGE" \
    --description "Private network for DSI workshop Droplets"
fi

VPC_UUID=$(doctl vpcs list --format ID,Name --no-header \
  | grep -F "$VPC_NAME" \
  | cut -d' ' -f1)

test -n "$VPC_UUID"
echo "$VPC_UUID"

# Cloud Firewall
for tag in "$WORKSHOP_TAG" "$BUILDER_TAG" "$PARTICIPANT_TAG"; do
  doctl compute tag create "$tag" 2>/dev/null || true
done

participant_ssh_rules="protocol:tcp,ports:22,address:${ADMIN_CIDR}"

if [[ "$VENUE_CIDR" != "$ADMIN_CIDR" ]]; then
  participant_ssh_rules+=" protocol:tcp,ports:22,address:${VENUE_CIDR}"
fi

participant_inbound_rules="${participant_ssh_rules} \
protocol:tcp,ports:80,address:0.0.0.0/0,address:::0/0 \
protocol:tcp,ports:443,address:0.0.0.0/0,address:::0/0"

if ! doctl compute firewall list \
    --format Name --no-header |
    grep -Fxq "$BUILDER_FIREWALL_NAME"; then

  doctl compute firewall create \
    --name "$BUILDER_FIREWALL_NAME" \
    --tag-names "$BUILDER_TAG" \
    --inbound-rules \
      "protocol:tcp,ports:22,address:${ADMIN_CIDR}" \
    --outbound-rules \
      "protocol:icmp,address:0.0.0.0/0,address:::0/0 protocol:tcp,ports:all,address:0.0.0.0/0,address:::0/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::0/0"
fi

if ! doctl compute firewall list \
    --format Name --no-header |
    grep -Fxq "$PARTICIPANT_FIREWALL_NAME"; then

  doctl compute firewall create \
    --name "$PARTICIPANT_FIREWALL_NAME" \
    --tag-names "$PARTICIPANT_TAG" \
    --inbound-rules "$participant_inbound_rules" \
    --outbound-rules \
      "protocol:icmp,address:0.0.0.0/0,address:::0/0 protocol:tcp,ports:all,address:0.0.0.0/0,address:::0/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::0/0"
fi
