# EARL 2026 Workshop Portal

This repository contains the runnable v0.1.0 foundation for the City & Guilds EARL 2026 workshop, “Development to Deployment: Infrastructure for Data Teams”. It is a small FastAPI application with server-rendered HTML, local CSS, and filesystem-driven placeholder course content.

The current course prose is deliberately representative placeholder material. Authors can substantially revise it without changing Python route code.

## Run locally

The project requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn earl_workshop.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The unauthenticated health check is available at `/healthz` and returns only `{"status":"ok"}`.

The installed console entry point is also available:

```bash
uv run earl-workshop serve
```

The portal includes application-managed user persistence, portal authentication, and an attendee VM-credentials dashboard. VM passwords are encrypted at rest with a dedicated Fernet key; administrator assignment forms are intentionally deferred.

## Repository layout

```text
assets/                  supplied brand guidance and image assets
content/workshop.yml    workshop title and subtitle
content/pages/          Markdown course pages
resources/              non-secret teaching resources
src/earl_workshop/      FastAPI app, loader, templates, and CSS
tests/                  content, persistence, and authentication tests
```

The supplied files under `assets/` are the branding authority. `assets/brand.md` currently approves `#E31837` as the primary colour and `#1D252D` as the secondary colour; the CSS uses those values and a system sans-serif fallback. The supplied `assets/cg-lion-news-cover-lion-jpg.jpg` is the visual source for the canonical local `assets/logo.svg` and `assets/favicon.png` files. The logo URL is served as SVG and the favicon URL as PNG; no external fonts, logos, CDN, or JavaScript framework is required.

## Authoring course content

The course is loaded from `content/` at application startup. `workshop.yml` contains only site-level metadata:

```yaml
title: Development to Deployment
subtitle: Infrastructure for Data Teams
```

Each `content/pages/*.md` file begins with a small YAML front matter block:

```yaml
---
id: connect
title: Connect to your VM
order: 10
section: Getting started
section_order: 10
resources:
  - file: examples/hello.txt
    label: Workshop example note
---
```

`id`, `title`, and `order` are required. IDs must be unique stable URL-safe identifiers using letters, numbers, `-`, or `_`; progress in a later slice will be able to refer to them independently of filenames and titles. `section` defaults to `Workshop`, `section_order` defaults to `0`, and `resources` defaults to an empty list. Resource paths must be relative and cannot contain `..` segments.

Pages are ordered deterministically by `section_order`, `order`, section name, and stable page ID. Duplicate IDs, malformed YAML, missing required fields, invalid integer fields, and unsafe resource declarations produce actionable startup validation errors. Markdown supports fenced code and tables; raw HTML is escaped rather than rendered as trusted page markup.

Resources in this slice are only stored and declared as content foundations. Resource download routes are reserved for a later slice.

## Configuration and packaging

Settings are environment-driven. Useful variables include:

```text
EARL_WORKSHOP_HOST
EARL_WORKSHOP_PORT
EARL_WORKSHOP_CONTENT_DIR
EARL_WORKSHOP_RESOURCES_DIR
EARL_WORKSHOP_ASSET_DIR
EARL_WORKSHOP_DATA_DIR
EARL_WORKSHOP_PUBLIC_BASE_URL
EARL_WORKSHOP_ENVIRONMENT
EARL_WORKSHOP_SECURE_COOKIES
EARL_WORKSHOP_SESSION_SECRET
EARL_WORKSHOP_VM_ENCRYPTION_KEY
EARL_WORKSHOP_DATABASE_PATH
```

Runtime data defaults to `.data/` in a source checkout and is ignored by Git. The SQLite database defaults to `.data/earl_workshop.sqlite3`; set `EARL_WORKSHOP_DATA_DIR` to place the whole runtime directory elsewhere, or set `EARL_WORKSHOP_DATABASE_PATH` for an explicit SQLite path. Both locations must be writable and should be outside installed package files. The application creates the directory and current schema automatically on startup; initialization is safe to rerun against an existing database.

Set `EARL_WORKSHOP_SESSION_SECRET` to a long random value for any deployed application. Production refuses to start without it. In development and tests, an unconfigured process gets a random in-process secret so it cannot silently use a predictable shared signing key; sessions from that process do not survive a restart. Set `EARL_WORKSHOP_SECURE_COOKIES=true` when serving through HTTPS. Session cookies are HttpOnly, signed, and SameSite=Lax.

Set `EARL_WORKSHOP_VM_ENCRYPTION_KEY` to a generated Fernet key before starting the application. It is required in every environment and invalid or missing values make the application unavailable rather than falling back to plaintext. Generate one with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Accounts and authentication

Create the first administrator from an interactive terminal. The password is prompted securely and is never a command-line argument:

```bash
EARL_WORKSHOP_DATA_DIR=.data uv run earl-workshop create-admin
```

The command prompts for a username, password, and confirmation. Portal roles are `admin` and `attendee`; administrator-only server routes return an authorization failure to attendees and anonymous requests. Login errors intentionally use one generic message, and inactive accounts cannot establish a session. Login and logout forms carry a token bound to the signed session; missing or invalid CSRF tokens are rejected.

Portal account passwords are stored only as one-way Argon2 password hashes. They are not logged or returned by the application. VM passwords are a different credential type: they must be recoverable for the assigned attendee, so they are encrypted with `EARL_WORKSHOP_VM_ENCRYPTION_KEY` before being stored in the `vm_credentials.encrypted_password` field and decrypted only for that attendee's dashboard. The `vm_credentials` model stores the host and SSH username alongside that ciphertext; `vm_assignments` links a credential to an attendee and tracks whether it is active, with database uniqueness allowing at most one active VM per attendee and one active attendee per VM. Assignment lookup uses the authenticated session identity and never accepts an attendee-supplied record ID. An attendee without an active assignment sees a waiting state.

Build an installable wheel with:

```bash
uv build
```

The wheel includes the package templates/CSS plus the current placeholder content, resources, and supplied asset files. When the package is run outside a source checkout, it falls back to those packaged files; set the content/resource/asset directory variables to use an external authoring or deployment directory.

## Deferred infrastructure

This v0.1.0 increment intentionally does not implement administrator forms for creating or assigning VM records, VM provisioning, SSH connectivity checks, VM health monitoring, progress tracking, resource download routes, DigitalOcean/Terraform provisioning, production bootstrap automation, final curriculum, domain/TLS automation, or conference deployment. VM provisioning is not part of v0.1.0. It also does not require Node.js.
