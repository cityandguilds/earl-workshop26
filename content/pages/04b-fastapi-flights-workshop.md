---
id: fastapi-flights
title: "Publish flights data with FastAPI"
slug: "fastapi-flights"
order: 310
section: "FastAPI"
section_order: 310
summary: "Create, start, document, and query a FastAPI backed by PostgreSQL"
level: "Beginner"
estimated_minutes: 30
---

## Session goal

In this session you will enable a prepared FastAPI service that exposes read-only endpoints for data in `flights.route_details`.

The API runs under a dedicated, non-interactive Linux service account called `fastapi`. Application code, runtime permissions, and database credentials are kept separate from the participant's `student` account.

At the beginning of the session, `dsi-fastapi` is disabled and stopped. Nginx already routes `/api/` to the expected upstream, so the public API initially returns **502 Bad Gateway**.

By the end, the request path will be:

```text
Local client
    |
    | HTTPS on public port 443
    v
Nginx /api/ route
    |
    | HTTP on 127.0.0.1:8000
    v
Uvicorn and FastAPI
    |
    | process runs as Linux user: fastapi
    v
PostgreSQL on 127.0.0.1:5432
    |
    v
flights.route_details
```

## Learning outcomes

By the end of the session, you should be able to:

- explain what an API endpoint is;
- identify path and query parameters;
- describe the roles of FastAPI, Uvicorn, systemd, Nginx, and PostgreSQL;
- explain why network services use dedicated service accounts;
- enable and start a systemd service;
- use Swagger UI to call an endpoint;
- call the API from your local computer.
- interpret common HTTP status codes.

## What is FastAPI?

FastAPI is a Python framework for creating web APIs. An API receives structured requests and returns structured responses, commonly JSON.

FastAPI uses Python type information to validate values and produce an OpenAPI description. It provides interactive Swagger UI documentation at `/docs` by default and ReDoc at `/redoc` by default.

The workshop app uses PostgreSQL directly through the `psycopg2` driver. FastAPI does not require a particular database library or database system.

Official resources:

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [FastAPI SQL database tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [FastAPI OpenAPI documentation reference](https://fastapi.tiangolo.com/reference/openapi/docs/)

## Why use a service account?

A public-facing application should not run as a participant's personal login account. The dedicated `fastapi` account gives the service its own identity and permissions.

In this workshop:

- `student` is used for interactive administration with `sudo`;
- `fastapi` runs the API process;
- application code is stored below `/opt/dsi-fastapi`;
- database settings are stored below `/home/fastapi/.config/dsi`;
- the service binds only to `127.0.0.1:8000`;
- Nginx provides the public HTTPS route.

The `fastapi` account should receive only the access needed to read the app, load its Python environment, read its database settings, and connect to local PostgreSQL.

## HTTP methods, paths, and parameters

The workshop API provides read-only `GET` endpoints:

```text
GET /health
GET /airports
GET /airports/{source_code}/routes
GET /airports/{source_code}/countries
```

For this request:

```text
GET /airports/MAN/routes?destination_country=France&limit=20
```

- `MAN` is a path parameter;
- `destination_country` is an optional query parameter;
- `limit` is an optional query parameter;
- the response body is JSON.

Common status codes in this exercise are:

- `200 OK`: the request succeeded;
- `404 Not Found`: no matching data was found;
- `422 Unprocessable Content`: an input failed validation;
- `502 Bad Gateway`: Nginx could not obtain a response from FastAPI.

## The prepared application

The application is installed at:

```text
/opt/dsi-fastapi/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   └── models.py
├── .venv/
├── requirements.txt
└── README.md
└── .gitignore
```

The API loads database settings from the home directory of the account running it:

```text
~/.config/dsi/database.env
```

Because systemd runs the process as `fastapi`, this resolves to:

```text
/home/fastapi/.config/dsi/database.env
```

## 0 to 3 minutes: observe the initial failure

Check the service state:

```bash
systemctl is-enabled dsi-fastapi || true
systemctl is-active dsi-fastapi || true
```

Test the local upstream:

```bash
curl -i http://127.0.0.1:8000/health
```

Nothing should be listening on port `8000` yet.

Test the public Nginx route:

```bash
curl -i https://dsi-01.earl.sjp-analytics.co.uk/api/health
```

The expected starting response is:

```text
502 Bad Gateway
```

This confirms that Nginx is available but its configured API upstream is not running.

## 3 to 6 minutes: inspect the service account and unit

Confirm that the dedicated account exists:

```bash
getent passwd fastapi
id fastapi
```

Inspect the service definition:

```bash
systemctl cat dsi-fastapi
```

The unit should use values equivalent to:

```ini
[Service]
User=fastapi
Group=fastapi
WorkingDirectory=/opt/dsi-fastapi
ExecStart=/opt/dsi-fastapi/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

Verify the important properties directly:

```bash
systemctl show dsi-fastapi \
  --property=User \
  --property=Group \
  --property=WorkingDirectory \
  --property=ExecStart
```

Do not start the service yet.

## 6 to 10 minutes: deploy the app

Clone the workshop repository into a temporary directory:

```bash
REPOSITORY_URL="https://github.com/cityandguilds/earl-workshop26.git"
APP_SOURCE_DIR="resources/dsi-fastapi"

rm -rf /tmp/earl-workshop26

git clone \
  --depth 1 \
  "$REPOSITORY_URL" \
  /tmp/earl-workshop26
```

Install the application into the directory expected by dsi-fastapi.service:

```bash
sudo install -d \
  -o root \
  -g fastapi \
  -m 0750 \
  /opt/dsi-fastapi

sudo cp -a \
  "/tmp/earl-workshop26/$APP_SOURCE_DIR/." \
  /opt/dsi-fastapi/
```

Apply ownership and permissions:

```bash
sudo chown -R root:fastapi /opt/dsi-fastapi

sudo find /opt/dsi-fastapi \
  -type d \
  -exec chmod 0750 {} \;

sudo find /opt/dsi-fastapi \
  -type f \
  -exec chmod 0640 {} \;
```

Confirm that the expected application entry point exists and is readable by the service account:

```bash
sudo test -f /opt/dsi-fastapi/app/main.py

sudo -u fastapi test \
  -r /opt/dsi-fastapi/app/main.py

echo $?
```

An exit status of 0 confirms that the application is ready for the fastapi service account.

Remove the temporary clone:

```bash
rm -rf /tmp/earl-workshop26
```

## 10 to 14 minutes: inspect application permissions

Inspect the deployment directory:

```bash
sudo find /opt/dsi-fastapi -maxdepth 2 \
  -printf '%M %u:%g %p\n' \
  | head -40
```

Confirm that the service account can read the application:

```bash
sudo -u fastapi test -r /opt/dsi-fastapi/app/main.py
echo $?
```

An exit value of `0` means the file is readable.

The application should not be editable by the service account. Confirm this without changing the file:

```bash
sudo -u fastapi test -w /opt/dsi-fastapi/app/main.py
echo $?
```

A non-zero value is expected when the deployment is owned by `root` and only readable by `fastapi`.

## 14 to 17 minutes: check database configuration for `fastapi`

Confirm ownership and permissions:

```bash
sudo ls -ld /home/fastapi/.config/dsi
sudo ls -l /home/fastapi/.config/dsi/database.env
```

Confirm that `fastapi` can read the file:

```bash
sudo -u fastapi test \
  -r /home/fastapi/.config/dsi/database.env
echo $?
```

Do not print the file. Do not store it in the application directory or Git repository.

## 17 to 20 minutes: test as the service account

Confirm that the API's Python packages load under the same account used by systemd:

```bash
sudo -u fastapi \
  /opt/dsi-fastapi/.venv/bin/python -c \
  'import fastapi, psycopg, uvicorn; print("imports successful")'
```

Test PostgreSQL using the service account's environment file:

```bash
sudo -u fastapi bash -c '
  set -a
  source /home/fastapi/.config/dsi/database.env
  set +a
  psql -c "SELECT COUNT(*) FROM flights.route_details;"
'
```

This verifies the service identity, configuration permissions, PostgreSQL credentials, and database view before the web service starts.

## 20 to 23 minutes: enable and start the API

Enable the service at boot and start it now:

```bash
sudo systemctl enable --now dsi-fastapi
```

Check its state:

```bash
systemctl is-enabled dsi-fastapi
systemctl is-active dsi-fastapi
systemctl status dsi-fastapi --no-pager
```

Confirm that Uvicorn is listening only on the loopback address:

```bash
sudo ss -lntp | grep ':8000'
```

Test FastAPI directly on the VM:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:8000/health
```

Expected response shape:

```json
{"status":"ok","database":"workshop_db"}
```

## 23 to 27 minutes: use Swagger UI through Nginx

Open the interactive documentation:

[Open the Flights API Swagger UI](https://dsi-01.earl.sjp-analytics.co.uk/api/docs)

Use an endpoint:

1. expand `GET /airports/{source_code}/routes`;
2. select **Try it out**;
3. enter `MAN` for `source_code`;
4. optionally enter `France` for `destination_country`;
5. enter `20` for `limit`;
6. select **Execute**;
7. inspect the request URL, response code, and JSON body.

FastAPI generates Swagger UI from the application's OpenAPI description. Nginx publishes it through the `/api/` route.

## 27 to 30 minutes: call the API from your local machine

From a terminal on your own computer, use the system `curl` command:

```bash
curl --fail --silent --show-error \
  'https://dsi-01.earl.sjp-analytics.co.uk/api/airports/MAN/routes?destination_country=France&limit=5'
```

Format another response with the local Python standard library:

```bash
curl --fail --silent --show-error \
  'https://dsi-01.earl.sjp-analytics.co.uk/api/airports/MAN/countries?limit=10' \
  | python3 -m json.tool
```

On Windows PowerShell:

```powershell
Invoke-RestMethod `
  -Uri "https://dsi-01.earl.sjp-analytics.co.uk/api/airports/MAN/countries?limit=10"
```

The request travels through Nginx to a Uvicorn process running as `fastapi`, which queries PostgreSQL and returns JSON.

## Troubleshooting

### `/api/` still returns 502

Check each layer in order:

```bash
systemctl is-active dsi-fastapi
sudo ss -lntp | grep ':8000'
curl -i http://127.0.0.1:8000/health
sudo nginx -t
systemctl is-active nginx
```

If the direct local request succeeds but the public request fails, investigate Nginx. If the local request fails, investigate `dsi-fastapi` first.

### The service fails to start

Inspect its log:

```bash
sudo journalctl -u dsi-fastapi -n 100 --no-pager
```

Check that systemd is configured to use the service account:

```bash
systemctl show dsi-fastapi --property=User --property=Group
```

Expected values:

```text
User=fastapi
Group=fastapi
```

### The database configuration cannot be read

```bash
sudo -u fastapi test \
  -r /home/fastapi/.config/dsi/database.env
echo $?
```

If necessary, restore the intended permissions:

```bash
sudo chown fastapi:fastapi \
  /home/fastapi/.config/dsi/database.env
sudo chmod 0600 \
  /home/fastapi/.config/dsi/database.env
```

### FastAPI returns 500

Check:

- PostgreSQL is active;
- the service account can read its environment file;
- the settings specify `127.0.0.1:5432`;
- `flights.route_details` exists;
- the virtual environment contains the required dependencies.

### FastAPI returns 422

Read the JSON validation response. For example, the API rejects a `limit` below `1` or above the endpoint maximum before executing the SQL query.

## Exercises

### Exercise 1: confirm process ownership

```bash
ps -eo user,group,pid,cmd \
  | grep '[u]vicorn.*app.main:app'
```

Confirm that the Uvicorn process belongs to `fastapi`, not `student` or `root`.

### Exercise 2: discover airports

Use Swagger UI to call:

```text
GET /airports?country=United Kingdom&limit=25
```

Identify the source airport code for Manchester.

### Exercise 3: trigger validation

Use a `limit` of `0`. Explain why FastAPI returns `422` before running the SQL query.

### Exercise 4: trace one request

Explain the role of each component:

```text
local curl
  -> Nginx
  -> Uvicorn running as fastapi
  -> FastAPI endpoint
  -> psycopg
  -> PostgreSQL
  -> JSON response
```

## Check your understanding

1. Why should the API not run as `student`?
2. What does `User=fastapi` do in the systemd unit?
3. Why is the service's database configuration stored below `/home/fastapi`?
4. Why is the environment file mode `0600`?
5. Why is the application code readable but not writable by `fastapi`?
6. Why did Nginx initially return `502 Bad Gateway`?
7. Which component listens on `127.0.0.1:8000`?
8. Which component accepts the public HTTPS connection?

## Key takeaway

A network service should run with its own restricted identity. In this deployment, `student` administers the VM, `fastapi` runs Uvicorn and reads only its required configuration, Nginx provides the public HTTPS route, and PostgreSQL remains available only on the local host. Of course, we also now have an API layer that we could insert between our shiny app and the database if wanted a dedicated layer for database concerns.
