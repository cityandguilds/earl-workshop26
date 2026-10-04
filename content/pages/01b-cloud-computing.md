---
id: cloud-computing
title: "Cloud computing for this workshop"
slug: "cloud-computing"
order: 20
section: "Getting started"
section_order: 20
summary: "Meet the cloud services that make your workshop VM reachable, secure, and reproducible."
level: "Beginner"
estimated_minutes: 15
---

## What you will learn

By the end of this page, you should be able to:

- describe what a virtual machine is;
- explain how traffic reaches your workshop VM;
- recognise the main DigitalOcean resources used in the workshop;
- match them to broadly similar Azure and AWS services;
- explain why only ports 22, 80, and 443 are public.

> **Beginner note:** You do not need to memorise every product name. Focus on the job each component performs.

## The big picture

Your workshop environment is a computer running in a cloud data centre. You connect to it over the internet.

```text
Your laptop
    |
    | SSH on port 22, or HTTPS on port 443
    v
Cloud Firewall
    |
    v
Workshop virtual machine
    |
    +-- Nginx, public gateway
    +-- FastAPI, local only
    +-- Shiny Server, local only
    +-- code-server, local only
    +-- PostgreSQL, local only
```

The cloud provider supplies the physical data centre, networking, and virtualisation. We configure the operating system and applications.

## DigitalOcean building blocks

### Project

A **Project** groups related cloud resources. In this workshop, the participant VMs, networking resources, and domain records belong to one organised workshop environment.

Think of a Project as a labelled workspace, not as a network boundary.

### VPC

A **Virtual Private Cloud**, or **VPC**, is a private network for cloud resources. Machines in the same VPC can communicate using private addresses without exposing that traffic directly to the public internet.

### Tags

A **tag** is a label attached to a resource, such as `workshop` or `participant`. Tags help us find groups of resources and apply shared configuration, including firewall rules.

### Cloud Firewall

A **Cloud Firewall** controls which network traffic may enter or leave a VM. Our default approach is simple:

1. allow only the public traffic required for the workshop;
2. deny unsolicited traffic to all other ports;
3. keep application services behind Nginx.

### Droplet

A **Droplet** is DigitalOcean's name for a virtual machine. Each participant receives a Droplet with Linux, workshop software, a public address, and a private VPC address.

### Snapshot

A **snapshot** is a reusable image of a VM disk. The workshop host prepares one tested "golden image", then creates participant VMs from it. This makes the starting environments consistent.

A snapshot is useful, but it is not a complete substitute for backups or source control.

### DNS

**Domain Name System**, or **DNS**, turns a readable hostname into an IP address.

```text
dsi-01.earl.sjp-analytics.co.uk  ->  203.0.113.10
```

The browser asks DNS where the hostname lives, then connects to the returned address.

### Nginx

**Nginx** is the public web gateway on each VM. It can serve static files and act as a **reverse proxy**, forwarding requests to local applications.

```text
/          -> landing page
/api/      -> FastAPI
/shiny/    -> Shiny Server
/code/     -> code-server
/proxy/    -> ShinyProxy
```

The browser only needs one public hostname. Internal applications can listen on local addresses such as `127.0.0.1:8000`.

### HTTPS

**HTTPS** is HTTP protected by TLS encryption. A TLS certificate connects the hostname to the server and allows the browser and server to establish an encrypted connection.

Typical flow:

1. DNS resolves the hostname.
2. The browser connects to port 443.
3. Nginx presents the TLS certificate.
4. The browser checks the certificate.
5. Encrypted HTTP requests pass between the browser and Nginx.
6. Nginx forwards each request to the appropriate local service.

Port 80 remains available so plain HTTP can be redirected to HTTPS and, where configured, certificate validation can take place.

### cloud-init

**cloud-init** applies first-boot configuration to a new VM. In this workshop it completes participant-specific work such as adding an SSH key, writing configuration, creating credentials, and starting services.

The snapshot supplies the common starting point. cloud-init supplies the settings unique to each participant VM.

## DigitalOcean, Azure, and AWS comparison

These are learning analogies, not claims that every service behaves identically.

| Purpose                    | DigitalOcean     | Microsoft Azure               | Amazon Web Services                          |
|----------------------------|------------------|-------------------------------|----------------------------------------------|
| Organise related resources | Project          | Resource group                | Resource tags/accounts/CloudFormation stacks |
| Virtual machine            | Droplet          | Azure Virtual Machine         | Amazon EC2 instance                          |
| Private network            | VPC              | Virtual Network, or VNet      | Virtual Private Cloud                        |
| Network access rules       | Cloud Firewall   | Network Security Group        | Security Group                               |
| Reusable machine image     | Snapshot         | Managed/Compute Gallery image | Amazon Machine Image                         |
| DNS hosting                | DigitalOcean DNS | Azure DNS                     | Amazon Route 53                              |
| Resource labels            | Tags             | Tags                          | Tags                                         |

The general pattern is portable: compute, private networking, traffic rules, images, DNS, and automated configuration exist across the major providers.

## Why only ports 22, 80, and 443 are public

A **port** identifies a network service on a machine.

| Port | Public purpose                                                                 |
|-----:|--------------------------------------------------------------------------------|
| 22   | SSH administration and participant terminal access                             |
| 80   | HTTP, normally redirected to HTTPS, plus certificate validation where required |
| 443  | Encrypted HTTPS access to the landing page and proxied applications            |

Application ports such as 3838, 5432, 8000, and 8080 are not public. They listen on the VM's loopback interface and are reached through Nginx where appropriate.

Benefits include:

- a smaller public attack surface;
- one HTTPS entry point;
- central request logging and routing;
- no need to expose database or development-service ports;
- simpler URLs for participants.

> **Important:** A closed public port does not make an application automatically secure. Authentication, updates, permissions, secrets handling, and application security still matter.

## Read a small Nginx example

```nginx
server {
    listen 80;
    server_name workshop.earl.sjp-analytics.co.uk;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name workshop.earl.sjp-analytics.co.uk;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

What it means:

- Nginx receives public HTTP and HTTPS traffic.
- HTTP is redirected to HTTPS.
- requests under `/api/` are sent to FastAPI on local port 8000;
- FastAPI does not need a public listening port.

## Try it: SSH
SSH, or Secure Shell, lets you open an encrypted command-line session on another computer, such as your workshop virtual machine.

```text
Your laptop  -- encrypted SSH connection -->  Workshop VM
```

TODO: make keys/credentials available for download

Open a terminal app.

```bash
ssh -i dsi-01-ssh student@dsi-01.earl.sjp-analytics.co.uk
```

Run these commands on your workshop VM:

```bash
hostname
ip address
sudo ss -lntp # Shows listening TCP ports and their owning processes
sudo nginx -t
curl -I http://localhost/healthz
```

Before using `sudo`, read the command and make sure you understand what it does.

```bash
man sudo
```

To close your secure shell and return to your local terminal, run the `exit` command.

## Check your understanding

1. What is the difference between a Droplet and a snapshot?
2. Which component maps a hostname to an IP address?
3. Why can FastAPI remain on `127.0.0.1:8000`?
4. What does the Cloud Firewall do that Nginx does not?
5. Which Azure and AWS services are broadly comparable to a DigitalOcean VPC?

## Key takeaway

The VM is not exposed as a collection of unrelated services. The firewall permits a small set of public ports, DNS directs users to the VM, HTTPS protects browser traffic, and Nginx routes web requests to local applications.
