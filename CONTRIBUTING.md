# Contributing

Thank you for contributing to the DSI Workshop project.

This repository contains a workshop website, course content, attendee resources, example applications, and cloud infrastructure automation. Changes should preserve the boundaries between those areas and avoid exposing credentials or operational files through the website.

## Ways to contribute

Contributions may include:

- fixing bugs in the FastAPI application
- improving authentication, administration, or progress tracking
- adding or revising workshop lessons or instructor resources
- correcting examples and exercise solutions
- improving templates, styles, and browser behaviour
- adding tests
- improving provisioning and deployment automation
- clarifying documentation

For a substantial change, open an issue or start a discussion before investing significant effort. This helps confirm the intended approach and avoids duplicated work.

## Repository structure

The main areas of the repository are:

```text
assets/             Brand source files and shared visual assets
content/            Workshop configuration and Markdown lessons
resources/          Attendee-downloadable files and example applications
src/earl_workshop/  Installable FastAPI application code
src/earl_workshop/static/
                    Browser JavaScript, CSS, and application images
src/earl_workshop/templates/
                    Jinja templates
tests/              Application, browser, and integration tests
infrastructure/     Provisioning and deployment automation
docs/               Developer and operator documentation
```

Use these boundaries when deciding where a change belongs:

- Put importable Python application code under `src/earl_workshop/`.
- Put workshop lessons and their metadata under `content/`.
- Put files intentionally offered to attendees under `resources/`.
- Put infrastructure provisioning and deployment automation under `infrastructure/`.
- Put contributor and operator guidance under `docs/`.
- Put application tests under `tests/`.

## Development setup

### Prerequisites

You will need:

- Git
- a Python version supported by `pyproject.toml`
- [uv](https://docs.astral.sh/uv/)

Infrastructure work may require additional tools. Consult the relevant infrastructure documentation before running provisioning commands.

### Create the development environment

Clone the repository and enter it:

```bash
git clone <repository-url>
cd <repository-directory>
```

Install the project and its development dependencies:

```bash
uv sync
```

If the project defines optional development dependencies, use the relevant extra or dependency group declared in `pyproject.toml`.

### Configure the application

Copy any supplied example environment file rather than creating configuration from memory:

```bash
cp .env.example .env
```

Never commit `.env` files containing live values.

## Running the application

see `SETUP.md`

## Making changes

Create a focused branch from the current default branch:

```bash
git switch -c <type>/<short-description>
```

Examples:

```text
fix/session-expiry
content/postgresql-exercise
infra/participant-validation
docs/content-authoring
```

Keep changes focused. Avoid combining application refactoring, curriculum revisions, and infrastructure changes in one pull request unless they are directly dependent on one another.

### Application code

For changes under `src/earl_workshop/`:

- preserve the existing `src` package layout
- keep request handling, business logic, data access, and presentation concerns separated where practical
- reuse the existing configuration system rather than reading environment variables throughout the codebase
- avoid embedding credentials, hostnames, deployment IDs, or workshop-specific secrets in source code
- add or update tests for changed behaviour
- preserve accessible HTML and keyboard-friendly interactions

### Templates and static files

For changes to templates, CSS, or JavaScript:

- reuse `base.html` for shared layout and navigation
- avoid duplicating markup across templates
- test attendee and administrator views where relevant
- verify layouts at narrow and wide viewport sizes
- ensure interactive controls have visible labels and keyboard support
- do not place secrets or privileged operational information in rendered pages or browser-side code

### Workshop content

Workshop lessons live under `content/pages/`, with workshop-level configuration in `content/workshop.yml`.

When changing workshop content:

- preserve the established filename ordering convention
- keep attendee material separate from instructor notes and solutions
- verify internal links, headings, code fences, images, and resource links
- use relative repository paths where supported
- test commands and code examples where practical
- avoid including real passwords, API tokens, account IDs, private URLs, or participant details

The current filenames use prefixes such as `01a`, `01b`, and `02z`. Follow the existing convention unless a wider reordering has been agreed. Treat files with instructor-oriented names or suffixes as non-attendee material and confirm that the application does not expose them unintentionally.

### Workshop resources and examples

Only place a file under `resources/` if it is intended to be available to workshop users.

Before adding a resource, confirm that it:

- contains no credentials, private keys, tokens, or personal data
- contains no generated infrastructure state
- is suitable for public or attendee access
- has a clear filename and purpose
- includes its own README when it is a multi-file example
- uses pinned or constrained dependencies where reproducibility matters

Example applications should be self-contained and should not import code from `src/earl_workshop/` unless that dependency is deliberate and documented.

## Testing

Run the complete test suite before submitting a pull request:

```bash
uv run pytest
```

Run a specific test module while developing:

```bash
uv run pytest tests/test_course.py
```

Run a specific test by name:

```bash
uv run pytest tests/test_course.py -k <test-name>
```

Browser checks live under `tests/browser/`. Check their prerequisites before running them, because they may require the application to be running and may require a browser automation dependency.

A contribution should normally include tests when it:

- fixes a bug
- adds or changes application behaviour
- changes authentication or session handling
- changes course navigation or progress tracking
- changes configuration parsing
- changes an infrastructure template that can be validated automatically

Documentation-only and prose-only content changes may not require automated tests, but links, code samples, and page rendering should still be checked.

## Code quality

Use the formatting, linting, and type-checking tools configured in `pyproject.toml`. Do not introduce a new overlapping tool without discussing the change first.

Typical commands may include:

```bash
uv run ruff check .
uv run ruff format --check .
```

For shell scripts, use defensive defaults where compatible with the script:

```bash
set -euo pipefail
```

Infrastructure shell changes should pass syntax checking:

```bash
bash -n path/to/script.sh
```

## Infrastructure changes

Infrastructure automation can create chargeable resources, modify DNS, expose services, and destroy workshop environments. Review these changes more carefully than ordinary application changes.

Place new infrastructure code under a top-level structure:

```text
infrastructure/
    ├── config/
    ├── image/
    ├── participants/
    └── portal/
```

When changing infrastructure:

- document prerequisites and required permissions
- provide `.example` files for configuration
- keep generated configuration and state outside tracked directories
- make destructive commands explicit
- add a confirmation or dry-run mechanism where practical
- make repeated execution safe where practical
- quote shell variables
- fail clearly when a required variable or command is missing
- avoid printing secrets to standard output or logs
- document created resources and generated output files
- include validation and cleanup instructions
- test against a temporary or non-production environment

Do not run provisioning or teardown commands against a shared workshop environment unless you are authorised to do so.

### Infrastructure pull request notes

An infrastructure pull request should state:

- which resources may be created, changed, or destroyed
- whether the change affects costs
- whether DNS, certificates, images, firewalls, or SSH access are affected
- how the change was validated
- how to roll back or recover from failure
- whether existing environments require migration

## Security and secrets

Never commit:

- private SSH keys
- cloud API tokens
- live `.env` files
- participant passwords or access manifests
- database files containing participant or administrator data
- generated cloud-init containing secrets
- certificate private keys
- provider state or output containing credentials

Commit example configuration instead:

```text
workshop.env.example
portal.env.example
```

Use obvious placeholders:

```dotenv
CERTBOT_EMAIL=_REPLACE_WITH_REAL_EMAIL_
WORKSHOP_DOMAIN=workshop.example.org
```

Generated secrets and deployment output should be written to an ignored local directory, e.g. `.paticipant-config/`, and should use restrictive file permissions.

Before committing, inspect the staged changes:

```bash
git diff --cached
```

Also check that sensitive files are not tracked:

```bash
git status --short
```

If a secret is committed, removing it in a later commit is not sufficient. Stop using it, rotate or revoke it, and notify the project maintainer. Follow the process in `SECURITY.md`.

## Commits and pull requests

- Commits: Write short, descriptive commit subjects in the imperative mood using a ['conventional commits'](https://www.freecodecamp.org/news/how-to-write-better-git-commit-messages/) style.
- Pull requests: include a concise description of the problem and solution, the relevant issue (if one exists), the areas of the repository affected, testing and validation performed, screenshots for visible website changes, operational impact for infrastructure changes, known limitations or follow-up work. Reviewers may ask for a pull request to be split if it combines unrelated concerns.

## Documentation

Update documentation in the same pull request when changing:

- local setup
- environment variables
- CLI commands
- course authoring conventions
- public resources
- deployment procedures
- generated infrastructure outputs
- destructive operations
- security-sensitive behaviour

Prefer linking to one authoritative explanation rather than copying the same instructions into multiple files.

Use clear headings, short paragraphs, fenced code blocks with language identifiers, and descriptive link text. Commands should be safe to copy, and destructive commands should be preceded by an explicit warning.

## Questions

If the correct location or approach for a change is unclear, open an issue with:

- the problem you are trying to solve
- the affected users
- the proposed area of the repository
- any security or infrastructure implications

A short design discussion is preferable to introducing a new convention that conflicts with the rest of the repository.
