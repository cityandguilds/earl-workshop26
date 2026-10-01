---
id: shiny-server-introduction
title: Introduction to Shiny Server
slug: "shiny-server-introduction"
order: 200
section: Shiny
section_order: 200
summary: "Understand what open source Shiny Server is, how it runs Shiny applications, and when to use it"
level: "Beginner"
estimated_minutes: 15
---

# Introduction to Shiny Server

## What you will learn

By the end of this page, you should be able to:

- explain the difference between Shiny and Shiny Server;
- describe how Shiny Server publishes an application;
- identify its main files, directories, service, and port;
- outline how it is installed on Linux;
- position it alongside other Shiny publishing options;
- describe its main advantages and disadvantages.

## Shiny and Shiny Server are different things

**Shiny** is a framework for building interactive web applications with R or Python. The application defines its interface and server-side behaviour.

**Shiny Server** is separate publishing software. It runs on a server, starts application processes when required, and makes Shiny applications available through web addresses.

```text
Shiny
  builds the application

Shiny Server
  hosts and manages the application
```

Running this command is useful while developing an app:

```r
shiny::runApp()
```

However, the command remains attached to that terminal session. Shiny Server provides a persistent service intended to host applications for visitors.

## What is open source Shiny Server?

Open source Shiny Server is self-hosted software from Posit. It can host multiple Shiny applications on one Linux server, with each application available through its own URL. It is free and open source under the AGPLv3 licence.

A default installation listens on port `3838`, although its behaviour can be changed in the configuration file.

In this workshop, Shiny Server is not directly exposed to the internet. It listens on the VM's loopback address:

```text
127.0.0.1:3838
```

Nginx receives the public HTTPS request and passes it to Shiny Server.

## How it works

The simplified request path is:

```text
Browser
   |
   | HTTPS on public port 443
   v
Nginx reverse proxy
   |
   | HTTP on 127.0.0.1:3838
   v
Shiny Server
   |
   | starts and manages an application process
   v
Shiny application
   |
   | optional local database connection
   v
PostgreSQL
```

When a visitor opens an application:

1. the browser sends a request to Nginx;
2. Nginx forwards the `/shiny/` request to Shiny Server;
3. Shiny Server identifies the application from the URL;
4. it starts or connects the visitor to an application process;
5. the application runs its R code and produces the interface;
6. browser inputs and application outputs continue to pass through Shiny Server and Nginx.

Shiny Server can host several applications at separate URLs and can restart an application process after a crash or termination when a later request arrives.

## Application directories and URLs

Our Shiny Server configuration publishes a directory of applications:

```text
/srv/shiny-server/
```

Each subdirectory represents an application:

```text
/srv/shiny-server/
├── shinyFlights/
│   ├── app.R
│   └── www/
│       └── styles.css
└── anotherApp/
    └── app.R
```

Shiny Server maps the directory name to part of the URL:

```text
Directory: /srv/shiny-server/shinyFlights
Local URL: http://127.0.0.1:3838/shinyFlights/
Public URL: https://ds01-earl.sjp-analytics.co.uk/shiny/shinyFlights/
```

The additional public `/shiny/` prefix belongs to the Nginx reverse-proxy configuration.

## The service account

Shiny Server normally runs application code as a dedicated operating-system user, such as `shiny`.

This is important because the application process must be able to:

- read the deployed application files;
- load the required R packages;
- read permitted configuration files;
- connect to required data sources;
- write only to locations where writing is genuinely required.

A project that works for the `student` account may still fail after deployment if the `shiny` account cannot read its files or configuration.

Do not solve permission problems by making everything writable by everyone. Grant only the access the service needs.

## Important locations

The exact paths can vary with installation and configuration, but this workshop uses:

| Purpose                              | Workshop location                     |
|--------------------------------------|---------------------------------------|
| Application directory                | `/srv/shiny-server/`                  |
| Main configuration                   | `/etc/shiny-server/shiny-server.conf` |
| Application logs                     | `/var/log/shiny-server/`              |
| Installed server files               | `/opt/shiny-server/`                  |
| Database settings for `shinyFlights` | `/etc/shiny-server/shinyFlights.env`  |

Inspect them with:

```bash
sudo cat /etc/shiny-server/shiny-server.conf
sudo find /srv/shiny-server -maxdepth 2 -type f
sudo find /var/log/shiny-server -maxdepth 1 -type f
```

Do not display files containing passwords or other secrets.

## A small configuration example

```text
run_as shiny;

server {
  listen 3838 127.0.0.1;

  location / {
    site_dir /srv/shiny-server;
    log_dir /var/log/shiny-server;
    directory_index on;
  }
}
```

This means:

- applications run as the `shiny` Linux user;
- Shiny Server accepts local connections on port `3838`;
- application directories are found below `/srv/shiny-server`;
- logs are written below `/var/log/shiny-server`;
- the application directory can be listed when appropriate.

## How Shiny Server is installed

Shiny Server is not installed from inside an R session. It is Linux server software installed by an administrator.

The broad installation sequence is:

1. install a supported Linux operating system;
2. install R;
3. install the `shiny` R package and the packages required by the apps;
4. download the appropriate Shiny Server installer;
5. install the operating-system package as an administrator;
6. configure Shiny Server;
7. deploy an application;
8. start the service and test it.

For example, Posit's Ubuntu instructions use a downloaded `.deb` package. The installer places Shiny Server under `/opt/shiny-server/` and creates a `shiny` user. R and the Shiny R package are separate prerequisites and are not included by the Shiny Server installer.

Our workshop image pins and installs a tested version during image creation, so participants do not repeat the server installation.

## Managing the service

On an Ubuntu system using `systemd`, inspect the service with:

```bash
systemctl status shiny-server --no-pager
systemctl is-active shiny-server
```

After changing an application or configuration, an administrator may restart it:

```bash
sudo systemctl restart shiny-server
```

Inspect recent service messages:

```bash
sudo journalctl -u shiny-server -n 50 --no-pager
```

Inspect application-specific logs:

```bash
sudo find /var/log/shiny-server -maxdepth 1 -type f -print
sudo tail -n 80 /var/log/shiny-server/example-app.log
```

The real filename depends on the application and server configuration.

## Where are the official docs?

Use these starting points:

- [Shiny Server documentation](https://docs.posit.co/shiny-server/)
- [Open source Shiny Server product page](https://posit.co/products/open-source/shiny-server)
- [Shiny hosting and deployment options](https://shiny.posit.co/r/deploy.html)
- [Shiny Server source repository](https://github.com/rstudio/shiny-server)
- [Shiny Server release notes](https://docs.posit.co/shiny-server/NEWS.txt)

The administrator guide covers installation, configuration, application hosting, service management, logs, proxy servers, and related operational topics.

## Position among Shiny publishing options

There is no single best publishing method for every project.

### Open source Shiny Server

Use this when you want a free, self-hosted way to publish one or more Shiny applications on a Linux server and you are prepared to manage that server.

### shinyapps.io

`shinyapps.io` is hosted by Posit. Posit operates the hosting environment, so publishers do not need to own and administer a server.

### Posit Connect

Posit Connect is Posit's commercial self-hosted publishing platform. It supports a broader range of R and Python content and includes publishing, access-control, management, scheduling, and operational features beyond open source Shiny Server.

### Posit Connect Cloud

Posit Connect Cloud is a hosted publishing option that can deploy supported data applications and other content from GitHub.

### Containers and general cloud platforms

Shiny applications can also be packaged in containers and deployed through general infrastructure platforms. This offers flexibility but requires additional knowledge about images, networking, orchestration, monitoring, and secrets.

## Advantages

- Free and open source: The software can be used without purchasing a licence, and its source code is publicly available.
- Self-hosted: The organisation controls the VM, operating system, network, application files, and local data connections.
- Simple directory-based deployment: For a basic setup, deploying an application can be as simple as placing a readable app directory below `/srv/shiny-server`.
- Multiple applications: One server can publish several Shiny apps, each at a different URL.
- Useful for learning infrastructure: It exposes the real boundaries between application code, Linux permissions, services, ports, reverse proxies, logs, and databases.
- Works behind a firewall: Posit presents open source Shiny Server as an option for self-hosted or VPC deployment, including deployment behind firewalls.

## Disadvantages and limitations

- You manage the server: Your organisation is responsible for Linux administration, updates, backups, HTTPS, firewall rules, monitoring, application dependencies, logs, and incident response.
- No built-in end-user authentication: if an application must be limited to approved users, access control must be provided by another suitable layer. Placing the whole infrastructure behind your organisation's VPN is useful as is the {shinymanager} R package.
- No built-in SSL termination: A common design is to terminate HTTPS at a reverse proxy such as Nginx, as this workshop does.
- More limited publishing workflow: does not provide push-button publishing, built-in content versioning, Git-backed content management, or scheduled jobs. Deployment is normally implemented with file copying, Git+remote, scripts, configuration management, containers, or another external process.
- Limited scaling and monitoring features
- R dependencies remain your responsibility: Installing Shiny Server does not install every package used by an application. Administrators must ensure that required R packages and system libraries exist and are available to the service account. `{renv}` or other dependency management methods are **highly** recommended.
- File permissions and secrets require care: The application must be able to read what it needs without exposing database passwords or granting excessive filesystem access.

## When is it a good fit?

Open source Shiny Server can be a good fit when:

- you have a Linux VM or server;
- you want to self-host Shiny applications;
- the applications can be public or protected by infrastructure outside Shiny Server;
- traffic and operational requirements are modest;
- your team can administer the host or you have appropriate support from your Technology team;
- you want a transparent, scriptable deployment process.

Consider a managed or commercial platform when you require features such as built-in authentication, self-service publishing, broader content types, scheduling, application scaling, detailed monitoring, or vendor support.

## Check your understanding

1. What is the difference between Shiny and Shiny Server?
2. Why does the `shiny` service account need access to the application directory?
3. How does an app directory become part of its URL?
4. Why does this workshop place Nginx in front of Shiny Server?
5. Which operational tasks remain the administrator's responsibility?
6. When might Posit Connect or a hosted platform be more appropriate?

## Key takeaway

Open source Shiny Server is a lightweight, self-hosted application server for publishing Shiny applications on Linux. It provides the hosting process and URL routing, but production concerns such as HTTPS, authentication, dependency management, monitoring, and deployment automation must be designed around it.
