#!/usr/bin/env bash

# Golden-image build script for Ubuntu 24.04 (Noble), amd64.
#
# This image contains shared workshop software and service definitions.
# Participant-specific settings such as SSH keys, passwords, hostnames,
# databases, TLS certificates, and participant services are applied later by
# cloud-init or the provisioning script.

set -Eeuo pipefail
umask 022
export DEBIAN_FRONTEND=noninteractive

readonly EXPECTED_UBUNTU_CODENAME="noble"
readonly CRAN_KEY_FINGERPRINT="E298A3A825C0D65DFD57CBB651716619E084DAB9"
readonly CRAN_KEYRING="/etc/apt/keyrings/cran-ubuntu.asc"

log() {
  printf '\n===== %s =====\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local exit_code=$?
  printf '\nERROR: bootstrap failed at line %s: %s\n' "${BASH_LINENO[0]}" "${BASH_COMMAND}" >&2
  exit "$exit_code"
}
trap on_error ERR

wait_for_http() {
  local url="$1"
  local service="$2"
  local attempts="${3:-30}"
  local delay="${4:-2}"
  local attempt

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl --fail --silent --show-error --output /dev/null "$url"; then
      printf '%s is ready\n' "$service"
      return 0
    fi

    if ! systemctl is-active --quiet "$service"; then
      journalctl -u "$service" -n 100 --no-pager >&2 || true
      fail "$service stopped during startup"
    fi

    sleep "$delay"
  done

  journalctl -u "$service" -n 100 --no-pager >&2 || true
  fail "$service readiness timeout waiting for $url"
}

check_listening_port() {
  local port="$1"
  local service="$2"

  if ! ss -H -lnt | awk -v endpoint="127.0.0.1:${port}" '$4 == endpoint { found = 1 } END { exit !found }'; then
    fail "$service is not listening on 127.0.0.1:${port}"
  fi
}

log "Validating build host"

[[ "$(id -u)" -eq 0 ]] || fail "run this script as root"
[[ "$(dpkg --print-architecture)" == "amd64" ]] || fail "only amd64 is supported"

. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "only Ubuntu is supported"
[[ "${VERSION_CODENAME:-}" == "$EXPECTED_UBUNTU_CODENAME" ]] ||
  fail "expected Ubuntu ${EXPECTED_UBUNTU_CODENAME}, found ${VERSION_CODENAME:-unknown}"

log "Updating Ubuntu"

apt-get update
apt-get upgrade -y

# Install the tools needed to configure third-party repositories before using
# wget, gpg, or add-apt-repository.
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg \
  software-properties-common \
  wget

log "Configuring the CRAN repository"

install -d -m 0755 /etc/apt/keyrings
wget --quiet --output-document="$CRAN_KEYRING" \
  https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc

actual_cran_fingerprint="$(
  gpg --show-keys --with-colons "$CRAN_KEYRING" |
    awk -F: '$1 == "fpr" { print $10; exit }'
)"
[[ "$actual_cran_fingerprint" == "$CRAN_KEY_FINGERPRINT" ]] ||
  fail "unexpected CRAN signing-key fingerprint"

cat > /etc/apt/sources.list.d/cran-r.list <<EOF
deb [signed-by=${CRAN_KEYRING}] https://cloud.r-project.org/bin/linux/ubuntu ${EXPECTED_UBUNTU_CODENAME}-cran40/
EOF

log "Installing system packages"

apt-get update
apt-get install -y --no-install-recommends \
  apt-transport-https \
  build-essential \
  certbot \
  git \
  jq \
  libcurl4-openssl-dev \
  libpq-dev \
  libssl-dev \
  libuv1-dev \
  libxml2-dev \
  lsb-release \
  nginx \
  openjdk-21-jdk \
  openssl \
  pkg-config \
  postgresql \
  postgresql-contrib \
  python3 \
  python3-certbot-nginx \
  python3-pip \
  python3-venv \
  r-base \
  r-base-dev \
  unzip

log "Creating workshop accounts and directories"

if ! id student >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash student
fi

if ! id fastapi >/dev/null 2>&1; then
  useradd \
    --system \
    --create-home \
    --home-dir /home/fastapi \
    --shell /usr/sbin/nologin \
    fastapi
fi

install -d -o student -g student -m 0700 \
  /home/student/.config \
  /home/student/.config/code-server \
  /home/student/.config/dsi

install -d -o fastapi -g fastapi -m 0700 \
  /home/fastapi/.config \
  /home/fastapi/.config/dsi

install -d -o root -g root -m 0755 /etc/dsi

log "Installing R packages"

Rscript --vanilla <<'RSCRIPT'
packages <- c(
  "shiny",
  "RPostgres",
  "DBI",
  "httr",
  "jsonlite",
  "knitr",
  "rmarkdown",
  "quarto",
  "ggplot2"
)

missing <- setdiff(packages, rownames(installed.packages()))
if (length(missing) > 0L) {
  install.packages(
    missing,
    repos = "https://cloud.r-project.org",
    Ncpus = 1L
  )
}

failed <- packages[
  !vapply(packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(failed) > 0L) {
  stop("R package verification failed: ", paste(failed, collapse = ", "))
}
RSCRIPT

log "Installing Shiny Server"

readonly SHINY_SERVER_VERSION="1.5.23.1030"
readonly SHINY_SERVER_DEB="/tmp/shiny-server.deb"
readonly SHINY_SERVER_URL="https://download3.rstudio.org/ubuntu-20.04/x86_64/shiny-server-${SHINY_SERVER_VERSION}-amd64.deb"

wget \
  --https-only \
  --tries=5 \
  --timeout=30 \
  --output-document="$SHINY_SERVER_DEB" \
  "$SHINY_SERVER_URL"

dpkg-deb --info "$SHINY_SERVER_DEB" >/dev/null
apt-get install -y "$SHINY_SERVER_DEB"
rm -f "$SHINY_SERVER_DEB"

cat > /etc/shiny-server/shiny-server.conf <<'CONF'
run_as shiny;

server {
  listen 3838 127.0.0.1;

  location / {
    site_dir /srv/shiny-server;
    log_dir /var/log/shiny-server;
    directory_index on;
  }
}
CONF

log "Installing FastAPI"

python3 -m venv /opt/dsi-fastapi-venv
/opt/dsi-fastapi-venv/bin/python -m pip install --upgrade pip
/opt/dsi-fastapi-venv/bin/python -m pip install \
  fastapi \
  pandas \
  psycopg2-binary \
  sqlalchemy \
  uvicorn

# A minimal placeholder app lets the image build validate the complete FastAPI
# service and Nginx route. Participants replace or extend this package later.
install -d -o root -g fastapi -m 0750 /opt/dsi-fastapi/app
install -o root -g fastapi -m 0640 /dev/null /opt/dsi-fastapi/app/__init__.py

cat > /opt/dsi-fastapi/app/main.py <<'PYTHON'
from fastapi import FastAPI

app = FastAPI(title="DSI Workshop API")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
PYTHON

chown root:fastapi /opt/dsi-fastapi/app/main.py
chmod 0640 /opt/dsi-fastapi/app/main.py

cat > /etc/systemd/system/dsi-fastapi.service <<'UNIT'
[Unit]
Description=DSI Workshop FastAPI
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=fastapi
Group=fastapi
WorkingDirectory=/opt/dsi-fastapi
EnvironmentFile=-/home/fastapi/.config/dsi/database.env
ExecStart=/opt/dsi-fastapi-venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
UNIT

log "Configuring PostgreSQL for local access only"

sed -ri \
  "s/^#?listen_addresses[[:space:]]*=.*/listen_addresses = '127.0.0.1'/" \
  /etc/postgresql/*/main/postgresql.conf

log "Installing Docker"

install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg |
  gpg --dearmor --yes --output /etc/apt/keyrings/docker.gpg
chmod 0644 /etc/apt/keyrings/docker.gpg

cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${EXPECTED_UBUNTU_CODENAME} stable
EOF

apt-get update
apt-get install -y --no-install-recommends \
  containerd.io \
  docker-buildx-plugin \
  docker-ce \
  docker-ce-cli \
  docker-compose-plugin

usermod -aG docker student

log "Installing ShinyProxy"

readonly SHINYPROXY_VERSION="3.2.4"
readonly SHINYPROXY_SHA256="0bd68e3ba31b5288b5523ee250e90f316f5e0524bd11bcc18645499ede1ee57e"
readonly SHINYPROXY_JAR="/opt/shinyproxy/shinyproxy.jar"

install -d -m 0755 /opt/shinyproxy /etc/shinyproxy
curl \
  --fail \
  --location \
  --retry 5 \
  --retry-all-errors \
  --connect-timeout 15 \
  --output "$SHINYPROXY_JAR" \
  "https://github.com/openanalytics/shinyproxy/releases/download/v${SHINYPROXY_VERSION}/shinyproxy-${SHINYPROXY_VERSION}.jar"

echo "${SHINYPROXY_SHA256}  ${SHINYPROXY_JAR}" | sha256sum --check -

cat > /etc/shinyproxy/application.yml <<'YAML'
proxy:
  title: Workshop ShinyProxy
  specs:
    - id: hello
      display-name: Hello App
      container-image: openanalytics/shinyproxy-demo
server:
  address: 127.0.0.1
  port: 8081
management:
  server:
    address: 127.0.0.1
    port: 9090
YAML

cat > /etc/systemd/system/shinyproxy.service <<'UNIT'
[Unit]
Description=ShinyProxy
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/etc/shinyproxy
ExecStart=/usr/bin/java -jar /opt/shinyproxy/shinyproxy.jar --spring.config.additional-location=file:/etc/shinyproxy/application.yml
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

log "Installing Quarto"

readonly QUARTO_VERSION="1.8.24"
readonly QUARTO_DEB="/tmp/quarto.deb"

wget --quiet \
  --output-document="$QUARTO_DEB" \
  "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb"
apt-get install -y "$QUARTO_DEB"
rm -f "$QUARTO_DEB"
quarto check

log "Installing code-server"

curl --fail --silent --show-error --location \
  https://code-server.dev/install.sh \
  --output /tmp/install-code-server.sh
sh /tmp/install-code-server.sh
rm -f /tmp/install-code-server.sh

cat > /home/student/.config/code-server/config.yaml <<'YAML'
bind-addr: 127.0.0.1:8080
auth: password
cert: false
YAML
chown student:student /home/student/.config/code-server/config.yaml
chmod 0600 /home/student/.config/code-server/config.yaml

# Participant provisioning supplies the password and enables this service.
systemctl disable --now code-server@student.service 2>/dev/null || true

log "Configuring Nginx"

cat > /etc/nginx/sites-available/dsi-workshop <<'NGINX'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location = /healthz {
        access_log off;
        default_type text/plain;
        return 200 'ok\n';
    }

    location / {
        root /var/www/html;
        index index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /shiny/ {
        proxy_pass http://127.0.0.1:3838/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /code/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /proxy/ {
        proxy_pass http://127.0.0.1:8081/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }
}
NGINX

rm -f /etc/nginx/sites-enabled/default
ln -sfn \
  /etc/nginx/sites-available/dsi-workshop \
  /etc/nginx/sites-enabled/dsi-workshop
nginx -t

log "Starting and validating image services"

systemctl daemon-reload
systemctl enable --now \
  certbot.timer \
  docker.service \
  nginx.service \
  postgresql.service \
  shiny-server.service \
  shinyproxy.service

wait_for_http http://127.0.0.1:3838/ shiny-server
wait_for_http http://127.0.0.1:8081/ shinyproxy

check_listening_port 3838 "Shiny Server"
check_listening_port 8081 "ShinyProxy"
check_listening_port 9090 "ShinyProxy management endpoint"

log "Validating FastAPI service and Nginx route"

# Start and validate FastAPI using the same unit participants will enable.
# Leave it stopped and disabled in the finished golden image.
systemctl start dsi-fastapi.service
wait_for_http http://127.0.0.1:8000/healthz dsi-fastapi
check_listening_port 8000 "FastAPI"
curl --fail --silent --show-error --output /dev/null \
  http://127.0.0.1/api/healthz

# Validate the unit identity while it is loaded and known to systemd.
[[ "$(systemctl show dsi-fastapi.service --property=User --value)" == "fastapi" ]]
[[ "$(systemctl show dsi-fastapi.service --property=Group --value)" == "fastapi" ]]

systemctl disable --now dsi-fastapi.service
systemctl reset-failed dsi-fastapi.service || true
fastapi_enablement="$(systemctl is-enabled dsi-fastapi.service 2>/dev/null || true)"
[[ "$fastapi_enablement" == "disabled" ]] ||
  fail "dsi-fastapi.service should be disabled, found: ${fastapi_enablement:-unknown}"
! systemctl is-active --quiet dsi-fastapi.service ||
  fail "dsi-fastapi.service should be stopped in the golden image"

log "Validating workshop accounts and permissions"

[[ "$(getent passwd fastapi | cut -d: -f6)" == "/home/fastapi" ]]
[[ "$(getent passwd fastapi | cut -d: -f7)" == "/usr/sbin/nologin" ]]
[[ "$(stat -c '%U:%G' /home/fastapi/.config/dsi)" == "fastapi:fastapi" ]]
[[ "$(stat -c '%a' /home/fastapi/.config/dsi)" == "700" ]]

log "Cleaning package caches"

apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/*

log "Golden-image build completed"
