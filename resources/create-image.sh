# build golden image
#!/usr/bin/env bash

# switches between remote and local execution
#! cannot run as an unsupervised script

if ! [[ -t 0 && -t 1 ]]; then
    echo "ERROR: This script must be run interactively." >&2
    exit 1
fi

# load/generate env vars
cd resources
# chmod 600 workshop.env

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

init_builder_variables=(
  BUILD_DROPLET
  REGION
  BUILD_SIZE
  BASE_IMAGE
  SSH_KEY_ID
  VPC_UUID
  BUILDER_TAG
  WORKSHOP_TAG
)

SSH_KEY_ID=$(doctl compute ssh-key list \
  --format ID,Name --no-header \
  | awk -v name="$SSH_KEY_NAME" '$2 == name {print $1; exit}')

VPC_UUID=$(doctl vpcs list --format ID,Name --no-header \
  | grep -F "$VPC_NAME" \
  | cut -d' ' -f1)

for variable in "${init_builder_variables[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    printf 'Missing required variable: %s\n' "$variable" >&2
    exit 1
  fi
done

# create droplet
doctl compute droplet create "$BUILD_DROPLET" \
  --region "$REGION" \
  --size "$BUILD_SIZE" \
  --image "$BASE_IMAGE" \
  --ssh-keys "$SSH_KEY_ID" \
  --vpc-uuid "$VPC_UUID" \
  --tag-names "$WORKSHOP_TAG,$BUILDER_TAG" \
  --enable-monitoring \
  --wait

BUILD_ID=$(doctl compute droplet list --format ID,Name --no-header \
  | awk -v name="$BUILD_DROPLET" '$2 == name {print $1; exit}')

BUILD_IP=$(doctl compute droplet get "$BUILD_ID" \
  --format PublicIPv4 --no-header)

PROJECT_ID=$(doctl projects list --format ID,Name --no-header \
  | grep -F " $PROJECT_NAME" \
  | awk '{print $1}')

doctl projects resources assign "$PROJECT_ID" \
  --resource "do:droplet:$BUILD_ID"

echo "$BUILD_ID $BUILD_IP"

# on remote - install software
ssh "root@${BUILD_IP}"

curl -fsSL "$BOOTSTRAP_URL" -o /tmp/bootstrap.sh
printf '%s  %s\n' "$BOOTSTRAP_SHA256" /tmp/bootstrap.sh \
  | sha256sum --check
chmod 700 /tmp/bootstrap.sh
sudo /tmp/bootstrap.sh

# test install
docker --version
docker compose version
R --version
python3 --version
quarto --version
java --version
psql --version
nginx -v
code-server --version
certbot --version

sudo systemctl status docker --no-pager
sudo systemctl status postgresql --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status shiny-server --no-pager
sudo systemctl status shinyproxy --no-pager
sudo systemctl status certbot.timer --no-pager

sudo ss -lntp
sudo nginx -t
curl --head http://127.0.0.1:3838/
curl --head http://127.0.0.1:8080/
curl --head http://127.0.0.1:8081/
curl --head http://127.0.0.1:8000/docs
sudo -u postgres psql -Atc "show listen_addresses;"

# clean VM
sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/*
sudo rm -rf /tmp/* /var/tmp/*
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s

sudo rm -rf /root/.config/doctl /root/.docker /root/.config/gh
sudo rm -f /root/.bash_history
rm -rf "$HOME/.config/doctl" "$HOME/.docker" "$HOME/.config/gh"
rm -f "$HOME/.bash_history"

sudo rm -f /etc/dsi/participant.env
sudo rm -f /home/student/.config/dsi/database.env

sudo cloud-init clean --logs --seed
sudo truncate -s 0 /etc/machine-id
sudo rm -f /var/lib/dbus/machine-id
sudo rm -f /etc/ssh/ssh_host_*

sync
sudo poweroff

# create snapshot (back local)
BUILD_ID=$(doctl compute droplet list --format ID,Name,Status --no-header \
  | awk -v name="$BUILD_DROPLET" '$2 == name {print $1; exit}')

doctl compute droplet-action snapshot "$BUILD_ID" \
  --snapshot-name "$SNAPSHOT_NAME" \
  --wait

SNAPSHOT_ID=$(doctl compute image list-user \
  --format ID,Name,Type,Distribution,MinDisk --no-header \
  | awk -v name="$SNAPSHOT_NAME" \
      '$2 == name && $3 == "snapshot" {print $1; exit}')

test -n "$SNAPSHOT_ID"
echo "$SNAPSHOT_ID"

# delete droplet
doctl compute droplet list \
  --format ID,Name,PublicIPv4,Status,Region
BUILD_ID=$(doctl compute droplet list --format ID,Name --no-header \
| awk -v name="$BUILD_DROPLET" '$2 == name {print $1; exit}')
doctl compute droplet delete $BUILD_ID --force
