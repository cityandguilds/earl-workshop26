# EARL 2026 Workshop Portal

This repository contains the runnable v0.1.0 foundation for the City & Guilds EARL 2026 workshop, “Development to Deployment: Infrastructure for Data Teams”. It is a small FastAPI application with server-rendered HTML, local CSS, and filesystem-driven placeholder course content.

The current course prose is deliberately representative placeholder material. Authors can substantially revise it without changing Python route code.

## Run locally

The project requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run uvicorn earl_workshop.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The unauthenticated health check is available at `/healthz` and returns only `{"status":"ok"}`.

The installed console entry point is also available:

```bash
uv run earl-workshop serve
```

The portal foundation has no authentication or persistent attendee state yet. Those capabilities are intentionally reserved for later implementation slices.

## Repository layout

```text
assets/                  supplied brand guidance and image assets
content/workshop.yml    workshop title and subtitle
content/pages/          Markdown course pages
resources/              non-secret teaching resources
src/earl_workshop/      FastAPI app, loader, templates, and CSS
tests/                  content and application foundation tests
```

The supplied files under `assets/` are the branding authority. `assets/brand.md` currently approves `#E31837` as the primary colour and `#1D252D` as the secondary colour; the CSS uses those values and a system sans-serif fallback. No external fonts, logos, CDN, or JavaScript framework is required.

The frozen implementation plan names `assets/logo.svg` and `assets/favicon.png`, but those two files are not present in this checkout. The application only uses the existing supplied lion image as a local fallback until the named supplied files are restored; it does not generate or download substitute branding.

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
```

Session and VM-encryption key settings are represented for subsequent slices but are not required by this read-only foundation. Runtime data defaults to `.data/` in a source checkout and is ignored by Git.

Build an installable wheel with:

```bash
uv build
```

The wheel includes the package templates/CSS plus the current placeholder content, resources, and supplied asset files. When the package is run outside a source checkout, it falls back to those packaged files; set the content/resource/asset directory variables to use an external authoring or deployment directory.

## Deferred infrastructure

This foundation intentionally does not implement authentication, SQLite attendee state, VM credentials or assignments, progress tracking, administrator screens, resource download routes, DigitalOcean/Terraform provisioning, monitoring, production bootstrap automation, final curriculum, domain/TLS automation, or conference deployment. It also does not require Node.js.
