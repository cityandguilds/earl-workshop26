# EARL 2026 Workshop Portal

This repository contains the runnable v0.2.0 foundation for the City & Guilds EARL 2026 workshop, “Development to Deployment: Infrastructure for Data Teams”. It is a small FastAPI application with server-rendered HTML, local CSS, and filesystem-driven course-page skeletons.

The course skeleton covers Ubuntu VM context, a Bash primer, application and system dependencies, containers, PostgreSQL, deployment options, and serving Shiny, Quarto, and FastAPI applications. Its Markdown is intentionally limited to authoring prompts, so authors can substantially revise it without changing Python route code.

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

The public Learn more page uses these local thumbnail files:

- `src/earl_workshop/static/images/peoplecert-placeholder.png`
- `src/earl_workshop/static/images/city-guilds-placeholder.png`

Replace either file with your own PNG using the same name to update the corresponding card. A landscape image with a 3:2 aspect ratio works best.

The supplied files under `assets/` are the branding authority. `assets/brand.md` currently approves `#E31837` as the primary colour and `#1D252D` as the secondary colour; the CSS uses those values and a system sans-serif fallback. The visible logo uses the supplied self-contained `assets/cg-lion-news-cover-lion-jpg.jpg`, while the favicon uses `assets/favicon.png`. The SVG source is retained as a reference, but it links to a nested image resource and is unreliable when used as an HTML image. No external fonts, logos, CDN, or JavaScript framework is required.

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
- The body is rendered as CommonMark with table and strikethrough support. Raw HTML is escaped.
  Declare a code-fence language (for example, `bash`, `python`, `r`, `sql`, or `yaml`) for
  syntax highlighting. Quarto `{r}` fences are also highlighted as R. Unknown or omitted
  languages use plain code. Code blocks show their language above the snippet and preserve
  tabs and blank lines. Fences also work inside lists and blockquotes.
  Each code block has a Copy button that also supports HTTP pages
  through a selection-based copy fallback. If both browser copy methods are blocked, the code
  is selected for manual copying. Highlighting assets are served locally.

Changing front matter or adding/removing Markdown files changes the current course sequence when
the application restarts; no Python route edits are required.

Pages are ordered deterministically by `section_order`, section name, `order`, and stable page ID. Duplicate IDs, malformed YAML, missing required fields, invalid integer fields, and unsafe resource declarations produce actionable startup validation errors. Markdown supports fenced code and tables; raw HTML is escaped rather than rendered as trusted page markup.

## Course access, resources, and progress

Sign in and open `/course` for the authenticated course index. Course pages at
`/course/<stable-page-id>` require an active portal session. Signed-out visitors are taken to
sign-in and returned to the selected course page afterwards, including after a failed attempt.
Course pages show previous/next links across
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

The command prompts for a username, password, and confirmation. Portal roles are `admin` and `attendee`; administrator-only server routes return an authorization failure to signed-in attendees. Login errors intentionally use one generic message, and inactive accounts cannot establish a session. Login and logout forms carry a token bound to the signed session; missing or invalid CSRF tokens in a live session are rejected.

Protected pages and form submissions redirect signed-out users to login with “Please sign in
again to continue.” After login, users return to the relevant page; expired submissions are
never replayed and must be entered again. Saved course progress remains intact. An expired
login form opens a fresh sign-in form, and an expired logout returns to login. Copying a VM
password also opens login if the session has expired. Recovery happens on the next interaction;
the existing eight-hour session lifetime is unchanged.

An attendee signs in with their unique username, not their optional display name. The display name is for presentation in the administrator area and is not unique enough to authenticate with.

Attendees normally land on `/course` after signing in; a course page selected before sign-in
takes precedence. The attendee header includes **Get credentials**, which opens `/attendee`.
From there, **View VM credentials** reveals the assigned connection details. The SSH password
stays hidden and is fetched only when the attendee chooses to copy it. Administrators retain
their existing navigation and login destination.

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
total. VMs are entered manually in v0.2.0; cloud provisioning and related infrastructure
automation are deferred.

Build an installable wheel with:

```bash
uv build
```

The wheel includes the package templates/CSS plus the current course skeleton, resources, and supplied asset files. When the package is run outside a source checkout, it falls back to those packaged files; set the content/resource/asset directory variables to use an external authoring or deployment directory.

## Browser clipboard checks

The clipboard check exercises actual clipboard writes on localhost and an ordinary HTTP
origin, a rejected Clipboard API call, and a browser that blocks both copy methods:

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python tests/browser/check_course_copy.py
```

## Infrastructure as code

v0.3.0 increment includes DigitalOcean VM provisioning, SSH connectivity checks, production bootstrap automation, curriculum, domain/TLS automation, and conference deployment. Administrators enter VM records manually through `/admin`.
