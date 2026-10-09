# Provision participant environments

The `provision-participants.sh` script creates and configures the DigitalOcean virtual machines used by workshop participants.

For each participant, it:

1. Generates dedicated SSH, code-server, and database credentials.
2. Creates a participant-specific cloud-init configuration.
3. Creates a droplet from the configured workshop snapshot.
4. Assigns the droplet to the workshop VPC and DigitalOcean project.
5. Creates a DNS record, unless automatic DNS management is disabled.
6. Waits for the machine and its cloud-init configuration to become ready.
7. Configures HTTPS using Certbot.
8. Runs HTTP and HTTPS health checks.
9. Saves the participant’s access details locally.

## Requirements

The script requires:

- an authenticated `doctl` context named `workshop`
- an existing DigitalOcean project, VPC, SSH key, and workshop snapshot
- a workshop configuration file
- the participant cloud-init template
- common command-line tools such as `ssh`, `openssl`, `curl`, and `dig`
- a Python virtual environment containing PyYAML

By default, configuration is loaded from:

```text
infrastructure/config/workshop.env
```

## Running the script

From the repository root:

```bash
./infrastructure/provision-participants.sh
```

To use a different configuration file:

```bash
./infrastructure/provision-participants.sh /path/to/workshop.env
```

## Generated files

Credentials, SSH keys, rendered cloud-init files, and participant access details are stored under:

```text
.participant-config/
```

This directory contains sensitive information. It must remain excluded from version control and must not be published as a workshop resource.

## Existing environments

If a droplet with the expected participant name already exists, the script skips it. It does not reconcile, validate, or repair existing participant environments.

Review existing droplets, DNS records, credentials, and generated files before rerunning the script.

## Validation

Provisioning succeeds only after the script confirms that:

- SSH is available
- cloud-init has completed
- the provisioning completion marker exists
- DNS resolves to the expected address
- the health endpoint is available over HTTPS
- HTTP redirects to HTTPS

A failed run may leave partially created cloud resources. Inspect the DigitalOcean project and local generated files before retrying.

## Security

The script creates participant credentials, private SSH keys, and cloud-init files containing secrets. These files are restricted to the local user but must still be handled securely.

After the workshop:

- destroy participant infrastructure that is no longer required
- remove obsolete DNS records
- revoke workshop-specific access
- securely remove generated credentials and private keys
- confirm that no generated files were committed to the repository

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

## Participant VM Validation

```bash
ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  student@dsi-01.earl.sjp-analytics.co.uk

# expect: Permission denied (publickey).

ssh -i .participant-config/dsi-01-ssh \
  student@dsi-01.earl.sjp-analytics.co.uk \
  "sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin) '"

# expect:
# permitrootlogin without-password
# pubkeyauthentication yes
# passwordauthentication no
# kbdinteractiveauthentication no

ssh -i .participant-config/dsi-01-ssh \
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
