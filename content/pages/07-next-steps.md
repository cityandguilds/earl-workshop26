---
id: next-steps
title: Next steps
slug: "next-steps"
order: 600
section: Next steps
section_order: 600
summary: "Continue exploring the workshop repository, infrastructure, applications, and cloud deployment"
level: "Beginner"
estimated_minutes: 10
---

You have followed one flights dataset from a cloud virtual machine into PostgreSQL, Shiny, FastAPI, Quarto, Docker, and ShinyProxy. The next step is to repeat selected parts independently, change them, and make the environment your own.

## Keep the repository

If the workshop repository was useful, star it on GitHub so that you can find it again. You can also fork it if you want your own copy for experiments and changes.

A useful first review is to compare:

- the participant-facing lesson pages;
- the instructor notes;
- the application source code;
- the `resources/` folder with the scripts and templates used to create the workshop infrastructure.

## Explore the `resources/` folder

The `resources/` folder shows how the workshop environment was assembled rather than only how it was used.

Focus on these responsibilities:

```text
bootstrap.sh
  prepares reusable software and services for the golden image

cloud-init.template.yml
  applies participant-specific configuration at VM creation

provisioning scripts
  create cloud resources, participant machines, DNS records, and credentials

workshop configuration (gitignored)
  supplies names, regions, sizes, domains, tags, and other deployment settings
```

Trace one requirement through the files. For example:

1. Find where Docker is installed.
2. Find where the `student` and `fastapi` accounts are created.
3. Find where PostgreSQL is restricted to the loopback interface.
4. Find where participant database credentials are generated.
5. Find where Nginx routes `/shiny/`, `/api/`, `/reports/`, and `/proxy/`.
6. Find where services are enabled, started, and tested.

This is a practical introduction to infrastructure as code: configuration and repeatable scripts describe how an environment should be built.

## Rebuild a small version of the platform

Do not begin by reproducing the full workshop. Start with a single small Linux VM and add one layer at a time:

1. Create an SSH key specifically for the experiment.
2. Create one Ubuntu VM.
3. Restrict inbound traffic with cloud firewall rules.
4. Connect over SSH using a non-root account.
5. Install Nginx and publish a static page.
6. Add PostgreSQL bound to `127.0.0.1`.
7. Deploy one application behind Nginx.
8. Add HTTPS only after DNS points to the VM.
9. Rebuild the VM from a script or cloud-init file.
10. Delete the resources when the experiment is complete.

Keep notes about every manual step. A good automation exercise is to rebuild those steps in `bootstrap.sh`, cloud-init, or your provider's infrastructure-as-code tooling.

## Try DigitalOcean

Create a DigitalOcean account and explore the concepts used in the workshop:

- Projects;
- Droplets;
- VPCs;
- Cloud Firewalls;
- SSH keys;
- tags;
- snapshots;
- DNS records;
- monitoring.

DigitalOcean provides an account registration page, but offers and eligibility can change, so review the current signup and billing terms before creating resources.

A sensible first experiment is one small Droplet with SSH restricted to your own public IP address and only ports `80` and `443` open to web traffic.

## Try Microsoft Azure

You can reproduce the same broad architecture with Azure services:

| Workshop concept | Azure direction to explore |
|---|---|
| Project grouping | Resource group |
| Virtual machine | Azure Virtual Machines |
| Private cloud network | Virtual network |
| Cloud firewall rules | Network security group |
| Public address | Public IP resource |
| DNS | Azure DNS |
| Golden image | Managed image or Azure Compute Gallery |
| Startup configuration | cloud-init on a Linux VM |

Microsoft currently describes its Azure free account as including credit for new customers, selected free service allowances, and spending protection during the free-account period. Check the current eligibility and terms before deployment. One problem you might face with Azure is a lack of availability for small, cheap virtual machines in most or all regions.

Keep the first Azure exercise small: one resource group, one virtual network, one subnet, one network security group, one public IP, and one Linux VM.

## Control cost before experimenting

Cloud resources may continue to incur charges while they exist, even when you are not actively using them.

Before starting:

- read the provider's current pricing and free-account terms;
- use the smallest suitable VM size;
- avoid creating resources you do not understand;
- set a budget or billing alert where available;
- record every resource you create;
- stop resources when appropriate;
- delete the full experiment when finished;
- verify that disks, snapshots, public IPs, DNS zones, registries, and other dependent resources are also removed when no longer needed.

Treat free credit as a spending limit to manage, not as a reason to leave infrastructure running!

## Improve the infrastructure

Once you can reproduce the basic VM, choose one improvement at a time.

### Security

- remove direct root SSH access;
- restrict SSH to known source addresses;
- rotate participant credentials;
- separate service identities;
- move secrets into an appropriate secret store;
- automate operating-system security updates;
- add backup and restore testing;
- inspect logs for failed access attempts.

### Reliability

- make scripts safe to run more than once (idempotent);
- add explicit readiness checks;
- verify service configuration before restarting;
- capture useful failure logs;
- pin downloaded artifact versions and verify checksums;
- test rebuilding from a clean VM;
- document recovery procedures.

### Automation

- move hard-coded values into configuration;
- validate required variables before provisioning;
- generate DNS and hostnames consistently;
- run syntax and configuration checks in continuous integration;
- create a disposable test deployment;
- destroy test infrastructure automatically after validation.

### Observability

- monitor disk, memory, CPU, and service health;
- collect application and reverse-proxy logs;
- add health endpoints;
- alert on repeated service failures;
- measure container startup and request times.

## Extend the data applications

You can continue without changing the infrastructure immediately.

### PostgreSQL

- add indexes and compare query plans;
- introduce migrations;
- create read-only application roles;
- add data-quality checks;
- schedule a repeatable data import;
- practise backup and restore.

### Shiny

- add filtering and visualisations;
- use `renv` for dependency management;
- add tests with `shinytest2` or a generic tool like 'cypress';
- improve accessibility and error handling;
- compare direct Shiny Server deployment with a containerised version.

### FastAPI

- add response models and validation;
- introduce automated tests;
- add pagination and structured errors;
- use connection pooling;
- generate client code from the OpenAPI document;
- protect selected endpoints with authentication.

### Quarto

- turn the report into a multi-page website;
- parameterise the report for different airports;
- add scheduled rendering;
- publish through a continuous integration workflow;
- add citations, cross-references, and reusable styling.

### Docker and ShinyProxy

- reduce image size;
- pin base-image and package versions;
- run containers with reduced privileges;
- add container health checks;
- publish images to a private registry;
- explore authentication and access groups in ShinyProxy;
- test application-container recovery.

## Use GitHub as a learning record

Create a fork or a separate repository for your experiments. GitHub's free plan includes public and private repositories.

Use branches for focused changes such as:

```text
feat/azure-cloud-init
feat/read-only-database-role
feat/fastapi-tests
feat/quarto-website
feat/shinyproxy-authentication
```

For each experiment, record:

- the problem you were trying to solve;
- the infrastructure or application change;
- how you tested it;
- what failed;
- how to remove or reverse it;
- any remaining security or production concerns.

Good documentation is part of the deployment, not an afterthought.

## A suggested practice project

Rebuild a smaller end-to-end version using a dataset of your choice:

```text
Cloud VM
  -> PostgreSQL
  -> one data import
  -> one Shiny app or FastAPI service
  -> Nginx and HTTPS
  -> one Quarto report
  -> automated rebuild instructions
```

Success means another person can follow your repository, create the environment, test it, and remove it without needing undocumented steps.

## Before using this in production

The workshop environment is designed for learning. A production service needs additional review covering:

- organisational cloud approval and ownership;
- identity and access management;
- data classification and privacy;
- network architecture;
- secret storage and rotation;
- patching and vulnerability management;
- backups and disaster recovery;
- monitoring and alerting;
- capacity and cost management;
- support and incident response;
- testing, change control, and rollback.

Involve your technology, security, data governance, and service-management teams before publishing organisational data or services.

## Personal next-step checklist

Choose a manageable sequence:

- [ ] Star or fork the workshop repository.
- [ ] Read the `resources/` folder from start to finish.
- [ ] Draw the provisioning sequence in your own words.
- [ ] Create one disposable Linux VM.
- [ ] Apply restrictive firewall rules.
- [ ] Publish a static page through Nginx.
- [ ] Recreate the VM with cloud-init.
- [ ] Deploy one workshop application.
- [ ] Add one automated test.
- [ ] Document and delete the environment.

## Key takeaway

The applications were only one part of the workshop. The deeper learning opportunity is the repeatable system around them: cloud resources, Linux accounts, network boundaries, service configuration, credentials, readiness checks, deployment, monitoring, and clean teardown. Start small, automate what you understand, and keep security and cost visible throughout the experiment.
