# EARL Workshop: DigitalOcean -> FastAPI Webserver

The complete deployment run as follows:

  - Generate or select the secure SSH key.
  - Create the Droplet.
  - Apply the DigitalOcean Cloud Firewall.
  - Run cloud-init to install and start FastAPI behind Nginx.
  - Create or update the workshop A record.
  - Wait for the hostname to resolve to the Droplet.
  - Verify the HTTP health endpoint.
  - Run Certbot’s Nginx plugin.
  - Test certificate renewal.
  - Verify the HTTPS health response.
  - Create the first portal administrator interactively.

## Pre-requisite: ssh key

```bash
ssh-keygen \
  -t ed25519 \
  -a 100 \
  -f ~/.ssh/digitalocean_workshop \
  -C "workshop-digitalocean"

doctl compute ssh-key import workshop-digitalocean \
  --public-key-file ~/.ssh/digitalocean_workshop.pub
doctl compute ssh-key list --format ID,Name
```

## Files

- `deploy-webserver.sh`: run locally. Creates the Droplet, firewall, DNS record, and HTTPS certificate.
- `provision-webserver.sh`: embedded into Droplet user data by the deployment script.
- `webserver.env.example`: copy to `webserver.env` and configure.

## Preparation

```bash
cp webserver.env.example webserver.env
chmod 600 webserver.env
openssl passwd -6 # on linux
```

Paste the resulting password hash into `WORKSHOP_PASSWORD_HASH` in `deployment.env`. Configure `SSH_KEY_NAME` and `CERTBOT_EMAIL` too.

The local machine needs `doctl`, `ssh`, `ssh-keygen`, `openssl`, `curl`, `dig`, `python3`, and the Python `cryptography` package. Authenticate the configured doctl context before deployment.

## Deploy

```bash
chmod +x deploy-webserver.sh provision-webserver.sh
./deploy-webserver.sh ./webserver.env
```

## Post-deployment

Create the first portal administrator:

```bash
ssh -t -i ./workshop-ssh workshop@workshop.earl.sjp-analytics.co.uk \
  'sudo earl-workshop-init create-admin'
```

Useful service commands:

```bash
sudo earl-workshop-init status
sudo earl-workshop-init logs
sudo earl-workshop-init health
sudo earl-workshop-init test-renewal
```

The private SSH key and `access-details.env` are created beside the deployment script. Keep both private and do not commit them.
