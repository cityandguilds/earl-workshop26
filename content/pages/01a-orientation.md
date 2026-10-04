---
id: orientation
title: "Welcome, intros and workshop overview"
slug: "orientation"
order: 10
section: "Getting started"
section_order: 10
summary: "Welcome and overview of workshop"
level: "Beginner"
estimated_minutes: 10
---

Welcome to the workshop. Today you will work through a small, connected data platform on your own Linux virtual machine, using one flights dataset across databases, applications, APIs, reports, and containers.

## Who are we?
80% of City & Guilds' Data Science team.

Stephen Price
Nela Morris
Alison Telford
Sam Anees-Hill

## Who are you?!
Skills audit

## What you will build

During the workshop, you will follow the same data through several layers:

```text
Flights data
    |
    v
PostgreSQL
    |
    +----> Shiny application
    |
    +----> FastAPI service
    |
    +----> Quarto report
    |
    +----> Docker and ShinyProxy
```

Nginx provides the public web entry point for the services running on the VM:

```text
Your browser
    |
    | HTTPS on port 443
    v
Nginx
    |
    +----> /shiny/  ----> Shiny Server
    +----> /api/    ----> FastAPI
    +----> /proxy/  ----> ShinyProxy
    +----> /reports/----> Static Quarto reports
```

The aim is not to master every tool in one session. Instead, you will see how familiar data skills fit into a complete deployment workflow.

## Workshop learning outcomes

By the end of the workshop, you should be able to:

- connect securely to a Linux virtual machine;
- navigate and inspect a Linux system from the command line;
- explain the purpose of cloud networking, firewalls, DNS, HTTPS, and reverse proxies;
- load and query data in PostgreSQL;
- connect to PostgreSQL from R;
- deploy an R Shiny application through open-source Shiny Server;
- run a FastAPI service under a dedicated service account;
- test API endpoints through Swagger UI and a local command-line client;
- create and publish a Quarto report;
- copy files securely between your computer and the VM;
- run a containerised application;
- access a container through ShinyProxy and Nginx.

## The workshop environment

Each participant receives a separate Ubuntu virtual machine with a unique hostname, SSH key, application credentials, and PostgreSQL password.

You will normally connect as the `student` account. This account has passwordless `sudo` access for workshop administration. Application services use separate identities where appropriate, including `shiny` for Shiny Server and `fastapi` for the FastAPI service.

Only three ports are publicly accessible:

| Port | Purpose |
|---|---|
| `22` | SSH administration and secure file transfer |
| `80` | HTTP and certificate validation |
| `443` | Public HTTPS access through Nginx |

PostgreSQL and the application servers listen only on the VM's loopback interface. Nginx receives public web requests and forwards them to the appropriate local service.

## Workshop programme

### Part 1: Infrastructure and Linux

You will begin by examining the platform that supports the rest of the workshop.

Topics include:

- cloud projects, virtual machines, private networks, tags, firewalls, snapshots, DNS, HTTPS, Nginx, and cloud-init;
- comparisons with equivalent concepts in Azure and AWS;
- why only SSH, HTTP, and HTTPS are public;
- why Linux distributions are commonly used for open-source data platforms;
- essential Unix and Linux commands for navigation, file operations, secure copying, permissions, processes, storage, and service monitoring.

You will connect using your supplied SSH key:

```bash
ssh -i dsi-01-ssh   student@dsi-01.earl.sjp-analytics.co.uk
```

Replace the key filename and hostname with the values provided to you.

You will also verify passwordless administrative access:

```bash
sudo -n whoami
```

Expected output:

```text
root
```

### Part 2: PostgreSQL

You will use PostgreSQL as the shared data layer for the remaining activities.

You will:

- explore schemas, tables, rows, primary keys, foreign keys, and views;
- connect to PostgreSQL from R;
- download tabular flights data to the VM;
- write data frames into the `flights` schema;
- use `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY`, and `JOIN`;
- create a reusable database view for later applications.

### Part 3: Shiny

You will deploy an R Shiny application using open-source Shiny Server.

You will:

- review the roles of a Shiny user interface and server function;
- clone a public GitHub repository;
- deploy `shinyFlights` below `/srv/shiny-server/shinyFlights`;
- connect the application to the PostgreSQL flights data;
- publish it through Nginx.

The deployed application will be available at a participant-specific URL such as:

```text
https://dsi-01.earl.sjp-analytics.co.uk/shiny/shinyFlights/
```

### Part 4: FastAPI

You will deploy a Python API that exposes read-only flights endpoints.

At the start of this section, the FastAPI service is disabled and stopped. Nginx is already configured to forward `/api/` requests to it, so the public API initially returns `502 Bad Gateway`.

You will:

- introduce FastAPI, Uvicorn, API endpoints, and validation;
- deploy the prepared application code;
- query PostgreSQL on `127.0.0.1:5432`;
- use credentials provisioned for the dedicated `fastapi` service account;
- enable and start `dsi-fastapi`;
- explore and call an endpoint through Swagger UI;
- send a request from your own computer using a system command-line library.

Swagger UI will be available at a participant-specific URL such as:

```text
https://dsi-01.earl.sjp-analytics.co.uk/api/docs
```

### Part 5: Quarto

You will turn the flights data into a reproducible HTML report.

You will:

- introduce Quarto documents and rendering;
- create a report containing narrative, R code, database queries, a table, and a chart;
- query PostgreSQL during rendering;
- render the report to a self-contained HTML file;
- publish the result through Nginx;
- retrieve the finished report on your own computer using SCP.

### Part 6: Docker and ShinyProxy

The final section introduces containerised deployment.

You will:

- explain images, containers, build files, ports, and isolation;
- build a container image;
- run an application in a container;
- understand how ShinyProxy starts and routes containerised applications;
- access the result through Nginx.

ShinyProxy will be available at a participant-specific URL such as:

```text
https://dsi-01.earl.sjp-analytics.co.uk/proxy/
```

## One dataset, several delivery methods

The workshop deliberately reuses the same flights data. This makes it easier to compare the role of each tool:

| Tool       | Role in the workshop                                  |
|------------|-------------------------------------------------------|
| PostgreSQL | Stores, organises, and queries the data               |
| Shiny      | Delivers an interactive R application                 |
| FastAPI    | Delivers data through HTTP API endpoints              |
| Quarto     | Produces a reproducible static report                 |
| Docker     | Packages an application with its runtime dependencies |
| ShinyProxy | Launches and routes containerised Shiny applications  |
| Nginx      | Provides the public HTTPS gateway                     |

## Working safely

During the workshop:

- do not display or commit passwords from `database.env`;
- use `sudo` only when a task requires administrative access;
- check commands before running them;
- keep application services bound to local interfaces unless instructed otherwise;
- use the supplied participant hostname and SSH key;
- stop and ask for help if your result differs significantly from the expected output.

## Before we begin

Confirm that you have:

- your participant number;
- your participant hostname;
- your private SSH key file;
- a terminal application;
- a modern web browser;
- access to the workshop materials.

Keep your participant hostname somewhere convenient. Most examples use participant `01`, so you will need to substitute your own number throughout the workshop.

## Key takeaway

This workshop follows a complete path from cloud infrastructure and Linux administration to stored data, interactive applications, APIs, reproducible reports, and containers. Each section adds another layer while reusing the same VM, network gateway, credentials model, and flights dataset.
