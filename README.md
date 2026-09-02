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

The portal includes application-managed user persistence, portal authentication, an authenticated
Markdown course experience, a protected administrator area, and an attendee VM-credentials
dashboard. VM passwords are encrypted at rest with a dedicated Fernet key.

## Repository layout

```text
assets/                  supplied brand guidance and image assets
content/workshop.yml    workshop title and subtitle
content/pages/          Markdown course pages
resources/              non-secret teaching resources
src/earl_workshop/      FastAPI app, loader, templates, and CSS
tests/                  content, persistence, authentication, and admin workflow tests
```

The supplied files under `assets/` are the branding authority. `assets/brand.md` currently approves `#E31837` as the primary colour and `#1D252D` as the secondary colour; the CSS uses those values and a system sans-serif fallback. The supplied `assets/cg-lion-news-cover-lion-jpg.jpg` is the visual source for the canonical local `assets/logo.svg` and `assets/favicon.png` files. The logo URL is served as SVG and the favicon URL as PNG; no external fonts, logos, CDN, or JavaScript framework is required.

## Authoring course content

The course is loaded from `content/` at application startup. `workshop.yml` contains only site-level metadata:

```yaml
title: Development to Deployment
subtitle: Infrastructure for Data Teams
```

Each `content/pages/*.md` file begins with a YAML front matter block followed by Markdown:

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

The authoring contract is:

- `id`, `title`, and `order` are required. `id` is the stable page ID: choose a unique,
  URL-safe value using letters, numbers, `-`, or `_`, and keep it unchanged when renaming a
  file or revising its title. Attendee completion is keyed by this value.
- `section` defaults to `Workshop`; `section_order` defaults to `0`. Sections are shown in
  ascending `section_order`, then case-insensitive section-name order. Pages within a section
  are shown in ascending `order`, then stable page ID. This makes navigation deterministic and
  entirely data-driven.
- `resources` defaults to an empty list. Each item must contain a relative `file` path and may
  contain a non-empty `label`. Paths are normalized to `/`, cannot be absolute, and cannot
  contain `..` segments. A resource is visible on a page only when that page declares it.
- The body is rendered as Markdown with fenced-code and table support. Raw HTML is escaped.

Changing front matter or adding/removing Markdown files changes the current course sequence when
the application restarts; no Python route edits are required.

Pages are ordered deterministically by `section_order`, section name, `order`, and stable page ID. Duplicate IDs, malformed YAML, missing required fields, invalid integer fields, and unsafe resource declarations produce actionable startup validation errors. Markdown supports fenced code and tables; raw HTML is escaped rather than rendered as trusted page markup.

## Course access, resources, and progress

Sign in and open `/course` for the authenticated course index. Course pages at
`/course/<stable-page-id>` require an active portal session. They show previous/next links across
the current deterministic page sequence, a page-specific resources menu, and the current
attendee's completion summary.

Declared resource files are intentionally public workshop teaching material. A declared file is
available at a stable URL such as:

```text
http://127.0.0.1:8000/resources/examples/hello.txt
```

The page menu also provides a VM-friendly command, for example:

```bash
curl -fL http://127.0.0.1:8000/resources/examples/hello.txt
```

The public route serves only existing files declared by current Markdown pages, after normalized
path and resolved-root checks. Absolute paths, traversal (including encoded traversal), symlinks
outside the resources root, undeclared files, and missing files return a safe not-found response.
This route is deliberately unauthenticated for attendee VMs; course HTML remains authenticated.
Set `EARL_WORKSHOP_PUBLIC_BASE_URL` when a reverse proxy or public domain should be used in the
browser and curl commands. Otherwise the current request origin is used.

The completion checkbox uses an authenticated POST protected by the same session-bound CSRF token
as the other state-changing forms. Saving a checked box marks the stable page ID complete;
unchecking and saving marks it incomplete. One unique record per attendee/page is retained in
SQLite, so state survives logout, application restart, and content filename/title changes.
Progress percentages count only current page IDs, so records for pages removed from the course are
ignored rather than breaking the current summary. Resource files must contain no passwords,
credentials, private keys, database files, configuration secrets, or other sensitive material.

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

## Administrator operations

After creating the first administrator, sign in and open `/admin`. Every administrator page and
mutation checks the signed-in `admin` role on the server and every form carries the session-bound
CSRF token. The area provides:

- attendee creation with a normalized unique username, optional display name, and an initial
  password;
- password replacement, display-name updates, and activation/deactivation for attendee accounts;
- VM credential creation and editing for host/IP, SSH username, and an optional encrypted password
  replacement;
- assignment, reassignment, and unassignment of existing VM records; moving a VM also clears any
  previous assignment held by the selected attendee so ownership is unambiguous;
- one overview of all attendee accounts, active state, VM host, and current-course progress.

There is no application-level attendee capacity limit. Passwords are never echoed in validation
messages or general administrator lists. A blank VM replacement-password field keeps the existing
encrypted password. Portal password resets invalidate the attendee's existing sessions.

Progress is calculated against the Markdown pages loaded from the current `content/` directory:
the overview's completed count, total, and last-progress timestamp do not use a hard-coded page
total. VMs are entered manually in v0.1.0; cloud provisioning and related infrastructure
automation are deferred.

Build an installable wheel with:

```bash
uv build
```

The wheel includes the package templates/CSS plus the current placeholder content, resources, and supplied asset files. When the package is run outside a source checkout, it falls back to those packaged files; set the content/resource/asset directory variables to use an external authoring or deployment directory.

## Deferred infrastructure

This v0.1.0 increment does not include VM provisioning, SSH connectivity checks, VM health
monitoring, DigitalOcean/Terraform provisioning, production bootstrap automation, final
curriculum, domain/TLS automation, or conference deployment. VM provisioning is not part of
v0.1.0: administrators enter VM records manually through `/admin`. It also does not require
Node.js.
