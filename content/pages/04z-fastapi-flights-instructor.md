---
id: fastapi-flights-instructor
title: "Instructor notes: Flights API"
slug: "fastapi-flights-instructor"
order: 910
section: "Instructor resources"
section_order: 910
summary: "Preparation and recovery notes for the FastAPI workshop session"
level: "Instructor"
estimated_minutes: 30
---

## Intended starting state

Before participants begin:

- PostgreSQL is active on `127.0.0.1:5432`;
- `flights.route_details` exists and contains data;
- Nginx is active and proxies `/api/` to `127.0.0.1:8000`;
- the `dsi-fastapi` unit is installed but disabled and stopped;
- no process listens on port `8000`;
- a public `/api/` request returns `502 Bad Gateway`;
- the non-interactive `fastapi` service account exists;
- `dsi-fastapi.service` specifies `User=fastapi` and `Group=fastapi`;
- cloud-init has already installed a private database configuration at `/home/fastapi/.config/dsi/database.env`;
- the configuration file is owned by `fastapi:fastapi` with mode `0600`;
- `/home/fastapi/.config/dsi` is owned by `fastapi:fastapi` with mode `0700`;
- the application code and virtual environment expected by `dsi-fastapi.service` are present;
- participants do not need to copy database credentials manually.

## Pre-flight checks

Check the supporting services and the intended stopped state:

```bash
systemctl is-active postgresql
systemctl is-active nginx
systemctl is-enabled dsi-fastapi || true
systemctl is-active dsi-fastapi || true
sudo ss -lntp | grep -E ':(5432|8000|443)' || true
```

Confirm the dedicated account and service configuration:

```bash
id fastapi
getent passwd fastapi
systemctl show dsi-fastapi   --property=User   --property=Group   --property=WorkingDirectory   --property=ExecStart
```

Expected service identity:

```text
User=fastapi
Group=fastapi
```

Confirm that cloud-init provisioned the service credential file without displaying its contents:

```bash
sudo ls -ld /home/fastapi/.config/dsi
sudo ls -l /home/fastapi/.config/dsi/database.env
sudo -u fastapi test   -r /home/fastapi/.config/dsi/database.env
echo $?
```

The final command should print `0`.

Confirm the expected ownership and modes:

```bash
test "$(stat -c '%U:%G' /home/fastapi/.config/dsi)"   = "fastapi:fastapi"
test "$(stat -c '%a' /home/fastapi/.config/dsi)" = "700"
test "$(stat -c '%U:%G'   /home/fastapi/.config/dsi/database.env)"   = "fastapi:fastapi"
test "$(stat -c '%a'   /home/fastapi/.config/dsi/database.env)" = "600"
```

Confirm the initial failure:

```bash
curl -i http://127.0.0.1:8000/health || true
curl -i   https://dsi-01.earl.sjp-analytics.co.uk/api/health
```

The local request should fail to connect and the public request should return `502 Bad Gateway`.

## Optional instructor start test

Before the workshop, confirm that the unit can start as `fastapi`, then restore the intended starting state:

```bash
sudo systemctl start dsi-fastapi
systemctl is-active dsi-fastapi
```

Confirm process ownership:

```bash
ps -eo user,group,pid,cmd   | grep '[u]vicorn.*app.main:app'
```

The Uvicorn process should belong to `fastapi:fastapi`.

Test both routes:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail   https://dsi-01.earl.sjp-analytics.co.uk/api/health
```

Restore the starting state:

```bash
sudo systemctl disable --now dsi-fastapi
sudo systemctl reset-failed dsi-fastapi || true
```

## Timing

| Time | Activity |
|---|---|
| 0 to 4 minutes | Observe the stopped service and `502` response |
| 4 to 9 minutes | Inspect the `fastapi` account and systemd unit |
| 9 to 13 minutes | Inspect deployment permissions |
| 13 to 17 minutes | Verify the pre-provisioned database configuration |
| 17 to 20 minutes | Test Python and PostgreSQL as `fastapi` |
| 20 to 23 minutes | Enable and start `dsi-fastapi` |
| 23 to 27 minutes | Use Swagger UI through Nginx |
| 27 to 30 minutes | Call the API from a local machine |

## Teaching emphasis

Keep the service boundaries and identities visible:

```text
local client
  -> Nginx
  -> Uvicorn running as fastapi
  -> FastAPI
  -> psycopg
  -> PostgreSQL
```

Emphasise these distinctions:

- `student` is the interactive participant account and performs administration through `sudo`;
- `fastapi` is the restricted service identity that runs Uvicorn;
- FastAPI is the Python framework;
- Uvicorn is the ASGI server process;
- systemd manages the process lifecycle and service identity;
- Nginx is the public reverse proxy;
- PostgreSQL is the data store.

A `502 Bad Gateway` response is useful evidence. It shows that Nginx was reached but its configured upstream was unavailable.

## Credential provisioning change

Cloud-init creates separate protected copies of `database.env` for the relevant accounts. The normal participant activity must **not** include commands that copy the student credential file into the `fastapi` home directory.

The participant lesson should only verify:

```bash
sudo -u fastapi test   -r /home/fastapi/.config/dsi/database.env
echo $?
```

Keep manual installation commands only as an instructor recovery procedure.

## Test the runtime as `fastapi`

Confirm that the virtual environment is usable by the service account:

```bash
sudo -u fastapi   /opt/dsi-fastapi/.venv/bin/python -c   'import fastapi, psycopg, uvicorn; print("imports successful")'
```

Test PostgreSQL using the service account configuration:

```bash
sudo -u fastapi bash -c '
  set -a
  source /home/fastapi/.config/dsi/database.env
  set +a
  psql -c "SELECT COUNT(*) FROM flights.route_details;"
'
```

Do not display the environment file itself.

## Important compatibility check

The project uses:

```python
app = FastAPI(root_path="/api")
```

This assumes Nginx removes the `/api/` prefix when proxying to Uvicorn. Confirm that these public resources load:

```text
/api/docs
/api/openapi.json
```

## Recovery procedures

### Restore a missing FastAPI credential copy

Use this only if cloud-init did not create the expected file:

```bash
sudo install -d   -o fastapi   -g fastapi   -m 0700   /home/fastapi/.config/dsi
```

```bash
sudo install   -o fastapi   -g fastapi   -m 0600   /home/student/.config/dsi/database.env   /home/fastapi/.config/dsi/database.env
```

Verify recovery:

```bash
sudo -u fastapi test   -r /home/fastapi/.config/dsi/database.env
```

### Service troubleshooting

```bash
sudo systemctl restart postgresql
sudo systemctl restart dsi-fastapi
sudo systemctl restart nginx
sudo journalctl -u dsi-fastapi -n 100 --no-pager
sudo nginx -t
```

Check the effective service identity:

```bash
systemctl show dsi-fastapi   --property=User   --property=Group
```

To restore the beginning-of-session state:

```bash
sudo systemctl disable --now dsi-fastapi
sudo systemctl reset-failed dsi-fastapi || true
```

## Success criteria

Participants should finish with:

- `dsi-fastapi` enabled and active;
- Uvicorn running as `fastapi:fastapi`;
- Uvicorn listening only on `127.0.0.1:8000`;
- the pre-provisioned database configuration verified
- a successful database health response;
- Swagger UI working through `/api/docs`;
- one route request executed in Swagger UI;
- one request sent from the participant's local computer;
- an explanation of the complete request path and service-account boundary.
