#!/usr/bin/env bash
# ==============================================================================
# EARL Workshop Portal: Droplet-side provisioning
# Target: Ubuntu 24.04 LTS
# Run as root through cloud-init/user data or manually on a fresh Droplet.
# ============================================================================== 
set -Eeuo pipefail
umask 027
trap 'echo "ERROR: provisioning failed at line ${LINENO}" >&2' ERR

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
APP_USER="${APP_USER:-workshop}"
APP_GROUP="${APP_GROUP:-workshop}"
APP_ROOT="${APP_ROOT:-/opt/earl-workshop}"
APP_DIR="${APP_ROOT}/current"
DATA_DIR="${DATA_DIR:-/var/lib/earl-workshop}"
CACHE_DIR="${CACHE_DIR:-/var/cache/earl-workshop}"
ENV_DIR="${ENV_DIR:-/etc/earl-workshop}"
ENV_FILE="${ENV_DIR}/earl-workshop.env"
PYTHON_DIR="${PYTHON_DIR:-/opt/earl-workshop-python}"
SERVER_NAME="${SERVER_NAME:-workshop.earl.sjp-analytics.co.uk}"
REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/cityandguilds/earl-workshop26.git}"
REPOSITORY_REF="${REPOSITORY_REF:-main}"
UV_VERSION="${UV_VERSION:-0.12.23}"

: "${SSH_PUBLIC_KEY:?Set SSH_PUBLIC_KEY to the complete public key}"
: "${WORKSHOP_PASSWORD_HASH:?Set WORKSHOP_PASSWORD_HASH to an openssl passwd -6 hash}"
: "${EARL_WORKSHOP_SESSION_SECRET:?Set EARL_WORKSHOP_SESSION_SECRET}"
: "${EARL_WORKSHOP_VM_ENCRYPTION_KEY:?Set EARL_WORKSHOP_VM_ENCRYPTION_KEY}"

[[ "$SSH_PUBLIC_KEY" == ssh-ed25519\ * || "$SSH_PUBLIC_KEY" == sk-ssh-ed25519@openssh.com\ * ]] || {
  echo "ERROR: SSH_PUBLIC_KEY must be an Ed25519 public key." >&2
  exit 1
}
[[ "$WORKSHOP_PASSWORD_HASH" == '$6$'* ]] || {
  echo "ERROR: WORKSHOP_PASSWORD_HASH must be a SHA-512 crypt hash." >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive

# ==============================================================================
# 2. PACKAGES
# ==============================================================================
apt-get update
apt-get upgrade -y
apt-get install -y --no-install-recommends \
  ca-certificates certbot curl git nginx openssl python3-certbot-nginx sudo ufw

# ==============================================================================
# 3. WORKSHOP USER, PASSWORD-PROTECTED SUDO, AND SSH KEY
# ==============================================================================
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --groups sudo \
    --password "$WORKSHOP_PASSWORD_HASH" "$APP_USER"
else
  usermod --append --groups sudo "$APP_USER"
  usermod --password "$WORKSHOP_PASSWORD_HASH" "$APP_USER"
fi
rm -f "/etc/sudoers.d/${APP_USER}"
visudo --check

install -d -m 0700 -o "$APP_USER" -g "$APP_GROUP" "/home/${APP_USER}/.ssh"
printf '%s\n' "$SSH_PUBLIC_KEY" > "/home/${APP_USER}/.ssh/authorized_keys"
chown "$APP_USER:$APP_GROUP" "/home/${APP_USER}/.ssh/authorized_keys"
chmod 0600 "/home/${APP_USER}/.ssh/authorized_keys"

# ==============================================================================
# 4. SSH HARDENING
# ==============================================================================
cat > /etc/ssh/sshd_config.d/99-workshop-hardening.conf <<SSH
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PermitRootLogin no
PermitEmptyPasswords no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers ${APP_USER}
SSH
install -d -m 0755 /run/sshd
/usr/sbin/sshd -t
if systemctl list-unit-files ssh.socket --no-legend 2>/dev/null | grep -q '^ssh.socket'; then
  systemctl enable --now ssh.socket
  systemctl restart ssh.socket
else
  systemctl enable --now ssh.service
  systemctl reload-or-restart ssh.service
fi

# ==============================================================================
# 5. HOST FIREWALL
# ==============================================================================
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# ==============================================================================
# 6. UV AND PYTHON 3.13
# ==============================================================================
curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_INSTALL_DIR=/usr/local/bin sh
export UV_PYTHON_INSTALL_DIR="$PYTHON_DIR"
/usr/local/bin/uv python install 3.13

# ==============================================================================
# 7. APPLICATION DIRECTORIES AND SOURCE
# ==============================================================================
install -d -m 0755 -o root -g root "$APP_ROOT"
install -d -m 0750 -o "$APP_USER" -g "$APP_GROUP" \
  "$DATA_DIR" "$CACHE_DIR" "$CACHE_DIR/uv" "$PYTHON_DIR"
install -d -m 0750 -o root -g "$APP_GROUP" "$ENV_DIR"

if [[ -d "$APP_DIR/.git" ]]; then
  sudo -H -u "$APP_USER" git -C "$APP_DIR" fetch --depth 1 origin "$REPOSITORY_REF"
  sudo -H -u "$APP_USER" git -C "$APP_DIR" checkout --force FETCH_HEAD
else
  rm -rf "$APP_DIR"
  sudo -H -u "$APP_USER" git clone --depth 1 --branch "$REPOSITORY_REF" \
    "$REPOSITORY_URL" "$APP_DIR"
fi

# Ensure the runtime user owns every location uv and the application modify.
chown -R \
  "$APP_USER:$APP_GROUP" \
  "$APP_DIR" \
  "$DATA_DIR" \
  "$CACHE_DIR" \
  "$PYTHON_DIR"

sudo -H -u "$APP_USER" env \
  UV_PYTHON_INSTALL_DIR="$PYTHON_DIR" \
  UV_CACHE_DIR="$CACHE_DIR/uv" \
  /usr/local/bin/uv sync --directory "$APP_DIR" --frozen

# ==============================================================================
# 8. APPLICATION ENVIRONMENT
# ==============================================================================
cat > "$ENV_FILE" <<ENV
EARL_WORKSHOP_HOST=127.0.0.1
EARL_WORKSHOP_PORT=8000
EARL_WORKSHOP_DATA_DIR=${DATA_DIR}
EARL_WORKSHOP_PUBLIC_BASE_URL=https://${SERVER_NAME}
EARL_WORKSHOP_ENVIRONMENT=production
EARL_WORKSHOP_SECURE_COOKIES=true
EARL_WORKSHOP_SESSION_SECRET=${EARL_WORKSHOP_SESSION_SECRET}
EARL_WORKSHOP_VM_ENCRYPTION_KEY=${EARL_WORKSHOP_VM_ENCRYPTION_KEY}
ENV
chown root:"$APP_GROUP" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

# ==============================================================================
# 9. SYSTEMD SERVICE
# ==============================================================================
cat > /etc/systemd/system/earl-workshop.service <<SYSTEMD
[Unit]
Description=EARL Workshop FastAPI Portal
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
Environment=HOME=/home/${APP_USER}
Environment=UV_CACHE_DIR=${CACHE_DIR}/uv
Environment=UV_PYTHON_INSTALL_DIR=${PYTHON_DIR}
ExecStart=${APP_DIR}/.venv/bin/earl-workshop serve
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
LockPersonality=true
RestrictSUIDSGID=true
ReadWritePaths=${DATA_DIR} ${CACHE_DIR}

[Install]
WantedBy=multi-user.target
SYSTEMD

# ==============================================================================
# 10. NGINX HTTP REVERSE PROXY
# Certbot adds TLS directives after public DNS resolves.
# ==============================================================================
cat > /etc/nginx/sites-available/earl-workshop <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAME};
    server_tokens off;
    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
NGINX
ln -sfn /etc/nginx/sites-available/earl-workshop /etc/nginx/sites-enabled/earl-workshop
rm -f /etc/nginx/sites-enabled/default
nginx -t

# ==============================================================================
# 11. SERVICE ADMINISTRATION COMMAND
# ==============================================================================
install -m 0755 /dev/stdin /usr/local/sbin/earl-workshop-init <<'ADMIN'
#!/usr/bin/env bash
set -Eeuo pipefail
APP_USER="workshop"
APP_DIR="/opt/earl-workshop/current"
ENV_FILE="/etc/earl-workshop/earl-workshop.env"
SERVICE="earl-workshop.service"
DOMAIN="workshop.earl.sjp-analytics.co.uk"
ACTION="${1:-status}"
[[ "$EUID" -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
run_app() {
  sudo -H -u "$APP_USER" env HOME="/home/$APP_USER" bash -c \
    'set -a; source "$1"; set +a; cd "$2"; shift 2; exec "$@"' \
    bash "$ENV_FILE" "$APP_DIR" "$@"
}
usage() {
  echo "Usage: sudo earl-workshop-init {initialize|start|stop|restart|status|logs|health|update|create-admin|certificate|renew-certificate|test-renewal}"
}
case "$ACTION" in
  initialize) systemctl daemon-reload; systemctl enable --now nginx "$SERVICE" ;;
  start|stop|restart|status) systemctl "$ACTION" "$SERVICE" ;;
  logs) journalctl -u "$SERVICE" -f -n 100 ;;
  health) curl --fail --silent --show-error http://127.0.0.1:8000/healthz; echo ;;
  update)
    systemctl stop "$SERVICE"
    sudo -H -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
    sudo -H -u "$APP_USER" /usr/local/bin/uv sync --directory "$APP_DIR" --frozen
    systemctl start "$SERVICE"
    ;;
  create-admin) run_app "$APP_DIR/.venv/bin/earl-workshop" create-admin ;;
  certificate)
    : "${CERTBOT_EMAIL:?Run as: sudo CERTBOT_EMAIL=you@example.com earl-workshop-init certificate}"
    certbot --nginx --domain "$DOMAIN" --email "$CERTBOT_EMAIL" \
      --agree-tos --non-interactive --redirect --keep-until-expiring
    ;;
  renew-certificate) certbot renew; systemctl reload nginx ;;
  test-renewal) certbot renew --dry-run ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
ADMIN

# ==============================================================================
# 12. START AND VERIFY HTTP
# ==============================================================================
systemctl daemon-reload
systemctl enable --now nginx earl-workshop.service
for attempt in $(seq 1 60); do
  curl --fail --silent http://127.0.0.1:8000/healthz >/dev/null && break
  [[ "$attempt" -lt 60 ]] || { journalctl -u earl-workshop -n 100 --no-pager >&2; exit 1; }
  sleep 2
done
touch /etc/earl-workshop/provisioning-complete
echo "Droplet provisioning complete. DNS and Certbot are handled by deploy-digitalocean.sh."
