#!/usr/bin/env bash

# Golden-image build script
# prepares a reusable Ubuntu image containing the software required by workshop VMs.
# Participant-specific settings (SSH keys, passwords, hostnames, databases, service startup and TLS)
# are handled later by cloud-init and a provisioning script

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

log() { printf '\n===== %s =====\n' "$*"; }

log "Updating Ubuntu"
apt-get update
apt-get upgrade -y

ARCH=$(dpkg --print-architecture)

if [[ "$ARCH" != "amd64" ]]; then
  printf 'Unsupported architecture: %s; expected amd64\n' "$ARCH" >&2
  exit 1
fi

# Install base software
log "Installing packages"
apt-get install -y \
  ca-certificates curl wget git unzip gnupg \
  software-properties-common apt-transport-https \
  build-essential pkg-config lsb-release jq openssl nginx \
  libcurl4-openssl-dev libssl-dev libpq-dev \
  libxml2-dev libuv1-dev \
  python3 python3-pip python3-venv \
  postgresql postgresql-contrib \
  openjdk-17-jdk r-base r-base-dev \
  certbot python3-certbot-nginx

# Create persistent participant account
log "Creating the persistent workshop account"
if ! id student >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash student
fi

install -d -o student -g student -m 0700 /home/student/.config
install -d -o student -g student -m 0700 /home/student/.config/code-server
install -d -o student -g student -m 0700 /home/student/.config/dsi
install -d -m 0755 /etc/dsi

# Install R packages
log "Installing R packages"
Rscript --vanilla -e \
  "install.packages(
    c('shiny', 'RPostgres', 'DBI', 'httr', 'jsonlite'),
    repos='https://cloud.r-project.org',
    Ncpus=1
  )"

# Install Shiny Server
log "Installing Shiny Server"
SHINY_SERVER_VERSION="1.5.23.1030"
wget -q \
  "https://download3.rstudio.org/ubuntu-22.04/x86_64/shiny-server-${SHINY_SERVER_VERSION}-amd64.deb" \
  -O /tmp/shiny-server.deb
apt-get install -y /tmp/shiny-server.deb
systemctl enable shiny-server

# Prepare FastAPI
log "Installing FastAPI in a virtual environment"
python3 -m venv /opt/dsi-fastapi-venv
/opt/dsi-fastapi-venv/bin/pip install --upgrade pip
/opt/dsi-fastapi-venv/bin/pip install \
  fastapi uvicorn sqlalchemy psycopg2-binary pandas

# systemd service runs main.py as student listening on 127.0.0.1
# loads PostgreSQL credentials created later by cloud-init (leading `-` tells systemd 
# not to fail merely because the file is initially absent)
# golden-image script does not create /home/student/fastapi or main.py. Participants 
# create the application during the workshop. Until then, the service cannot start successfully.
cat > /etc/systemd/system/dsi-fastapi.service <<'UNIT'
[Unit]
Description=DSI Workshop FastAPI
After=network.target postgresql.service

[Service]
User=student
Group=student
WorkingDirectory=/home/student/fastapi
EnvironmentFile=-/home/student/.config/dsi/database.env
ExecStart=/opt/dsi-fastapi-venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

# Restrict PostgreSQL: prevents PostgreSQL from accepting direct external network connections.
# Cloud-init later creates: workshop_user, workshop_db, participant-specific password, database.env
log "Configuring PostgreSQL for local access only"
sed -ri "s/^#?listen_addresses\s*=.*/listen_addresses = '127.0.0.1'/" \
  /etc/postgresql/*/main/postgresql.conf
systemctl enable postgresql

# Installing Docker
# - Adds Docker’s package-signing key.
# - Determines the system architecture and Ubuntu codename.
# - Adds Docker’s official repository.
# - Installs Docker Engine, Buildx and Compose.
# - Enables Docker at boot.
# - Adds student to the docker group (run without sudo)
log "Installing Docker"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
ARCH=$(dpkg --print-architecture)
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
systemctl enable docker
usermod -aG docker student

# Install ShinyProxy (runs as root rather than via dedicated shiny proxy service account)
log "Installing ShinyProxy"
SHINYPROXY_VERSION="3.2.4"
install -d -m 0755 /opt/shinyproxy /etc/shinyproxy
wget -q \
  "https://repo1.maven.org/maven2/eu/openanalytics/shinyproxy/${SHINYPROXY_VERSION}/shinyproxy-${SHINYPROXY_VERSION}.jar" \
  -O /opt/shinyproxy/shinyproxy.jar

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
YAML

cat > /etc/systemd/system/shinyproxy.service <<'UNIT'
[Unit]
Description=ShinyProxy
After=docker.service
Requires=docker.service

[Service]
User=root
WorkingDirectory=/etc/shinyproxy
ExecStart=/usr/bin/java -jar /opt/shinyproxy/shinyproxy.jar --spring.config.additional-location=file:/etc/shinyproxy/application.yml
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

# Install Quarto
log "Installing Quarto"
QUARTO_VERSION="1.8.24"
wget -q \
  "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb" \
  -O /tmp/quarto.deb
apt-get install -y /tmp/quarto.deb

# Install code-server (provides VS Code in a browser)
# the service intentionally disabled in the golden image
# Cloud-init later:
# - Writes the participant-specific password.
# - Starts the service.
# - Enables it for future boots.
log "Installing code-server"
curl -fsSL https://code-server.dev/install.sh -o /tmp/install-code-server.sh
sh /tmp/install-code-server.sh
systemctl disable code-server@student 2>/dev/null || true

cat > /home/student/.config/code-server/config.yaml <<'YAML'
bind-addr: 127.0.0.1:8080
auth: password
cert: false
YAML
chown student:student /home/student/.config/code-server/config.yaml
chmod 0600 /home/student/.config/code-server/config.yaml

# Configuring Nginx (VM's public gateway)
# enables WebSocket proxying (important for interactive services e.g. code-server, Shiny)
# image installs Certbot and enables its renewal timer, but does not issue a certificate, 
# this is left for the provisioning script once the hostname is known
log "Configuring default Nginx site"
cat > /etc/nginx/sites-available/dsi-workshop <<'NGINX'
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
   }

    location /code/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /proxy/ {
        proxy_pass http://127.0.0.1:8081/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
    }
}
NGINX

rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/dsi-workshop \
  /etc/nginx/sites-enabled/dsi-workshop
nginx -t

# Enable services
systemctl daemon-reload
systemctl enable nginx shinyproxy dsi-fastapi certbot.timer
systemctl restart postgresql nginx

log "Golden-image build completed"
