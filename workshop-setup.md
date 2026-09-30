# DSI workshop prep

Participant VM provisioning with DigitalOcean.

- participant `student` accounts receive unique SSH keys;
- `student` has passwordless `sudo`;
- each participant receives a unique Nginx `server_name`;
- participant DNS records are created after Droplet IPs exist;
- Certbot automatically enables HTTPS after DNS resolves;
- code-server and PostgreSQL credentials are unique per participant;
- only SSH, HTTP, and HTTPS are exposed publicly;

> **Architecture:** Nginx is the only public application entry point. code-server, Shiny Server, FastAPI, ShinyProxy, and PostgreSQL listen locally and are reached through Nginx where appropriate.

## Authenticate doctl and Verify access
Using a named context makes it easier to separate this account from other DigitalOcean accounts.

```bash
doctl auth init --context workshop

# Paste the PAT when prompted. Input may remain invisible while pasting.
# Activate that context:
doctl auth switch --context workshop

# verify
doctl auth list
doctl account get
doctl compute region list
```

If these return account and region information, authentication is working.

## prepare domain
- Create a workshop sub-domain in DigitalOcean (Core Cloud → Networking → Domains → Add a domain), e.g. `earl.sjp-analytics.co.uk`.
- Delegate that subdomain in Cloudflare. Create NS records in the DNS Records section using the DigitalOcean nameservers. "For anything under earl.sjp-analytics.co.uk, ask DigitalOcean."

Example participant hostnames:

```text
dsi-01.earl.sjp-analytics.co.uk
dsi-02.earl.sjp-analytics.co.uk
...
dsi-10.earl.sjp-analytics.co.uk
```

DNS works like an address book. Each participant hostname receives an `A` record pointing to that participant Droplet's public IPv4 address:

```text
dsi-01.earl.sjp-analytics.co.uk -> participant 01 public IPv4
dsi-02.earl.sjp-analytics.co.uk -> participant 02 public IPv4
dsi-15.earl.sjp-analytics.co.uk -> participant 15 public IPv4
```

Create these records only after the Droplets exist because DigitalOcean assigns their public addresses during creation.

The provisioning script currently assumes DigitalOcean DNS. Set `CREATE_DIGITALOCEAN_DNS=false` if DNS is managed elsewhere, then create equivalent `A` records with that provider.

## Define infrastructure variables

- add env vars to `resources/workshop.env`

```bash
chmod 600 resources/workshop.env

CONFIG_FILE="${1:-./workshop.env}"

if [[ ! -r "$CONFIG_FILE" ]]; then
  printf 'Configuration file is not readable: %s\n' "$CONFIG_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
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

Check current availability before committing to values:

```bash
doctl compute region list
doctl compute size list
doctl compute image list-distribution --public
```

Region-droplet combination options for builder:

Slug                         Description                      Memory     VCPUs    Disk    Price Monthly    Price Hourly  Region
s-1vcpu-2gb-intel            Basic Intel                      2048       1        50      14.00            0.020830        lon1
s5-1vcpu-3gb-50gb            v5 Shared                        3072       1        50      25.89            0.034800        atl1

## Create the administrator SSH key record

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

## Create a Project

A Project groups the workshop resources for organisation and billing visibility.

```bash
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
```

## Create the VPC

The VPC is the private regional network for the Droplets.

```bash
if ! doctl vpcs list --format Name --no-header | grep -Fxq "$VPC_NAME"; then
  doctl vpcs create \
    --name "$VPC_NAME" \
    --region "$REGION" \
    --ip-range "$VPC_RANGE" \
    --description "Private network for DSI workshop Droplets"
fi

VPC_UUID=$(doctl vpcs list --format ID,Name --no-header \
  | awk -v name="$VPC_NAME" '$2 == name {print $1; exit}')

test -n "$VPC_UUID"
echo "$VPC_UUID"
```

## Cloud Firewall

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

```bash
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
```

## Golden image

DigitalOcean uses Droplet snapshots for golden images.

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

### Create the builder Droplet

```bash
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

doctl projects resources assign "$PROJECT_ID" \
  --resource "do:droplet:$BUILD_ID"
`
echo "$BUILD_ID $BUILD_IP"
ssh "root@${BUILD_IP}"
```

### Run a pinned bootstrap script

```bash
BOOTSTRAP_URL="https://raw.githubusercontent.com/earl-workshop26/resources/REPLACE_WITH_COMMIT_SHA/bootstrap.sh"
BOOTSTRAP_SHA256="REPLACE_WITH_REAL_SHA256"

curl -fsSL "$BOOTSTRAP_URL" -o /tmp/bootstrap.sh
printf '%s  %s\n' "$BOOTSTRAP_SHA256" /tmp/bootstrap.sh \
  | sha256sum --check
chmod 700 /tmp/bootstrap.sh
sudo /tmp/bootstrap.sh
```

Calculate the checksum from the exact pinned file:

```bash
curl -fsSL "$BOOTSTRAP_URL" -o bootstrap.sh
sha256sum bootstrap.sh
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

### Test the builder

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
```

### Clean the builder and prepare the snapshot

```bash
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
```

### Create the snapshot

```bash
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
```

## Participant cloud-init template

The `student` account already exists in the snapshot because installed services refer to it. Cloud-init can add its participant-specific SSH key and sudo policy.

**PASSWORDS MUST NOT CONTAIN \'**. Use a restricted password alphabet, or encode substitutions safely. For workshop automation, generating passwords from letters, digits, _ and - is the simplest option.

## Provisioning participant VMs
yaml check requires PyYAML so install in virtual env in directory where provisioning script lives.

```bash
cd resources
python3 -m venv .venv
.venv/bin/python -m pip install PyYAML
```

For each participant, the provisioning script (`resources/provision-participants.sh`):

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

A staging certificate intentionally produces a browser trust warning. Once the complete workflow succeeds, delete the disposable test Droplet and DNS record, then provision the real class with appropriate `PARTICIPANT_COUNT` (9) and with `CERTBOT_STAGING=false`.

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

# Workshop outline

## Part 1: Infrastructure (30 min)

- Explain Projects, VPCs, tags, Cloud Firewalls, Droplets, snapshots, DNS, Nginx, HTTPS, and cloud-init.
- Explain network configuration and HTTPS.
- Show why only ports 22, 80, and 443 are public. `nginx`
- Connect with the supplied key:

```bash
ssh -i dsi-01-ssh student@dsi-01.earl.sjp-analytics.co.uk
```

- Demonstrate passwordless sudo:

```bash
sudo -n whoami
```

## Part 2: PostgreSQL

Teaching databasing - free relational data.

## Part 3: Shiny (20 min)

```r
readRenviron("~/.config/dsi/database.env")

library(DBI)
con <- dbConnect(
  RPostgres::Postgres(),
  dbname = Sys.getenv("PGDATABASE"),
  host = Sys.getenv("PGHOST"),
  port = as.integer(Sys.getenv("PGPORT")),
  user = Sys.getenv("PGUSER"),
  password = Sys.getenv("PGPASSWORD")
)
```

- Create myapp.
- Deploy to `/srv/shiny-server/myapp`.
- Deploy with Git/GitHub (public repo)
- Browse (`Nginx` again):

```text
https://dsi-01.earl.sjp-analytics.co.uk/shiny/myapp/
```

## Part 4: FastAPI (20 min)

<!-- FastAPI is still not enabled or started

cloud-init starts:

docker nginx postgresql shiny-server shinyproxy
code-server@student

but not:

dsi-fastapi

Add:

systemctl enable --now dsi-fastapi

However, this only works if the golden image contains:

/home/student/fastapi/main.py

If workshop participants are expected to create the FastAPI application themselves, leaving it stopped is ok. 
/api/ will initially return 502 Bad Gateway. -->

- Build the API.
- Query PostgreSQL on `127.0.0.1:5432`.
- Load credentials from `~/.config/dsi/database.env`.
- Use Swagger UI through Nginx:

```text
https://dsi-01.earl.sjp-analytics.co.uk/api/docs
```

## Part 5: Docker and ShinyProxy (30 min)

- Build a container.
- Explain containerised deployment.
- Access ShinyProxy through:

```text
https://dsi-01.earl.sjp-analytics.co.uk/proxy/
```

## Part 6: Quarto (20 min)

- Create a Quarto report.
- Query PostgreSQL data.
- Render to HTML.
- Publish through Nginx or retrieve it with SCP.

# Updating the golden image

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

# Teardown

Delete participant Droplets promptly after the workshop:

```bash
DROPLET_IDS=$(doctl compute droplet list \
  --tag-name "$PARTICIPANT_TAG" \
  --format ID --no-header | tr '\n' ' ')

if [ -n "${DROPLET_IDS// }" ]; then
  doctl compute droplet delete $DROPLET_IDS --force
fi
```

Delete the participant DNS records, then remove local credential files:

```bash
shred -u participant-config/cloud-init-*.yml 2>/dev/null || true
shred -u participant-config/access-details.csv 2>/dev/null || true
shred -u participant-config/dsi-*-ssh 2>/dev/null || true
rm -f participant-config/dsi-*-ssh.pub
```

Treat all credentials as valid until they are explicitly expired or their Droplets are deleted. Secure deletion is not guaranteed on every filesystem, SSD, snapshot, or backup.

# Azure-to-DigitalOcean mapping

| Azure | DigitalOcean replacement |
| --- | --- |
| Subscription | Account or team |
| Resource groups | Project plus tags |
| VNet and subnet | Regional VPC |
| NSG | Cloud Firewall attached by tag |
| VM | Droplet |
| `az` | `doctl` |
| Compute Gallery image version | Named Droplet snapshot |
| VM custom data | User data and cloud-init |
| `az vm run-command` | SSH, cloud-init, or configuration management |
| `waagent -deprovision` | Clean cloud-init, machine ID, host keys, and credentials |
| Public IP resource | Droplet public IPv4/IPv6 |

# Final pre-flight checklist

- [ ] Region supports the selected sizes and snapshot.
- [ ] The trainer SSH source is a correct and stable `/32` address.
- [ ] The Cloud Firewall exposes only ports 22, 80, and 443.
- [ ] PostgreSQL listens only on loopback.
- [ ] code-server, Shiny, FastAPI, and ShinyProxy listen only on loopback.
- [ ] Every participant has a unique SSH key.
- [ ] `student` can connect with that key.
- [ ] `sudo -n whoami` returns `root`.
- [ ] Every participant Nginx configuration has the correct `server_name`.
- [ ] Every DNS `A` record points to the matching public IP.
- [ ] Certbot staging succeeds before any production issuance.
- [ ] Production HTTPS works for every hostname.
- [ ] `certbot.timer` is active.
- [ ] Nginx WebSocket proxying works for code-server and Shiny.
- [ ] Snapshot clones regenerate machine ID and SSH host keys.
- [ ] cloud-init completes successfully.
- [ ] Every participant has unique code-server and PostgreSQL passwords.
- [ ] The access CSV, cloud-init files, and private keys are mode `0600` and excluded from Git.
- [ ] Teardown commands have been tested on disposable resources.
- [ ] The previous known-good snapshot remains available until after the workshop.
