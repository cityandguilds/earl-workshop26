#!/usr/bin/env bash
set -euo pipefail
umask 077

require_command() {
  command -v "$1" >/dev/null || {
    echo "ERROR: $1 is not installed." >&2
    exit 1
  }
}

for command in doctl ssh ssh-keygen openssl curl dig awk grep sort seq base64 python3 perl; do
  require_command "$command"
done

if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_COMMAND=(timeout)
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_COMMAND=(gtimeout)
else
  TIMEOUT_COMMAND=(perl -e 'alarm shift; exec @ARGV')
fi
run_with_timeout() { local seconds=$1; shift; "${TIMEOUT_COMMAND[@]}" "$seconds" "$@"; }

cd resources
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
: "${REGION:?Missing REGION}"
: "${WORKSHOP_TAG:?Missing WORKSHOP_TAG}"
: "${CERTBOT_EMAIL:?Missing CERTBOT_EMAIL}"
: "${DOMAIN:=earl.sjp-analytics.co.uk}"
: "${ADMIN_VM_NAME:=workshop}"
: "${ADMIN_HOSTNAME:=workshop.${DOMAIN}}"
: "${ADMIN_SIZE:=${PARTICIPANT_SIZE:?Missing ADMIN_SIZE or PARTICIPANT_SIZE}}"
: "${ADMIN_TAG:=workshop-admin}"
: "${ADMIN_FIREWALL_NAME:=earl-workshop-admin}"
: "${CREATE_DIGITALOCEAN_DNS:=true}"
: "${CERTBOT_STAGING:=false}"
: "${REPOSITORY_URL:=https://github.com/cityandguilds/earl-workshop26.git}"
: "${REPOSITORY_REF:=main}"

[[ "$ADMIN_HOSTNAME" == "workshop.${DOMAIN}" ]] || {
  echo "ERROR: ADMIN_HOSTNAME must be workshop.${DOMAIN}" >&2
  exit 1
}
[[ "$CREATE_DIGITALOCEAN_DNS" =~ ^(true|false)$ ]] || {
  echo "ERROR: CREATE_DIGITALOCEAN_DNS must be true or false" >&2
  exit 1
}
[[ "$CERTBOT_STAGING" =~ ^(true|false)$ ]] || {
  echo "ERROR: CERTBOT_STAGING must be true or false" >&2
  exit 1
}

doctl auth init --context workshop
doctl auth switch --context workshop

SSH_KEY_ID=$(doctl compute ssh-key list --format ID,Name --no-header \
  | awk -v name="$SSH_KEY_NAME" '$2 == name {print $1; exit}')
VPC_UUID=$(doctl vpcs list --format ID,Name --no-header \
  | awk -v name="$VPC_NAME" '$2 == name {print $1; exit}')
SNAPSHOT_ID=$(doctl compute image list-user \
  --format ID,Name,Type,Distribution,MinDisk --no-header \
  | awk -v name="$SNAPSHOT_NAME" '$2 == name && $3 == "snapshot" {print $1; exit}')
PROJECT_ID=$(doctl projects list --format ID,Name --no-header \
  | awk -v name="$PROJECT_NAME" '$2 == name {print $1; exit}')
for variable in SSH_KEY_ID VPC_UUID SNAPSHOT_ID PROJECT_ID; do
  [[ -n "${!variable:-}" ]] || {
    echo "ERROR: Could not resolve $variable" >&2
    exit 1
  }
done

CONFIG_DIR="${SCRIPT_DIR}/../admin-config"
CLOUD_INIT="${CONFIG_DIR}/cloud-init-admin.yml"
PRIVATE_KEY="${CONFIG_DIR}/${ADMIN_VM_NAME}-ssh"
PUBLIC_KEY="${PRIVATE_KEY}.pub"
ACCESS_FILE="${CONFIG_DIR}/access-details.env"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [[ ! -f "$PRIVATE_KEY" ]]; then
  ssh-keygen -t ed25519 -a 100 -N "" \
    -C "${ADMIN_VM_NAME}-workshop" -f "$PRIVATE_KEY"
fi
chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"
ADMIN_SSH_PUBLIC_KEY=$(cat "$PUBLIC_KEY")
SESSION_SECRET=$(openssl rand -base64 48 | tr -d '\n')
VM_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '=\n')=

# Encode values before substitution so cloud-init remains valid even when values
# contain punctuation meaningful to YAML or shell.
SSH_KEY_B64=$(printf '%s' "$ADMIN_SSH_PUBLIC_KEY" | base64 -w0)
SESSION_SECRET_B64=$(printf '%s' "$SESSION_SECRET" | base64 -w0)
VM_KEY_B64=$(printf '%s' "$VM_ENCRYPTION_KEY" | base64 -w0)
REPO_URL_B64=$(printf '%s' "$REPOSITORY_URL" | base64 -w0)
REPO_REF_B64=$(printf '%s' "$REPOSITORY_REF" | base64 -w0)
HOSTNAME_B64=$(printf '%s' "$ADMIN_HOSTNAME" | base64 -w0)

cat > "$CLOUD_INIT" <<'CLOUD'
#cloud-config
hostname: workshop
fqdn: __HOSTNAME__
manage_etc_hosts: true
package_update: false
package_upgrade: false
users:
  - default
  - name: workshopadmin
    gecos: Workshop Administrator
    shell: /bin/bash
    groups: [sudo, docker]
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    lock_passwd: true
    ssh_authorized_keys:
      - __SSH_PUBLIC_KEY__
  - name: sam
    gecos: Workshop Team Member
    shell: /bin/bash
    groups: [docker]
    lock_passwd: true
    ssh_authorized_keys:
      - __SSH_PUBLIC_KEY__
  - name: ali
    gecos: Workshop Team Member
    shell: /bin/bash
    groups: [docker]
    lock_passwd: true
    ssh_authorized_keys:
      - __SSH_PUBLIC_KEY__
  - name: nel
    gecos: Workshop Team Member
    shell: /bin/bash
    groups: [docker]
    lock_passwd: true
    ssh_authorized_keys:
      - __SSH_PUBLIC_KEY__
write_files:
  - path: /etc/ssh/sshd_config.d/00-workshop-admin-hardening.conf
    owner: root:root
    permissions: "0644"
    content: |
      PasswordAuthentication no
      KbdInteractiveAuthentication no
      PubkeyAuthentication yes
      PermitRootLogin no
      X11Forwarding no
      AllowUsers workshopadmin sam ali nel
      MaxAuthTries 3
  - path: /etc/nginx/sites-available/earl-workshop
    owner: root:root
    permissions: "0644"
    content: |
      server {
          # The golden image already contains the participant default site.
          # This named vhost must not also claim the default listener.
          listen 80;
          listen [::]:80;
          server_name __HOSTNAME__;
          client_max_body_size 10m;
          location / {
              proxy_pass http://127.0.0.1:8000;
              proxy_http_version 1.1;
              proxy_set_header Host $host;
              proxy_set_header X-Real-IP $remote_addr;
              proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
              proxy_set_header X-Forwarded-Proto $scheme;
          }
      }
  - path: /etc/systemd/system/earl-workshop.service
    owner: root:root
    permissions: "0644"
    content: |
      [Unit]
      Description=EARL 2026 Workshop Portal
      After=network-online.target
      Wants=network-online.target
      StartLimitIntervalSec=60
      StartLimitBurst=5

      [Service]
      Type=simple
      User=workshopadmin
      Group=workshopadmin
      WorkingDirectory=/opt/earl-workshop
      EnvironmentFile=/etc/earl-workshop/earl-workshop.env
      Environment=HOME=/home/workshopadmin
      Environment=UV_CACHE_DIR=/var/cache/earl-workshop/uv
      Environment=UV_PYTHON_INSTALL_DIR=/opt/earl-workshop-python
      ExecStart=/opt/earl-workshop/.venv/bin/earl-workshop serve
      Restart=on-failure
      RestartSec=5
      NoNewPrivileges=true
      PrivateTmp=true
      ProtectSystem=strict
      ProtectHome=true
      ReadWritePaths=/var/lib/earl-workshop /var/cache/earl-workshop

      [Install]
      WantedBy=multi-user.target
  - path: /root/configure-admin.sh
    owner: root:root
    permissions: "0700"
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      trap 'echo "Admin configuration failed at line $LINENO" >&2' ERR
      decode() { printf '%s' "$1" | base64 -d; }
      repo_url=$(decode '__REPO_URL_B64__')
      repo_ref=$(decode '__REPO_REF_B64__')
      portal_hostname=$(decode '__HOSTNAME_B64__')
      session_secret=$(decode '__SESSION_SECRET_B64__')
      vm_key=$(decode '__VM_KEY_B64__')

      install -d -m 0755 /etc/dsi
      install -d -o workshopadmin -g workshopadmin -m 0750 \
        /var/lib/earl-workshop /var/cache/earl-workshop \
        /var/cache/earl-workshop/uv /opt/earl-workshop-python \
        /etc/earl-workshop
      chown workshopadmin:workshopadmin /home/workshopadmin
      chmod 0750 /home/workshopadmin

      # Install uv system-wide from its official installer, then install Python 3.13.
      export UV_INSTALL_DIR=/usr/local/bin
      export UV_PYTHON_INSTALL_DIR=/opt/earl-workshop-python
      curl -LsSf https://astral.sh/uv/install.sh | sh
      sudo -H -u workshopadmin env \
        UV_PYTHON_INSTALL_DIR=/opt/earl-workshop-python \
        /usr/local/bin/uv python install 3.13

      if [[ -d /opt/earl-workshop/.git ]]; then
        git -C /opt/earl-workshop fetch --depth 1 origin "$repo_ref"
        git -C /opt/earl-workshop checkout --force FETCH_HEAD
      else
        rm -rf /opt/earl-workshop
        git clone --depth 1 --branch "$repo_ref" "$repo_url" /opt/earl-workshop
      fi
      chown -R workshopadmin:workshopadmin /opt/earl-workshop
      sudo -H -u workshopadmin env \
        UV_PYTHON_INSTALL_DIR=/opt/earl-workshop-python \
        UV_CACHE_DIR=/var/cache/earl-workshop/uv \
        /usr/local/bin/uv sync \
        --directory /opt/earl-workshop --frozen

      cat > /etc/earl-workshop/earl-workshop.env <<ENV
      EARL_WORKSHOP_HOST=127.0.0.1
      EARL_WORKSHOP_PORT=8000
      EARL_WORKSHOP_DATA_DIR=/var/lib/earl-workshop
      EARL_WORKSHOP_PUBLIC_BASE_URL=https://${portal_hostname}
      EARL_WORKSHOP_ENVIRONMENT=production
      EARL_WORKSHOP_SECURE_COOKIES=true
      EARL_WORKSHOP_SESSION_SECRET=${session_secret}
      EARL_WORKSHOP_VM_ENCRYPTION_KEY=${vm_key}
      ENV
      chown root:workshopadmin /etc/earl-workshop/earl-workshop.env
      chmod 0640 /etc/earl-workshop/earl-workshop.env

      rm -f /etc/nginx/sites-enabled/default
      ln -sfn /etc/nginx/sites-available/earl-workshop \
        /etc/nginx/sites-enabled/earl-workshop
      install -d -o root -g root -m 0755 /run/sshd
      /usr/sbin/sshd -t
      nginx -t
      test -x /opt/earl-workshop/.venv/bin/python
      test -x /opt/earl-workshop/.venv/bin/earl-workshop
      resolved_python=$(readlink -f /opt/earl-workshop/.venv/bin/python)
      case "$resolved_python" in
        /opt/earl-workshop-python/*) ;;
        *)
          echo "Unexpected virtualenv interpreter: $resolved_python" >&2
          exit 1
          ;;
      esac
      sudo -H -u workshopadmin \
        /opt/earl-workshop/.venv/bin/python --version

      systemctl daemon-reload
      if systemctl list-unit-files ssh.socket --no-legend 2>/dev/null | grep -q '^ssh.socket'; then
        systemctl enable --now ssh.socket
        systemctl restart ssh.socket
        systemctl is-active --quiet ssh.socket
      else
        systemctl enable --now ssh.service
        systemctl reload-or-restart ssh.service
        systemctl is-active --quiet ssh.service
      fi
      systemctl enable --now nginx earl-workshop
      systemctl is-active --quiet nginx
      systemctl is-active --quiet earl-workshop
      for attempt in $(seq 1 60); do
        curl --fail --silent http://127.0.0.1:8000/healthz >/dev/null && break
        [[ "$attempt" -lt 60 ]] || {
          journalctl -u earl-workshop -n 100 --no-pager >&2
          exit 1
        }
        sleep 2
      done
      touch /etc/dsi/admin-provisioning-complete
      rm -f /root/configure-admin.sh
runcmd:
  - [bash, /root/configure-admin.sh]
final_message: "EARL workshop admin configuration completed"
CLOUD

ADMIN_HOSTNAME="$ADMIN_HOSTNAME" \
ADMIN_SSH_PUBLIC_KEY="$ADMIN_SSH_PUBLIC_KEY" \
REPO_URL_B64="$REPO_URL_B64" \
REPO_REF_B64="$REPO_REF_B64" \
HOSTNAME_B64="$HOSTNAME_B64" \
SESSION_SECRET_B64="$SESSION_SECRET_B64" \
VM_KEY_B64="$VM_KEY_B64" \
python3 - "$CLOUD_INIT" <<'PY'
import os
import sys
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
values = {
    "__HOSTNAME__": os.environ["ADMIN_HOSTNAME"],
    "__SSH_PUBLIC_KEY__": os.environ["ADMIN_SSH_PUBLIC_KEY"],
    "__REPO_URL_B64__": os.environ["REPO_URL_B64"],
    "__REPO_REF_B64__": os.environ["REPO_REF_B64"],
    "__HOSTNAME_B64__": os.environ["HOSTNAME_B64"],
    "__SESSION_SECRET_B64__": os.environ["SESSION_SECRET_B64"],
    "__VM_KEY_B64__": os.environ["VM_KEY_B64"],
}
for key, value in values.items():
    text = text.replace(key, value)
if "__" in text:
    unresolved = sorted({part for part in text.split() if part.startswith("__")})
    raise RuntimeError(f"Possible unresolved placeholders: {unresolved}")
path.write_text(text)
PY
chmod 600 "$CLOUD_INIT"

existing_id=$(doctl compute droplet list --format ID,Name --no-header \
  | awk -v name="$ADMIN_VM_NAME" '$2 == name {print $1; exit}')
[[ -z "$existing_id" ]] || {
  echo "ERROR: Droplet ${ADMIN_VM_NAME} already exists as ${existing_id}." >&2
  exit 1
}

if [[ "$CREATE_DIGITALOCEAN_DNS" == true ]]; then
  ! doctl compute domain list --no-header | grep -Fxq "$DOMAIN" || {
    echo "ERROR: ${DOMAIN} is not configured in DigitalOcean DNS." >&2
    exit 1
  }
fi

echo "Creating ${ADMIN_VM_NAME} as ${ADMIN_HOSTNAME}"
doctl compute droplet create "$ADMIN_VM_NAME" \
  --region "$REGION" \
  --size "$ADMIN_SIZE" \
  --image "$SNAPSHOT_ID" \
  --ssh-keys "$SSH_KEY_ID" \
  --vpc-uuid "$VPC_UUID" \
  --tag-names "$WORKSHOP_TAG,$ADMIN_TAG" \
  --enable-monitoring \
  --user-data-file "$CLOUD_INIT" \
  --wait

droplet_id=$(doctl compute droplet list --format ID,Name --no-header \
  | awk -v name="$ADMIN_VM_NAME" '$2 == name {print $1; exit}')
[[ -n "$droplet_id" ]]
public_ip=$(doctl compute droplet get "$droplet_id" --format PublicIPv4 --no-header)
[[ -n "$public_ip" ]]
doctl projects resources assign "$PROJECT_ID" --resource "do:droplet:${droplet_id}"

# Network policy: public key-only SSH plus HTTP/HTTPS.
FIREWALL_INBOUND_RULES='protocol:tcp,ports:22,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:80,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:443,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0'
FIREWALL_OUTBOUND_RULES='protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0'
firewall_id=$(doctl compute firewall list --format ID,Name --no-header | awk -v name="$ADMIN_FIREWALL_NAME" '$2 == name {print $1; exit}')
if [[ -n "$firewall_id" ]]; then
  doctl compute firewall update "$firewall_id" --name "$ADMIN_FIREWALL_NAME" --droplet-ids "$droplet_id" --inbound-rules "$FIREWALL_INBOUND_RULES" --outbound-rules "$FIREWALL_OUTBOUND_RULES"
else
  doctl compute firewall create --name "$ADMIN_FIREWALL_NAME" --droplet-ids "$droplet_id" --inbound-rules "$FIREWALL_INBOUND_RULES" --outbound-rules "$FIREWALL_OUTBOUND_RULES"
fi

if [[ "$CREATE_DIGITALOCEAN_DNS" == true ]]; then
  dns_record_id=$(doctl compute domain records list "$DOMAIN" --format ID,Type,Name,Data --no-header | awk -v name="$ADMIN_VM_NAME" '$2 == "A" && $3 == name {print $1; exit}')
  if [[ -n "$dns_record_id" ]]; then
    doctl compute domain records update "$DOMAIN" --record-id "$dns_record_id" --record-type A --record-name "$ADMIN_VM_NAME" --record-data "$public_ip" --record-ttl 300
  else
    doctl compute domain records create "$DOMAIN" --record-type A --record-name "$ADMIN_VM_NAME" --record-data "$public_ip" --record-ttl 300
  fi
else
  echo "Create or update an A record: ${ADMIN_HOSTNAME} -> ${public_ip} (TTL 300)"
fi

wait_for_ssh() {
  for attempt in $(seq 1 60); do
    if ssh -i "$PRIVATE_KEY" -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
      "workshopadmin@${public_ip}" true 2>/dev/null; then
      return 0
    fi
    sleep 10
  done
  echo "ERROR: SSH did not become available on ${public_ip}." >&2
  return 1
}
wait_for_dns() {
  for attempt in $(seq 1 60); do
    if dig +short A "$ADMIN_HOSTNAME" | sort -u | grep -Fxq "$public_ip"; then
      return 0
    fi
    sleep 10
  done
  echo "ERROR: ${ADMIN_HOSTNAME} did not resolve to ${public_ip}." >&2
  return 1
}

SSH_OPTIONS=(
  -i "$PRIVATE_KEY"
  -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=10
  -o ConnectionAttempts=1
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
)

wait_for_provisioning() {
  local attempt
  local status

  for attempt in $(seq 1 120); do
    if run_with_timeout 20 ssh "${SSH_OPTIONS[@]}" \
      "workshopadmin@${public_ip}" \
      "test -f /etc/dsi/admin-provisioning-complete"
    then
      echo "Admin provisioning completed."
      return 0
    fi

    status=$(
      run_with_timeout 20 ssh "${SSH_OPTIONS[@]}" \
        "workshopadmin@${public_ip}" \
        "sudo cloud-init status --long 2>&1 || true" \
        2>/dev/null || true
    )

    printf 'Waiting for admin provisioning (%s/120): %s\n' \
      "$attempt" "${status//$'\n'/; }"

    if grep -Eq 'status: (error|degraded)' <<<"$status"; then
      echo "ERROR: cloud-init reported a failure." >&2

      run_with_timeout 30 ssh "${SSH_OPTIONS[@]}" \
        "workshopadmin@${public_ip}" \
        "sudo tail -n 200 /var/log/cloud-init-output.log;
         sudo journalctl -u cloud-final.service -n 100 --no-pager" \
        >&2 || true

      return 1
    fi

    sleep 10
  done

  echo "ERROR: Admin provisioning did not finish within 20 minutes." >&2

  run_with_timeout 30 ssh "${SSH_OPTIONS[@]}" \
    "workshopadmin@${public_ip}" \
    "sudo cloud-init status --long;
     sudo tail -n 200 /var/log/cloud-init-output.log;
     sudo journalctl -u cloud-final.service -n 100 --no-pager" \
    >&2 || true

  return 1
}

wait_for_http() {
  local url=$1
  local description=$2
  local attempt

  for attempt in $(seq 1 60); do
    if curl \
      --silent \
      --show-error \
      --fail \
      --connect-timeout 5 \
      --max-time 15 \
      "$url" \
      >/dev/null
    then
      echo "${description} is ready."
      return 0
    fi

    echo "Waiting for ${description} (${attempt}/60)"
    sleep 5
  done

  echo "ERROR: ${description} did not become ready." >&2
  return 1
}

wait_for_ssh
wait_for_provisioning
wait_for_dns
wait_for_http \
  "http://${ADMIN_HOSTNAME}/healthz" \
  "portal HTTP health check"

certbot_options=(--nginx --domain "$ADMIN_HOSTNAME" --email "$CERTBOT_EMAIL" \
  --agree-tos --non-interactive --redirect --keep-until-expiring)
if [[ "$CERTBOT_STAGING" == true ]]; then
  certbot_options+=(--staging --config-dir /etc/letsencrypt-staging \
    --work-dir /var/lib/letsencrypt-staging \
    --logs-dir /var/log/letsencrypt-staging)
fi
printf -v certbot_command '%q ' sudo certbot "${certbot_options[@]}"
ssh -i "$PRIVATE_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "workshopadmin@${public_ip}" "$certbot_command"

curl_options=(--silent --show-error --fail --max-time 15)
[[ "$CERTBOT_STAGING" == true ]] && curl_options+=(--insecure)
test "$(curl "${curl_options[@]}" "https://${ADMIN_HOSTNAME}/healthz")" = \
  '{"status":"ok"}'

cat > "$ACCESS_FILE" <<EOF
ADMIN_VM_NAME=${ADMIN_VM_NAME}
DROPLET_ID=${droplet_id}
PUBLIC_IP=${public_ip}
ADMIN_HOSTNAME=${ADMIN_HOSTNAME}
SSH_USER=workshopadmin
SSH_PRIVATE_KEY=${PRIVATE_KEY}
EARL_WORKSHOP_SESSION_SECRET=${SESSION_SECRET}
EARL_WORKSHOP_VM_ENCRYPTION_KEY=${VM_ENCRYPTION_KEY}
EOF
chmod 600 "$ACCESS_FILE"

echo "Ready: https://${ADMIN_HOSTNAME}/"
echo "Secrets and access details: ${ACCESS_FILE}"
echo "Create the first portal administrator interactively with:"
echo "ssh -t -i \"${PRIVATE_KEY}\" \"workshopadmin@${ADMIN_HOSTNAME}\" \"sudo -u workshopadmin bash -lc 'set -a; source /etc/earl-workshop/earl-workshop.env; set +a; cd /opt/earl-workshop; exec .venv/bin/earl-workshop create-admin'\""
