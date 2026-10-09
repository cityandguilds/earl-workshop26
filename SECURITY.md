# Security Policy

Security is important to the DSI Workshop project because the repository contains a web application, authentication and participant-progress features, workshop content, and automation that creates internet-accessible cloud infrastructure.

This document explains how to report a vulnerability and describes the project's security expectations. It is not a guarantee that the software is suitable for handling sensitive, regulated, or production data.

## Reporting a vulnerability

**Do not report a suspected security vulnerability in a public issue, discussion, pull request, workshop chat, or course page.**

Report it privately by email to **sjamesprice@gmail.com** with the subject `Security report: DSI Workshop`.

### Information to include

Provide as much of the following as is practical:

- a concise description of the issue
- the affected component, file, route, command, or deployment workflow
- the affected branch, tag, release, or commit
- the configuration required to reproduce it
- step-by-step reproduction instructions
- a minimal proof of concept, if safe to share
- the observed and expected behaviour
- the potential impact
- whether the issue may affect an active workshop or deployed environment
- any suggested mitigation or remediation
- your preferred name and contact details for follow-up

Do not include real participant credentials, cloud tokens, private keys, database contents, or other unnecessary sensitive data. Redact secrets and use synthetic examples wherever possible.

## What to expect after reporting

The maintainers will aim to acknowledge receipt quickly then patch and communicate the update.

A report may be closed if it cannot be reproduced, is outside the project's scope, or does not create a meaningful security risk. The maintainers will explain the decision where it is safe and practical to do so.

## Secrets and sensitive files

The following must never be committed to the repository:

- private SSH keys
- cloud API tokens
- certificate private keys
- live `.env` files
- generated cloud-init files containing secrets
- participant usernames, passwords, or access manifests
- attendee personal data
- production or workshop databases
- provider state and command output containing credentials

Only sanitised example configuration should be tracked, using obvious placeholders such as:

```dotenv
CLOUD_API_TOKEN=_REPLACE_ME_
WORKSHOP_DOMAIN=workshop.example.org
```

Generated secrets and deployment outputs should be stored in an ignored local directory, such as `.participant-config/`, with restrictive file permissions. Public keys are not secrets, but generated key pairs should normally remain deployment artefacts rather than repository content.

### If a secret is exposed

Removing a secret from the latest commit is not sufficient. Treat an exposed secret as compromised.

1. Stop using the credential.
2. Revoke or rotate it at the issuing service.
3. Check relevant audit logs and deployed systems for unexpected use.
4. Remove the secret from the working tree and prevent it from being republished.
5. Assess whether repository history, releases, build artefacts, logs, or caches also contain it.
6. Notify affected maintainers or users through a private channel.
7. Document the incident and the actions taken without reproducing the secret.

History rewriting may reduce accidental discovery, but it does not replace revocation or rotation.

## Participant and administrator data

Collect and retain only the information required to run the workshop.

- Do not use real participant data in development fixtures, screenshots, logs, or bug reports.
- Do not display passwords or access tokens after they are no longer operationally required.
- Do not expose administrator-only data through attendee routes or downloadable resources.
- Protect database files, generated credential manifests, and exports with restrictive permissions.
- Remove workshop credentials and personal data when they are no longer required, subject to any applicable organisational policy.
- Use synthetic data when demonstrating or testing administration features.

The repository should document what participant data is collected, where it is stored, who can access it, and how it is removed after a workshop.

## Application security expectations

Contributors should:

- use the central configuration system rather than scattering environment-variable reads
- validate untrusted input at application boundaries
- apply authentication and authorisation checks on the server
- avoid placing secrets or privileged decisions in browser-side code
- escape rendered content by default
- review any deliberate use of unescaped HTML
- use parameterised database operations
- use secure session and cookie settings in deployed environments
- avoid logging passwords, tokens, session identifiers, or sensitive participant data
- fail closed when authentication or configuration is invalid
- add regression tests for security fixes where it is safe to do so

Changes to authentication, session handling, administrator routes, Markdown rendering, file serving, or credential generation require focused security review.

## Infrastructure security expectations

Infrastructure automation may create chargeable and publicly accessible resources. Contributors should:

- use least-privilege cloud credentials
- require explicit configuration for public exposure
- limit firewall rules to necessary ports and sources
- avoid storing secrets in command history, process arguments, or logs
- quote shell variables and validate externally supplied values
- make destructive operations explicit and difficult to invoke accidentally
- provide validation and teardown procedures
- write generated sensitive files with restrictive permissions
- avoid reusing participant credentials or SSH key pairs across workshops
- test changes in an isolated, non-production environment
- document created services, DNS records, images, volumes, firewalls, and other resources

Do not run provisioning, migration, or teardown commands against a shared environment without authorisation.

## Dependencies and supply chain

The project should retain reproducible dependency information in `pyproject.toml` and `uv.lock`.

When changing dependencies:

- review why the dependency is needed
- prefer maintained packages from their canonical distribution source
- review dependency changes in the lock file
- avoid unpinned remote scripts in provisioning workflows
- verify downloaded artefacts where the publisher provides a supported verification mechanism
- remove dependencies that are no longer used
- assess security advisories that affect code paths exercised by the project

Automated dependency or security alerts should be reviewed, but an alert does not by itself establish that this project is exploitable.

## Logging and diagnostics

Logs should support diagnosis without becoming a secondary store of secrets or personal data.

Do not log:

- passwords or password hashes
- API tokens
- complete session cookies or authorisation headers
- private keys
- full participant credential manifests
- unnecessary request bodies containing personal data

Sanitise diagnostic output before attaching it to an issue or sending it to another person.

## Maintainer incident response

For a credible report or suspected compromise, maintainers should:

1. preserve the report in a private channel
2. identify affected code, credentials, data, and deployed environments
3. contain immediate risk, including disabling access or rotating credentials where required
4. preserve useful logs without broadly distributing sensitive data
5. develop and test a remediation
6. notify affected operators or participants when appropriate
7. publish an advisory or release when disclosure is warranted
8. record follow-up actions that reduce the likelihood or impact of recurrence

## Policy maintenance

Review this policy when:

- the reporting contact changes
- the project introduces releases or support branches
- authentication or participant-data handling changes
- infrastructure providers or deployment architecture change
- a security incident reveals a missing or unclear procedure
