---
id: install-software
title: Install software, system libraries, etc.
slug: "install-software"
order: 50
section: Getting started
section_order: 50
summary: "Install software, system libraries and R packages on a Linux machine"
level: "Beginner"
estimated_minutes: 10
---

## What you will learn

By the end of this page, you should be able to:

- explain what a package manager does;
- update the list of available Ubuntu packages;
- search for and install software;
- distinguish system packages from R packages;
- recognise when an R package needs a system library;
- verify that an installation worked.

> **Workshop note:** Your virtual machine is already provisioned with the main workshop software. Only install additional software when an exercise requires it.

## Three kinds of installation

During the workshop, you may encounter three related but different types of software.

### Command-line applications

These are programs you can run from the terminal.

Examples include:

- Git;
- Nginx;
- PostgreSQL;
- `curl`;
- Quarto.

Ubuntu normally installs these using the `apt` package manager.

### System libraries

A system library contains code used by other programs.

For example, the R package `RPostgres` communicates with PostgreSQL using a PostgreSQL client library. On Ubuntu, its development files are supplied by the `libpq-dev` system package.

System-library package names often begin with `lib` and end with `-dev`.

### R packages

R packages add functions, data, documentation, and other features to R.

Examples include:

- `DBI`;
- `RPostgres`;
- `shiny`;
- `ggplot2`;
- `jsonlite`.

R packages are normally installed from inside R rather than directly with `apt`.

## Check the operating system

Before following installation instructions, check which Linux distribution and version you are using:

```bash
cat /etc/os-release
```

You can also inspect the machine architecture:

```bash
dpkg --print-architecture
```

Package names and installation commands can differ between Linux distributions.

## Understanding `apt`

Ubuntu uses the Advanced Packaging Tool, commonly called **APT**, to install and manage system packages. APT obtains packages from configured software repositories and keeps track of their dependencies.

A repository is a server that holds software packages and package information.

### Update the package index

Before installing a package, refresh the VM's local list of available packages:

```bash
sudo apt update
```

This does not normally upgrade installed software. It downloads current information about the packages available from the configured repositories.

### Why is `sudo` required?

Installing system software changes shared areas of the operating system. These changes require administrator privileges.

`sudo` runs the following command with elevated privileges:

```bash
sudo apt update
```

Before entering a command with `sudo`, check that you understand what it will change.

## Search for software

Search the available package descriptions:

```bash
apt search tree
```

Display additional information about a package:

```bash
apt show tree
```

Check whether a command is already installed:

```bash
command -v tree
```

If installed, this prints its location, such as:

```text
/usr/bin/tree
```

## Install a system package

Install the small `tree` utility:

```bash
sudo apt install tree
```

APT shows the packages it intends to install and asks for confirmation.

Test the installation:

```bash
tree --version
tree ~
```

You can install several packages in one command by separating their names with spaces.

```bash
sudo apt install tree jq
```

## Remove a package

Remove a package with:

```bash
sudo apt remove tree
```

Removing a package does not necessarily remove every dependency or configuration file associated with it.

> **Important**: Do not remove workshop software.

## System libraries and development packages

Some Python and R packages contain compiled code or connect to external software. Installing them may require:

- a compiler;
- header files;
- system libraries;
- a package ending in `-dev`.

For example:

```bash
sudo apt install libpq-dev
```

`libpq-dev` provides development files used when building software that communicates with PostgreSQL. The `RPostgres` package is one example of an R package that uses this client library on Linux.

Other common examples include:

```bash
sudo apt install libcurl4-openssl-dev
sudo apt install libssl-dev
sudo apt install libxml2-dev
```

Do not guess which libraries are needed. Read the package documentation and the complete installation error first.

## Install an R package

Start R from the terminal:

```bash
R
```

At the R prompt, install a package:

```r
install.packages(
  "jsonlite",
  repos = "https://cloud.r-project.org"
)
```

Load it:

```r
library(jsonlite)
```

Check its installed version:

```r
packageVersion("jsonlite")
```

Leave R:

```r
q()
```

When asked whether to save the workspace, choose the option appropriate to your exercise. You will usually answer `n`.

## Install several R packages

You can install several packages together:

```r
install.packages(
  c("DBI", "RPostgres", "shiny"),
  repos = "https://cloud.r-project.org"
)
```

Package names are case-sensitive. For example, `RPostgres` and `rpostgres` are not the same name.

## Install an R package without opening R

You can run an R expression directly from the Linux shell:

```bash
Rscript --vanilla -e \
  'install.packages("jsonlite", repos="https://cloud.r-project.org")'
```

This is useful in provisioning scripts because the command can be recorded and repeated.

## Where are R packages installed?

Inspect the active R library paths:

```bash
Rscript -e '.libPaths()'
```

A **library** is a directory containing installed R packages.

If a shared system library is writable only by an administrator, R may offer to create a personal package library inside your home directory. A personal library lets you install R packages without changing packages used by every account on the VM.

## R packages can have two types of dependencies

An R package may depend on:

1. other R packages;
2. external system software or libraries.

`install.packages()` can usually install other required R packages. It cannot always provide the underlying Ubuntu libraries.

A failed installation may therefore include messages such as:

```text
configuration failed
```

```text
library not found
```

```text
fatal error: example.h: No such file or directory
```

Read upward from the final error. The most useful explanation is often several lines earlier. Needless to say, LLMs can really help with trouble-shooting!

## A typical installation sequence

Suppose an R package requires the PostgreSQL client library.

First install the system dependency from the Linux shell:

```bash
sudo apt update
sudo apt install libpq-dev
```

Then install the R package:

```bash
Rscript --vanilla -e \
  'install.packages("RPostgres", repos="https://cloud.r-project.org")'
```

Finally, verify it:

```bash
Rscript --vanilla -e \
  'library(RPostgres); packageVersion("RPostgres")'
```

CRAN also recommends installing `r-base-dev` when users need to compile R packages from source on Ubuntu.

## Verify installations

Do not assume that an installation succeeded merely because the command finished.

For a command-line application:

```bash
command -v git
git --version
```

For an Ubuntu package:

```bash
dpkg -s git
```

For an R package:

```bash
Rscript --vanilla -e \
  'stopifnot(requireNamespace("jsonlite", quietly = TRUE))'
```

A successful verification command should exit without an error.

## System-wide installation versus project environments

System packages installed with `sudo apt install` affect the VM.

R packages may be installed into:

- a shared system library;
- your personal R library;
- a project-specific library managed by a tool such as `renv`.

For reproducible projects, record package requirements rather than relying only on packages that happen to be installed on one machine.

At minimum, keep:

- source code in version control;
- a clear installation guide;
- package names and versions where appropriate;
- required operating-system libraries;
- commands needed to recreate the environment.

## Good installation habits

### Read before using `sudo`

Administrator commands can affect every user and service on the VM.

### Prefer trusted repositories

Use the repositories prepared for the workshop. Do not add an unfamiliar repository or run an internet-hosted installation script without understanding and verifying it.

### Do not upgrade everything during the workshop

Avoid running this unless the workshop host explicitly instructs you:

```bash
sudo apt upgrade
```

A full upgrade can take time and may change package versions expected by the exercises.

### Record what you install

Add installation commands to the project documentation or provisioning scripts.

For example:

```text
System dependencies:
- libpq-dev
- libcurl4-openssl-dev

R packages:
- DBI
- RPostgres
- jsonlite
```

### Read error messages

Copy the complete error into a text file if necessary:

```bash
Rscript install-packages.R 2>&1 | tee installation.log
```

This displays the output and saves it to `installation.log`.

## Practice exercise

Check whether `tree` is installed:

```bash
command -v tree
```

If it is missing, install it:

```bash
sudo apt update
sudo apt install tree
```

Create a small directory structure:

```bash
mkdir -p ~/installation-practice/data
mkdir -p ~/installation-practice/output
touch ~/installation-practice/README.md
```

Display it:

```bash
tree ~/installation-practice
```

Install and test an R package:

```bash
Rscript --vanilla -e \
  'install.packages("jsonlite", repos="https://cloud.r-project.org")'

Rscript --vanilla -e \
  'library(jsonlite); cat(toJSON(list(status="ready")), "\n")'
```

Clean up the practice directory:

```bash
rm -r ~/installation-practice
```

The installed software and R package can remain available for later exercises.

## Troubleshooting checklist

If installation fails, check:

1. Are you connected to the internet?
2. Did `sudo apt update` succeed?
3. Is the package name spelled correctly?
4. Is the package available for this Ubuntu release?
5. Do you have enough disk space?

```bash
df -h
```

6. Does an R package require a missing system library?
7. Does the error mention a missing header file or external command?
8. Are you installing into a writable R library?

```bash
Rscript -e '.libPaths()'
```

9. Can the package or command be loaded after installation?
10. Did you preserve the complete error message?

## Check your understanding

1. What is the difference between `apt update` and `apt install`?
2. Why does installing system software usually require `sudo`?
3. What is a system library?
4. Why might installing an R package require an Ubuntu package ending in `-dev`?
5. How would you check whether `git` is installed?
6. How would you verify that the R package `jsonlite` can be loaded?
7. Why should installation commands be recorded in project documentation?

## Key takeaway

Installing data software often involves more than one layer. Use APT for Ubuntu applications and system libraries, use R's package tools for R packages, verify each installation, and record the dependencies needed to recreate the project.
