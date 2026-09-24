# Pre workshop
## buy domain

## Create VMs
in subnet?
Azure cli

## Cloud Firewall => Azure NSG
### Create NSG
- Open Azure Portal
- Search for Network security groups
- Click Create
- Choose Subscription, Resource Group, Region
- Click Review + Create

| Priority | Port | Protocol | Purpose              |
| -------- | ---- | -------- | -------------------- |
| 100      | 22   | TCP      | SSH                  |
| 110      | 8080 | TCP      | code-server          |
| 120      | 3838 | TCP      | Shiny Server         |
| 130      | 8000 | TCP      | FastAPI              |
| 140      | 8081 | TCP      | ShinyProxy (if used) |
| 150      | 80   | TCP      | HTTP                 |
| 160      | 443  | TCP      | HTTPS                |

**Note: we do not expose PostgreSQL (port 5432) publicly since it's an *internal* database**

### Attach the NSG to a Subnet
Virtual Network
  → Subnets
  → workshop-subnet
  → Associate NSG and select by name, e.g. workshop-nsg

```bash
az version

# Sign in
az login

az account list --output table

az account set --subscription "YOUR-SUBSCRIPTION-NAME-OR-ID"

# define variables
SUBSCRIPTION_ID=$(az account show --query id --output tsv)

LOCATION="uksouth"

IMAGE_RG="rg-workshop-image"
NETWORK_RG="rg-workshop-network"
VM_RG="rg-workshop-vms"

GALLERY_NAME="workshopGallery"
IMAGE_DEFINITION="workshopUbuntu"
IMAGE_VERSION="1.0.0"

BUILD_VM="workshop-image-builder"
ADMIN_USER="workshopadmin"

VNET_NAME="vnet-workshop"
SUBNET_NAME="snet-participants"
NSG_NAME="nsg-workshop"

# Create the resource groups
az group create \
  --name "$IMAGE_RG" \
  --location "$LOCATION"

az group create \
  --name "$NETWORK_RG" \
  --location "$LOCATION"

az group create \
  --name "$VM_RG" \

# Create the virtual network and subnet
az network vnet create \
  --resource-group "$NETWORK_RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.20.0.0/16" \
  --subnet-name "$SUBNET_NAME" \
  --subnet-prefixes "10.20.1.0/24"

# Create the Network Security Group
az network nsg create \
  --resource-group "$NETWORK_RG" \
  --name "$NSG_NAME" \
  --location "$LOCATION"

# allow http
az network nsg rule create \
  --resource-group "$NETWORK_RG" \
  --nsg-name "$NSG_NAME" \
  --name "Allow-HTTP" \
  --priority 100 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes Internet \
  --source-port-ranges "*" \
  --destination-address-prefixes "*" \
  --destination-port-ranges 80

# allow https
az network nsg rule create \
  --resource-group "$NETWORK_RG" \
  --nsg-name "$NSG_NAME" \
  --name "Allow-HTTPS" \
  --priority 110 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes Internet \
  --source-port-ranges "*" \
  --destination-address-prefixes "*" \
  --destination-port-ranges 443

# ssh # TODO: relax this!
ADMIN_IP="203.0.113.10/32"

az network nsg rule create \
  --resource-group "$NETWORK_RG" \
  --nsg-name "$NSG_NAME" \
  --name "Allow-SSH-Admin" \
  --priority 120 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes "$ADMIN_IP" \
  --source-port-ranges "*" \
  --destination-address-prefixes "*" \
  --destination-port-ranges 22

# attach NSG to subnet
az network vnet subnet update \
  --resource-group "$NETWORK_RG" \
  --vnet-name "$VNET_NAME" \
  --name "$SUBNET_NAME" \
  --network-security-group "$NSG_NAME"
```

## Golden image
Azure Compute Gallery
└── workshop-linux
    ├── 1.0.0
    ├── 1.0.1
    └── 1.1.0

Workshop VNet
└── workshop-subnet
    ├── workshop-01
    ├── workshop-02
    ├── ...
    └── workshop-30

Use a B2s or larger for constructing the image

```bash
# Create the image-builder VM
az vm create \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM" \
  --location "$LOCATION" \
  --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
  --size "Standard_B2s" \
  --admin-username "$ADMIN_USER" \
  --generate-ssh-keys \
  --public-ip-sku Standard \
  --os-disk-size-gb 64

# get the public IP
BUILD_IP=$(az vm show \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM" \
  --show-details \
  --query publicIps \
  --output tsv)

echo "$BUILD_IP"

# connect to the vm
ssh "${ADMIN_USER}@${BUILD_IP}" # ADMIN_USER defined earlier when creating NSG

# Install workshop software
# use a script from the gh repo
BOOTSTRAP_URL="https://github.com/earl-workshop26/setup/bootstrap.sh"

az vm run-command invoke \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM" \
  --command-id RunShellScript \
  --scripts "
    set -e
    curl -fsSL '$BOOTSTRAP_URL' -o /tmp/bootstrap.sh
    chmod 700 /tmp/bootstrap.sh
    sudo /tmp/bootstrap.sh
  "

BOOTSTRAP_SHA256="REPLACE_WITH_REAL_SHA256" # TODO: how to find this?!

az vm run-command invoke \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM" \
  --command-id RunShellScript \
  --scripts "
    set -e
    curl -fsSL '$BOOTSTRAP_URL' -o /tmp/bootstrap.sh
    echo '$BOOTSTRAP_SHA256  /tmp/bootstrap.sh' | sha256sum --check
    chmod 700 /tmp/bootstrap.sh
    sudo /tmp/bootstrap.sh
  "
```

### Configure services for the image
<!-- TODO: how? -->
Use separate internal ports:
code-server    127.0.0.1:8080
ShinyProxy     127.0.0.1:8081
FastAPI        127.0.0.1:8000
Shiny Server   127.0.0.1:3838
Nginx          0.0.0.0:80 and :443
PostgreSQL     127.0.0.1:5432

Important code-server point

Do not store the code-server password inside the image. Put only a template in the image, for example:
bind-addr: 127.0.0.1:8080
auth: password
cert: false

Generate the actual password when each participant VM is created.

Likewise, avoid creating the workshop PostgreSQL password in the image. Create or rotate it during each VM's first boot.

### Test the builder thoroughly

```bash
docker --version
docker compose version
R --version
python3 --version
quarto --version
java --version
psql --version
nginx -v
code-server --version

sudo systemctl status docker --no-pager
sudo systemctl status postgresql --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status shiny-server --no-pager

sudo ss -lntp # listening ports?

sudo nginx -t

# test local backends
curl --head http://127.0.0.1:3838/
curl --head http://127.0.0.1:8080/
curl --head http://127.0.0.1:8081/
curl --head http://127.0.0.1:8000/docs

```
### clean the image
```bash
sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/*
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s

# remove shell history, temp repos, creds
history -c
rm -f ~/.bash_history
rm -rf ~/.azure
rm -rf ~/.docker
rm -rf ~/.config/gh
```
### deprovision the VM
<!--! Machine won't restart afterwards!  -->
```bash
# still on the VM
sudo waagent -deprovision+user -force
exit
```

### deallocate and generalise
<!-- i.e. back in local terminal -->

```bash
az vm deallocate \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM"

az vm generalize \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM"

az vm get-instance-view \
  --resource-group "$IMAGE_RG" \
  --name "$BUILD_VM" \
  --query "instanceView.statuses[].displayStatus" \
  --output table
```

### Create an Azure Compute Gallery
An image definition describes the image family; an image version is the deployable artefact. One definition can therefore contain versions such as 1.0.0, 1.0.1 and 2.0.0.

```bash
az sig create \
  --resource-group "$IMAGE_RG" \
  --gallery-name "$GALLERY_NAME" \
  --location "$LOCATION" \
  --description "Workshop VM images"

az sig image-definition create \
  --resource-group "$IMAGE_RG" \
  --gallery-name "$GALLERY_NAME" \
  --gallery-image-definition "$IMAGE_DEFINITION" \
  --publisher "StephenPriceWorkshops" \
  --offer "OpenSourceWorkshop" \
  --sku "Ubuntu2204" \
  --os-type Linux \
  --os-state Generalized \
  --hyper-v-generation V2 \
  --features SecurityType=Standard

```

### Create the golden image version
```bash
az sig image-version create \
  --resource-group "$IMAGE_RG" \
  --gallery-name "$GALLERY_NAME" \
  --gallery-image-definition "$IMAGE_DEFINITION" \
  --gallery-image-version "$IMAGE_VERSION" \
  --virtual-machine "$BUILD_VM" \
  --target-regions "$LOCATION=1=Standard_LRS"

az sig image-version show \
  --resource-group "$IMAGE_RG" \
  --gallery-name "$GALLERY_NAME" \
  --gallery-image-definition "$IMAGE_DEFINITION" \
  --gallery-image-version "$IMAGE_VERSION" \
  --output table

IMAGE_VERSION_ID=$(az sig image-version show \
  --resource-group "$IMAGE_RG" \
  --gallery-name "$GALLERY_NAME" \
  --gallery-image-definition "$IMAGE_DEFINITION" \
  --gallery-image-version "$IMAGE_VERSION" \
  --query id \
  --output tsv)

echo "$IMAGE_VERSION_ID"
```

### Test the image
```bash
az vm create \
  --resource-group "$VM_RG" \
  --name "workshop-test" \
  --location "$LOCATION" \
  --image "$IMAGE_VERSION_ID" \
  --size "Standard_B1s" \
  --admin-username "student" \
  --generate-ssh-keys \
  --vnet-name "$VNET_NAME" \
  --subnet "$SUBNET_NAME" \
  --public-ip-sku Standard \
  --nsg ""

az vm get-instance-view \
  --resource-group "$VM_RG" \
  --name "workshop-test" \
  --query "instanceView.statuses[].displayStatus" \
  --output table

az vm show \
  --resource-group "$VM_RG" \
  --name "workshop-test" \
  --show-details \
  --query publicIps \
  --output tsv
```

## Create participant VMS
cloud-init.yml:
```yaml
#cloud-config

package_update: false
package_upgrade: false

write_files:
  - path: /etc/workshop/participant-id
    owner: root:root
    permissions: "0644"
    content: |
      PARTICIPANT_ID

runcmd:
  - mkdir -p /etc/workshop
  - systemctl enable docker
  - systemctl enable nginx
  - systemctl enable postgresql
  - systemctl enable shiny-server
  - systemctl restart docker
  - systemctl restart postgresql
  - systemctl restart shiny-server
  - nginx -t
  - systemctl restart nginx

final_message: "Workshop VM configuration completed"
```

```bash
mkdir -p participant-config

for i in $(seq -w 1 30); do
  VM_NAME="workshop-${i}" # TODO: set this
  CODE_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)
  DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
  # TODO: see the previous cloud-config
  cat > "participant-config/cloud-init-${i}.yml" <<EOF
#cloud-config

write_files:
  - path: /etc/workshop/participant-id
    owner: root:root
    permissions: "0644"
    content: |
      ${i}

  - path: /home/student/.config/code-server/config.yaml
    owner: student:student
    permissions: "0600"
    content: |
      bind-addr: 127.0.0.1:8080
      auth: password
      password: ${CODE_PASSWORD}
      cert: false

runcmd:
  - chown -R student:student /home/student/.config
  - systemctl enable --now code-server@student
  - systemctl restart nginx

final_message: "Workshop VM ${i} is ready"
EOF

  az vm create \
    --resource-group "$VM_RG" \
    --name "$VM_NAME" \
    --location "$LOCATION" \
    --image "$IMAGE_VERSION_ID" \
    --size "Standard_B1s" \
    --admin-username "student" \
    --generate-ssh-keys \
    --vnet-name "$VNET_NAME" \
    --subnet "$SUBNET_NAME" \
    --public-ip-sku Standard \
    --nsg "" \
    --custom-data "participant-config/cloud-init-${i}.yml"

  PUBLIC_IP=$(az vm show \
    --resource-group "$VM_RG" \
    --name "$VM_NAME" \
    --show-details \
    --query publicIps \
    --output tsv)

  printf "%s,%s,%s\n" \
    "$VM_NAME" \
    "$PUBLIC_IP" \
    "$CODE_PASSWORD" \
    >> participant-config/access-details.csv
done

chmod 600 participant-config/access-details.csv

# validate
az vm list \
  --resource-group "$VM_RG" \
  --show-details \
  --query "[].{Name:name,Power:powerState,Provisioning:provisioningState,IP:publicIps}" \
  --output table

# test port 80
while IFS=, read -r vm ip password; do
  if curl --silent --fail --max-time 5 "http://${ip}/" >/dev/null; then
    echo "OK: ${vm} ${ip}"
  else
    echo "FAILED: ${vm} ${ip}"
  fi
done < participant-config/access-details.csv

```

Important limitation in that example

The database password is generated but not yet applied. PostgreSQL password handling is best done through:

- Azure Key Vault, or
- a root-only first-boot script that uses the generated value.

Do not pass secrets directly on an Azure CLI command line if your shell history or CI logs can expose them.

## Updates to the golden image
Create a fresh builder VM from the existing version:

```bash
az vm create \
  --resource-group "$IMAGE_RG" \
  --name "workshop-image-builder-v101" \
  --location "$LOCATION" \
  --image "$IMAGE_VERSION_ID" \
  --size "Standard_B2s" \
  --admin-username "$ADMIN_USER" \
  --generate-ssh-keys \
  --public-ip-sku Standard
```

Then make the changes and follow the initiation process but upversion using semantic versioning.

# Workshop
## Part 1: Infrastructure (30 min)
Teaching materials: Configure firewall - assuming you will talk to IT or - as we have done for your VMs - configure a firewall appropriately for your cloud platform

- general intro
- SSH into VM
- nix primer
- introduce the software

## Part 2: Shiny (20 min)

- Create a simple app
- Deploy
  - manually to /srv/shiny-server
  - via git and github
- Browse to `http://<ip>:3838/myapp`

## Part 3: FastAPI (20 min)

Build API
Query PostgreSQL
Test in Swagger UI (/docs)

## Part 4: Docker + ShinyProxy (30 min)

Create a container
Explain containerised deployment
Access app through ShinyProxy

## Part 5: Quarto (20 min)

Create a Quarto report
Publish analysis from PostgreSQL data
Render to HTML


# setup script
```
#!/bin/bash

set -e

echo "=============================="
echo "Updating Ubuntu"
echo "=============================="

sudo apt update
sudo apt upgrade -y

echo "=============================="
echo "Installing base packages"
echo "=============================="

sudo apt install -y \
    curl \
    wget \
    git \
    unzip \
    gnupg \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    build-essential

echo "=============================="
echo "Installing R"
echo "=============================="

sudo apt install -y r-base r-base-dev

sudo R -e "install.packages(c('shiny','RPostgres','DBI','httr','jsonlite'), repos='https://cloud.r-project.org')"

echo "=============================="
echo "Installing Shiny Server"
echo "=============================="

wget -O shiny-server.deb \
https://download3.rstudio.org/ubuntu-20.04/x86_64/shiny-server-1.5.20.1002-amd64.deb

sudo apt install -y ./shiny-server.deb

sudo systemctl enable shiny-server
sudo systemctl start shiny-server

echo "=============================="
echo "Installing Python + FastAPI"
echo "=============================="

sudo apt install -y python3 python3-pip python3-venv

pip3 install \
    fastapi \
    uvicorn \
    sqlalchemy \
    psycopg2-binary \
    pandas

echo "=============================="
echo "Installing PostgreSQL"
echo "=============================="

sudo apt install -y \
    postgresql \
    postgresql-contrib

sudo systemctl enable postgresql
sudo systemctl start postgresql

echo "=============================="
echo "Creating workshop database"
echo "=============================="

sudo -u postgres psql <<EOF

CREATE USER workshop_user
WITH PASSWORD 'workshop123';

CREATE DATABASE workshop_db
OWNER workshop_user;

GRANT ALL PRIVILEGES
ON DATABASE workshop_db
TO workshop_user;

EOF

echo "=============================="
echo "Installing Docker"
echo "=============================="

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
sudo gpg --dearmor -o /usr/share/keyrings/docker.gpg

echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu \
$(lsb_release -cs) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update

sudo apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker

sudo usermod -aG docker $USER

echo "=============================="
echo "Installing Java"
echo "=============================="

sudo apt install -y openjdk-17-jdk

echo "=============================="
echo "Installing ShinyProxy"
echo "=============================="

sudo mkdir -p /opt/shinyproxy

wget -O shinyproxy.jar \
https://repo1.maven.org/maven2/eu/openanalytics/shinyproxy/3.1.1/shinyproxy-3.1.1.jar

sudo mv shinyproxy.jar /opt/shinyproxy/

sudo tee /etc/systemd/system/shinyproxy.service > /dev/null <<EOF
[Unit]
Description=ShinyProxy
After=docker.service

[Service]
User=root
ExecStart=/usr/bin/java -jar /opt/shinyproxy/shinyproxy.jar
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "=============================="
echo "Creating ShinyProxy config"
echo "=============================="

sudo mkdir -p /etc/shinyproxy

sudo tee /etc/shinyproxy/application.yml > /dev/null <<EOF
proxy:
  title: Workshop ShinyProxy

  specs:
    - id: hello
      display-name: Hello App
      container-image: openanalytics/shinyproxy-demo

server:
  port: 8080

spring:
  security:
    user:
      name: admin
      password: admin
EOF

sudo systemctl daemon-reload
sudo systemctl enable shinyproxy

echo "=============================="
echo "Installing Quarto"
echo "=============================="

QUARTO_VERSION="1.8.24"

wget \
https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb

sudo apt install -y ./quarto-${QUARTO_VERSION}-linux-amd64.deb

echo "=============================="
echo "Installing Nginx"
echo "=============================="

sudo apt install -y nginx

sudo systemctl enable nginx
sudo systemctl start nginx

echo "=============================="
echo "Workshop environment ready"
echo "=============================="

echo ""
echo "Shiny Server:"
echo "http://<VM-IP>:3838"
echo ""
echo "FastAPI:"
echo "http://<VM-IP>:8000/docs"
echo ""
echo "ShinyProxy:"
echo "http://<VM-IP>:8080"
echo ""
echo "PostgreSQL:"
echo "Database: workshop_db"
echo "User: workshop_user"
echo "Password: workshop123"
echo ""
echo "Logout/Login to use Docker"
```

```
#!/bin/bash

# manage PostgreSQL resource
sudo nano /etc/postgresql/*/main/postgresql.conf
# shared_buffers = 128MB

# test postgres
sudo -i -u postgres
psql
# postgresql://workshop_user:password123@localhost:5432/workshop_db
# library(DBI)
# con <- dbConnect(
#   RPostgres::Postgres(),
#   dbname = "workshop_db",
#   host = "localhost",
#   user = "workshop_user",
#   password = "password123"
# )
```

# find your public ip
`curl ifconfig.me`
