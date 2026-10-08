# Infastructure as code

Cloud infrastructure provisioning on DigitalOcean. Workshop participants receive individual virtual machines with workshop software installed via a golden image snapshot.

- participant `student` accounts receive unique SSH keys and passwords;
- `student` has passwordless `sudo`;
- each participant receives a unique Nginx `server_name`;
- participant DNS records are created after Droplet IPs exist;
- Certbot automatically enables HTTPS after DNS resolves;
- code-server and PostgreSQL credentials are unique per participant;
- only SSH, HTTP, and HTTPS are exposed publicly;

> **Architecture:** Nginx is the only public application entry point. Workshop software (code-server, Shiny Server, FastAPI, ShinyProxy, and PostgreSQL) listen locally and are reached through Nginx where appropriate.

## Configuration
Environment variables are essential for configuration and examples with values to replace are provided in `config/`.

- copy `workshop.env.example` to `workshop.env` and replace placeholders with your working values

```bash
cd infrastructure/
chmod 600 config/workshop.env

CONFIG_FILE="${1:-./config/workshop.env}"

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
```

## SSH keys
SSH keys provide a secure way to authenticate to remote systems without using a password. An SSH key pair consists of:

- **Private key**: Stored securely on your local machine and never shared.
- **Public key**: Shared with the remote server or service you want to access.

When you connect via SSH, the server verifies that you possess the corresponding private key through a cryptographic challenge-response process. This proves your identity without transmitting your private key over the network.

### Generate an SSH Key Pair

Generate a new Ed25519 key pair (recommended):

```bash
ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/id_ed25519"
```

Press **Enter** to accept the default file location and optionally set a passphrase for additional security.

This creates the following files:

```text
~/.ssh/id_ed25519       # Private key
~/.ssh/id_ed25519.pub   # Public key
```

To display your public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the contents of the `.pub` file and add it to the remote server or service you wish to access. Keep your private key secure and never share it.

```bash
printf '%s\n' "$SSH_PUBLIC_KEY" > "/home/student/.ssh/authorized_keys"
```

## Domain preparation
- Create a workshop sub-domain in DigitalOcean (Core Cloud → Networking → Domains → Add a domain), e.g. `earl.sjp-analytics.co.uk`.
- Delegate sub-domain in Cloudflare or other DNS provider. Create NS records using DigitalOcean nameservers (→ DNS Records).

> For anything earl.sjp-analytics.co.uk, ask DigitalOcean.

Example participant hostnames:

```text
dsi-01.earl.sjp-analytics.co.uk
dsi-02.earl.sjp-analytics.co.uk
...
```

DNS works like an address book. Each participant hostname receives an `A` record pointing to that participant Droplet's public IPv4 address:

```text
dsi-01.earl.sjp-analytics.co.uk -> participant 01 public IPv4
dsi-02.earl.sjp-analytics.co.uk -> participant 02 public IPv4
...
```

Create these records only after the Droplets exist because DigitalOcean assigns their public addresses during creation.

The provisioning script currently assumes DigitalOcean DNS. Set `CREATE_DIGITALOCEAN_DNS=false` if DNS is managed elsewhere, then create equivalent `A` records with that provider.

## Create cloud infrastructure: `init-cloud-infra.sh`

`init-cloud-infra.sh` contains DigitalOcean commands for initiation of cloud infrastructure:

- Authenticate doctl and Verify access
- Define infrastructure variables
- Check current availability before committing to values
- Create the administrator SSH key
- Create a Project: A Project groups the workshop resources for organisation and billing visibility.
- Create the VPC: The VPC is the private regional network for the Droplets.
- Create the Cloud Firewall

### Check availability before committing to values

```bash
doctl compute region list
doctl compute size list
doctl compute image list-distribution --public
```

Region-droplet combination options for builder:

| Slug              | Description | Memory (MB) | vCPUs | Disk (GB) | Price Monthly | Price Hourly | Region |
| ----------------- | ----------- | ----------: | ----: | --------: | ------------: | -----------: | ------ |
| s-1vcpu-2gb-intel | Basic Intel |        2048 |     1 |        50 |         14.00 |     0.020830 | lon1   |
| s5-1vcpu-3gb-50gb | v5 Shared   |        3072 |     1 |        50 |         25.89 |     0.034800 | atl1   |

### Create administrator SSH key

This is the organiser's *fallback* key. Each participant **also** receives a separate key later.

```bash
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
```

### Create the Cloud Firewall

Public ports:

| Port | Protocol | Source                        | Purpose                           |
| ---- | -------- | ----------------------------- | --------------------------------- |
| 22   | TCP      | Builder: Trainer/admin CIDR   | SSH                               |
|      |          | Trainer/admin and venue CIDRs | SSH                               |
| 80   | TCP      | Any IPv4/IPv6                 | HTTP and Let's Encrypt validation |
| 443  | TCP      | Any IPv4/IPv6                 | HTTPS                             |

The following remain private:

| Port | Binding     | Service      |
| ---- | ----------- | ------------ |
| 8080 | `127.0.0.1` | code-server  |
| 8081 | `127.0.0.1` | ShinyProxy   |
| 8000 | `127.0.0.1` | FastAPI      |
| 3838 | `127.0.0.1` | Shiny Server |
| 5432 | `127.0.0.1` | PostgreSQL   |

DigitalOcean Cloud Firewalls attach to Droplets or tags. Builder and participant firewalls are attached through their respective tags. Builder Droplets receive the builder firewall, while participant Droplets receive the participant firewall.

## Golden image: `./image/create-image.sh`

DigitalOcean uses Droplet snapshots for golden images. Commands are captured separately in `./image/create-image.sh`. *This script is not currently executable and switches between commands run interactively on your local machine and on the builder VM and back again*.

```text
Builder Droplet
      |
      v
Versioned snapshot
      |
      +-- dsi-01
      +-- dsi-02
      +-- ...
      +-- dsi-10
```

- load/generate and check for necessary env vars
- Create the builder VM
- ssh onto VM and install software from a bootstrap scipt: `./image/create-image.sh` sourced from a github repo
- test installation
- clean up the VM
- create the snapshot from local machine
- delete the droplet

### Create the builder Droplet

```bash
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
```

### Service layout

```text
code-server    127.0.0.1:8080
ShinyProxy     127.0.0.1:8081
FastAPI        127.0.0.1:8000
Shiny Server   127.0.0.1:3838
PostgreSQL     127.0.0.1:5432
Nginx          0.0.0.0:80 and :443
```

Nginx accepts public requests and sends them to the appropriate local service:

```text
/         landing page
/code/    code-server
/shiny/   Shiny Server
/api/     FastAPI
/proxy/   ShinyProxy
```

The golden snapshot keeps `server_name _;`. Participant cloud-init replaces the entire Nginx site with a participant-specific configuration, such as `server_name dsi-01.earl.sjp-analytics.co.uk;`.

## Cloud-Init Template Overview

The cloud-init template provisions and configures a complete workshop environment for an individual participant. It creates a dedicated user account, configures remote access, deploys development tools and web services, provisions a PostgreSQL database, and validates that all required services are operational before marking the system as ready.

### User Configuration

- Creates a `student` user with:
  - `sudo` privileges (passwordless)
  - Membership of the `docker` group
  - A configurable password
  - A configurable SSH public key for key-based authentication
- Uses placeholder values that are replaced during deployment.

### Development Environment

- Configures **code-server** (browser-based VS Code) for the participant (an alternative to ssh for participants on heavily locked down corporate machines that block port 22)
- Creates participant-specific configuration files and secrets.
- Stores a participant identifier on the host for tracking and administration.

### SSH Configuration

- Configures SSH to allow:
  - Public key authentication
  - Password authentication
  - Keyboard-interactive authentication
- Prevents direct root login using passwords while still allowing administrative access through the `student` account.

### Web Services and Reverse Proxy

- Configures **NGINX** as the primary web entry point.
- Proxies requests to:
  - FastAPI (`/api/`)
  - Shiny applications (`/shiny/`)
  - code-server (`/code/`)
  - ShinyProxy (`/proxy/`)
- Exposes a `/healthz` endpoint for health checks and service monitoring.

### Database Provisioning

- Creates a PostgreSQL role named `workshop_user`.
- Creates a database named `workshop_db`.
- Sets a deployment-specific database password.
- Generates database connection configuration files for:
  - `student`
  - `shiny`
  - `fastapi`
- Applies appropriate ownership and file permissions for each service account.

### Service Enablement

The template enables and starts the following services:

- Docker
- PostgreSQL
- NGINX
- Shiny Server
- ShinyProxy
- code-server (running under the `student` account)

Optional FastAPI service startup is also included.

### Validation and Health Checks

Before completing provisioning, the script:

- Validates SSH configuration.
- Tests NGINX configuration.
- Confirms all required services are running.
- Verifies database connectivity.
- Checks the health endpoint.
- Waits for code-server and ShinyProxy to become available over HTTP.
- Creates a marker file indicating successful provisioning.

### Completion

Once all configuration and validation steps succeed:

- The provisioning script removes itself.
- A completion marker file is created.
- Cloud-init reports successful configuration for the participant instance.

## Provisioning participant VMs
yaml check requires PyYAML so install in virtual env in directory where provisioning script lives.

```bash
cd infrastructure/
python3 -m venv .venv
.venv/bin/python -m pip install PyYAML
```

For each participant, the provisioning script (`./participants/provision-participants.sh`):

1. Resolves the DigitalOcean SSH key, VPC and snapshot.
2. Creates a unique SSH key pair and credentials.
3. Substitutes those values into the cloud-init template.
4. Creates a droplet from the golden snapshot.
5. Assigns it to the project.
6. Creates a DNS record.
7. Waits for SSH and cloud-init.
8. Waits for DNS.
9. Issues a TLS certificate.
10. Tests the endpoints.
11. Records access details.

Cloud-init then:

1. Configures the existing student account.
2. Installs its participant SSH key.
3. Writes code-server and Nginx configuration.
4. Creates the PostgreSQL role and database.
5. Starts the required services.
6. Runs local health checks.

## Certbot testing strategy
Create and fully test one disposable participant clone before provisioning the full class.

Do not develop the automation using production certificates. First test with one participant and Let's Encrypt staging:

```bash
PARTICIPANT_COUNT=1
CERTBOT_STAGING=true
```

A staging certificate intentionally produces a browser trust warning. Once the complete workflow succeeds, delete the disposable test Droplet and DNS record, then provision the real class with appropriate `PARTICIPANT_COUNT` and with `CERTBOT_STAGING=false`.

Certbot requires:

- the participant hostname to resolve publicly to the correct Droplet;
- port 80 to be publicly reachable for the HTTP challenge;
- Nginx to contain the matching `server_name`;
- port 443 to be open for normal HTTPS access.

Certbot's timer handles renewals. Check it on a participant Droplet:

```bash
sudo systemctl status certbot.timer --no-pager
sudo certbot renew --dry-run
```

## Validate each participant

```bash
ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  student@dsi-01.earl.sjp-analytics.co.uk

# expect: Permission denied (publickey).

ssh -i participant-config/dsi-01-ssh \
  student@dsi-01.earl.sjp-analytics.co.uk \
  "sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin) '"

# expect:
# permitrootlogin without-password
# pubkeyauthentication yes
# passwordauthentication no
# kbdinteractiveauthentication no

ssh -i participant-config/dsi-01-ssh \
  student@dsi-01.earl.sjp-analytics.co.uk

whoami
sudo -n whoami
groups
sudo nginx -t
curl http://localhost/healthz
```

Expected identity results:

```text
student
root
```

Check externally:

```bash
curl -I http://dsi-01.earl.sjp-analytics.co.uk/healthz
curl -I https://dsi-01.earl.sjp-analytics.co.uk/healthz
```

Check that private services are not exposed:

```bash
for port in 3838 5432 8000 8080 8081; do
  nc -z -w 2 dsi-01.earl.sjp-analytics.co.uk "$port" \
    && echo "UNEXPECTEDLY OPEN: $port" \
    || echo "closed as expected: $port"
done
```

### Test quarto
```bash
sudo -u student which quarto
sudo -u student quarto check
sudo -u student bash <<'EOF'
mkdir -p /tmp/quarto-test
cd /tmp/quarto-test

quarto create-project test
cd test

quarto render
EOF

sudo -H -u shiny bash -c '
  cd "$HOME"
  quarto check
'
sudo mkdir -p /srv/shiny-server/test
sudo cp /tmp/quarto-test/test/test.qmd /srv/shiny-server/test/
sudo chown -R shiny:shiny /srv/shiny-server/test
sudo chmod 0755 /srv/shiny-server/test
sudo chmod 0644 /srv/shiny-server/test/test.qmd
sudo -H -u shiny bash -c '
  cd "$HOME"
  quarto render /srv/shiny-server/test/test.qmd
'
sudo -H -u student bash -c '
  cd "$HOME"
  quarto render /tmp/quarto-test/test/test.qmd
'
```

## Updating the golden image

1. Create a new builder from the current snapshot.
2. Apply changes.
3. Run all software, service, and network tests.
4. Remove credentials and instance-specific state.
5. Clean cloud-init, machine ID, and SSH host keys.
6. Power off the builder.
7. Create a new semantic snapshot version, such as `dsi-ubuntu-1.0.1`.
8. Create a disposable participant clone.
9. Test cloud-init, SSH, sudo, DNS, Nginx, and staged Certbot.
10. Retain the previous known-good snapshot until after the workshop.

## Teardown: `destroy.sh`

Delete participant Droplets promptly after the workshop.

## Azure-to-DigitalOcean mapping

| Azure                         | DigitalOcean replacement                                 |
| ----------------------------- | -------------------------------------------------------- |
| Subscription                  | Account or team                                          |
| Resource groups               | Project plus tags                                        |
| VNet and subnet               | Regional VPC                                             |
| NSG                           | Cloud Firewall attached by tag                           |
| VM                            | Droplet                                                  |
| `az`                          | `doctl`                                                  |
| Compute Gallery image version | Named Droplet snapshot                                   |
| VM custom data                | User data and cloud-init                                 |
| `az vm run-command`           | SSH, cloud-init, or configuration management             |
| `waagent -deprovision`        | Clean cloud-init, machine ID, host keys, and credentials |
| Public IP resource            | Droplet public IPv4/IPv6                                 |
