# dsi-fastapi

A read-only FastAPI service for the workshop's PostgreSQL
`flights.route_details` view.

## Endpoints

- `GET /health`
- `GET /airports`
- `GET /airports/{source_code}/routes`
- `GET /airports/{source_code}/countries`

## Configuration

The process reads PostgreSQL settings from:

```text
~/.config/dsi/database.env
```

Required names:

```text
PGHOST
PGPORT
PGDATABASE
PGUSER
PGPASSWORD
```

Set `DSI_DATABASE_ENV` to use another file.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the local documentation at `http://127.0.0.1:8000/docs`.

The application uses `root_path="/api"` because the workshop's public URL is
served through an Nginx `/api/` reverse-proxy route.
