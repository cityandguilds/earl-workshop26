---
id: linux
title: "Why Linux for open source data software?"
slug: "linux"
order: 30
section: "Getting started"
section_order: 30
summary: "Understand why cloud VMs commonly run Linux and what a distribution provides."
level: "Beginner"
estimated_minutes: 5
---

## What you will learn

By the end of this page, you should be able to:

- distinguish Linux from a Linux distribution;
- explain why Linux is common on cloud servers;
- identify practical benefits for open source data tooling;
- recognise that Linux is a choice with trade-offs.

## Linux in one paragraph

**Linux** is the operating-system kernel at the centre of many server operating systems. A **Linux distribution** packages that kernel with command-line tools, libraries, an installer, a package manager, and security updates.

Examples include Ubuntu, Debian, Fedora, Rocky Linux, and openSUSE.

This workshop uses Ubuntu on the participant VMs.

## Why use Linux on a virtual machine?

### It fits the server model

Linux works well without a graphical desktop. A small server can be managed through SSH, configuration files, services, and automation. This reduces unnecessary software on a VM designed to run applications rather than act as a personal desktop.

### Open source tools are at home here

Many data and infrastructure tools are developed for, packaged for, or routinely deployed on Linux. Examples include:

- Python and R;
- PostgreSQL;
- Nginx;
- Git;
- Docker and other container tools;
- FastAPI and Shiny;
- Quarto.

This does not mean these tools only run on Linux. It means Linux provides a common deployment environment for them.

### Package management is built in

A package manager installs signed software packages and keeps track of their dependencies.

On Ubuntu, common commands include:

```bash
sudo apt update
apt search nginx
apt show nginx
sudo apt install nginx
```

Do not install or upgrade system packages during the workshop unless the instructions ask you to.

### It is scriptable and reproducible

Text-based configuration and shell commands are easy to record in scripts. The workshop image and cloud-init configuration can therefore build similar environments repeatedly.

### It supports remote administration

SSH provides an encrypted terminal connection. You can manage the VM from a laptop without needing a remote graphical desktop.

### Permissions separate users and services

Linux permissions help control who may read, change, or execute a file. Services can run as dedicated users so that a problem in one service does not automatically grant access to everything on the machine.

## What a distribution gives you

A distribution combines several layers:

```text
Applications: FastAPI, Shiny, PostgreSQL, Nginx
System tools: shell, package manager, systemd, SSH
Libraries: shared code used by applications
Linux kernel: processes, memory, filesystems, networking, devices
Cloud virtual hardware
```

Two distributions can both use Linux while differing in package versions, defaults, support policies, and administration commands.

## Services and systemd

On Ubuntu, many background applications are managed by `systemd`. A managed background application is often called a **service**.

Safe inspection commands include:

```bash
systemctl status nginx --no-pager
systemctl is-active nginx
journalctl -u nginx -n 30 --no-pager
```

Commands that start, stop, or restart services change the VM and normally require `sudo`.

## Benefits and trade-offs

### Benefits

- strong support for command-line automation;
- broad availability on cloud platforms;
- mature networking, permissions, and service management;
- a large open source ecosystem;
- consistent deployment targets for many web and data applications.

### Trade-offs

- beginners must learn the shell and filesystem layout;
- distributions differ in commands and package versions;
- permissions can be confusing at first;
- administration mistakes can affect the whole server;
- open source still requires maintenance, updates, testing, and support choices.

## Practical rule for the workshop

Work as the `student` user for normal tasks. Use `sudo` only when the exercise explicitly requires administrator privileges.

```bash
whoami
sudo -n whoami
```

The first command should identify your normal account. The second demonstrates administrator access without changing anything.

## Check your understanding

1. Is Ubuntu the same thing as the Linux kernel?
2. Why is a command-line server useful for automation?
3. What does a package manager do?
4. Why might a service run as its own user?
5. Name one benefit and one trade-off of Linux for a data-science VM.

## Key takeaway

Linux gives open source data software a practical, automatable server environment. A distribution such as Ubuntu turns the Linux kernel into a complete operating system with packages, security updates, tools, and service management.
