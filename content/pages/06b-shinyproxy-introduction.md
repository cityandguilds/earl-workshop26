---
id: shinyproxy-introduction
title: Introduction to ShinyProxy
slug: "shinyproxy-introduction"
order: 510
section: Docker and ShinyProxy
section_order: 510
summary: "Understand what ShinyProxy is, how it launches containerised applications, and when to use it"
level: "Beginner"
estimated_minutes: 15
---

## What you will learn

By the end of this page, you should be able to:

- explain the difference between Shiny, Shiny Server, Docker, and ShinyProxy;
- describe how ShinyProxy launches an application container;
- identify its main configuration file, service, ports, and logs;
- explain how application specifications connect URLs to Docker images;
- position ShinyProxy alongside other Shiny publishing options;
- describe its main advantages and disadvantages.

## Shiny and ShinyProxy are different things

**Shiny** is the framework used to build an interactive application with R or Python.

**Docker** packages the application, runtime, packages, and supporting files into a container image.

**ShinyProxy** is separate publishing software. It presents applications to users and uses a container backend to start an isolated application instance from a configured image.

```text
Shiny
  builds the application

Docker
  packages the application

ShinyProxy
  launches and routes application containers
```

ShinyProxy is not a replacement for the application code or its container image. The application must first be packaged into an image that ShinyProxy can access.

## What is ShinyProxy?

ShinyProxy is a Java application designed to publish containerised web applications. Although it is commonly used for Shiny applications, its deployment documentation states that it can support other web applications as well.

For each configured application, ShinyProxy can:

- display an application entry to the user;
- identify the Docker image associated with that entry;
- create an application container;
- route the user's browser session to that container;
- remove or recover containers according to its configuration and lifecycle rules.

In this workshop, ShinyProxy runs as a systemd service on the participant VM and uses the local Docker Engine. It listens on the VM's loopback address rather than being exposed directly to the internet:

```text
127.0.0.1:8081
```

Nginx receives public HTTPS requests and forwards `/proxy/` traffic to ShinyProxy.

## How it works

The simplified request path is:

```text
Browser
   |
   | HTTPS on public port 443
   v
Nginx reverse proxy
   |
   | HTTP on 127.0.0.1:8081
   v
ShinyProxy
   |
   | requests a container from Docker Engine
   v
Docker container
   |
   | runs the packaged application
   v
Shiny application
   |
   | optional connection to services or data
   v
PostgreSQL
```

When a user opens an application:

- the browser sends a request to Nginx;
- Nginx forwards the `/proxy/` request to ShinyProxy;
- ShinyProxy reads the matching application specification;
- Docker Engine creates a container from the configured image;
- the application process listens inside that container;
- ShinyProxy routes the browser session to the correct container;
- the container is managed according to the configured application lifecycle.

## How this differs from Shiny Server

Shiny Server and ShinyProxy can both publish Shiny applications, but their deployment models differ.

| Shiny Server | ShinyProxy |
|---|---|
| Runs application code from directories on the host | Runs applications from container images |
| Uses R packages installed on the host | Uses packages included in the selected image |
| Commonly maps app directories to URLs | Maps application specifications to images and URLs |
| Application processes share the host software environment | Application processes run in separate containers |
| Simple for direct Linux-host deployment | Adds container packaging and lifecycle management |

In the earlier workshop activity, Shiny Server published:

```text
/srv/shiny-server/shinyFlights/
```

In the ShinyProxy activity, the deployable unit is instead a Docker image referenced from `application.yml`.

## Application images and specifications

ShinyProxy deployment begins with a Docker image containing the application. The image can be built on the same machine or stored in a registry that ShinyProxy can access. If an image is available from a registry but absent from the server, ShinyProxy can pull it.

An application then needs a specification in the `proxy.specs` section of `application.yml`. The official deployment guidance identifies these core properties:

- `id`, used as the application identifier and in its URL;
- `container-image`, identifying the Docker image;
- `port`, when the application does not use Shiny's default container port of `3838`.

A small example is:

```yaml
proxy:
  title: Workshop ShinyProxy
  specs:
    - id: flights
      display-name: Flights application
      description: Explore flights data
      container-image: shiny-flights:1.0
```

This associates the `flights` application entry with the local image `shiny-flights:1.0`.

## The configuration file

ShinyProxy is mainly configured in a file named `application.yml`. The expected location depends on how ShinyProxy is deployed. For a JAR deployment, a custom file can be supplied alongside the JAR or through a Spring configuration location; Debian and RPM package deployments use `/etc/shinyproxy/application.yml`. The filename must use the `.yml` extension rather than `.yaml`.

This workshop uses:

```text
/etc/shinyproxy/application.yml
```

Inspect it with:

```bash
sudo cat /etc/shinyproxy/application.yml
```

YAML uses indentation to represent structure. Incorrect indentation can prevent ShinyProxy from reading the intended configuration.

Do not display configuration files if they contain passwords, tokens, registry credentials, or other secrets.

## Important locations

The workshop uses the following locations and services:

| Purpose | Workshop location |
|---|---|
| ShinyProxy JAR | `/opt/shinyproxy/shinyproxy.jar` |
| Main configuration | `/etc/shinyproxy/application.yml` |
| systemd unit | `/etc/systemd/system/shinyproxy.service` |
| Main application port | `127.0.0.1:8081` |
| Management port | `127.0.0.1:9090` |
| Docker images | Docker Engine's local image store |
| Service logs | systemd journal for `shinyproxy` |

Inspect the setup with:

```bash
systemctl cat shinyproxy
sudo ls -l /opt/shinyproxy/shinyproxy.jar
sudo ls -l /etc/shinyproxy/application.yml
docker images
```

## The Docker relationship

When ShinyProxy uses the Docker backend, Docker must be installed on the server that runs ShinyProxy.

The relationship is:

```text
ShinyProxy
    |
    | Docker API request
    v
Docker Engine
    |
    | creates from image
    v
Application container
```

ShinyProxy therefore needs permission to communicate with Docker Engine. This is highly privileged access and must be treated carefully.

In this workshop, ShinyProxy is already installed and configured during golden-image creation. Participants build and register an application image rather than installing the platform itself.

## Ports and routing

Several ports are involved, but they have different scopes:

```text
443
  public HTTPS handled by Nginx

8081
  local ShinyProxy application interface

9090
  local management interface

3838
  default port expected inside a Shiny application container
```

The public path is:

```text
https://dsi-01.earl.sjp-analytics.co.uk/proxy/
```

The `8081`, `9090`, and container application ports are not intended to be exposed publicly in this workshop.

## Authentication and access control

ShinyProxy supports configurable authentication and application access rules. Its configuration examples include authentication settings, users, groups, administrative groups, and per-application access groups.

Authentication design is separate from Nginx HTTPS termination. In a production deployment, plan both:

- how users prove their identity;
- which applications each user may access;
- how registry and application secrets are protected;
- how public traffic reaches ShinyProxy safely.

The workshop configuration is intentionally simplified for learning and should not be copied unchanged into a production environment.

## Managing the service

Inspect the service:

```bash
systemctl status shinyproxy --no-pager
systemctl is-active shinyproxy
```

After changing `application.yml`, restart ShinyProxy so that it loads the new configuration. The official deployment guidance requires a restart after configuration changes.

```bash
sudo systemctl restart shinyproxy
```

Inspect recent service messages:

```bash
sudo journalctl -u shinyproxy -n 100 --no-pager
```

Confirm the listening ports:

```bash
sudo ss -lntp | grep -E ':(8081|9090)'
```

Test ShinyProxy locally:

```bash
curl --head http://127.0.0.1:8081/
```

## Application container inspection

When an application is started, use Docker to inspect its container:

```bash
docker ps
```

Read a container's logs:

```bash
docker logs CONTAINER_NAME
```

Inspect the image and network details:

```bash
docker inspect CONTAINER_NAME
```

Avoid manually stopping an active application container unless you are intentionally attempting recovery or performing troubleshooting.

## How ShinyProxy is installed

ShinyProxy supports several deployment approaches, including a JAR file, Debian or Red Hat packages, Docker, Docker Swarm, Kubernetes, and AWS ECS.

A broad single-server installation sequence is:

- install a supported Java runtime;
- install and start Docker Engine;
- download or install ShinyProxy;
- grant the ShinyProxy process the required Docker access;
- create `application.yml`;
- define application specifications;
- start ShinyProxy;
- place it behind a secure reverse proxy;
- test application container creation and routing.

This workshop uses the JAR approach managed as a systemd service. The bootstrap process installs a pinned JAR and starts it with the workshop configuration.

## Where are the official docs?

Use these starting points:

- [ShinyProxy documentation](https://www.shinyproxy.io/documentation/)
- [ShinyProxy configuration](https://www.shinyproxy.io/documentation/configuration/)
- [ShinyProxy deployment guidance](https://dev.shinyproxy.io/documentation/deployment/)
- [Deploying applications with ShinyProxy](https://dev.shinyproxy.io/documentation/deploying-apps/)
- [ShinyProxy configuration examples](https://github.com/openanalytics/shinyproxy-config-examples)

The documentation covers concepts, configuration, deployment, security, application parameters, recovery, troubleshooting, and API usage. citeturn39search233

## Advantages

- **Application isolation:** each application runs from its configured container image rather than relying entirely on host-installed packages.
- **Reproducible packaging:** the image records the application runtime and dependencies used to start the container.
- **Multiple applications:** `application.yml` can define multiple application specifications.
- **Flexible backends:** ShinyProxy documents deployment options for Docker, Docker Swarm, Kubernetes, and AWS ECS.
- **Central entry point:** users access applications through the ShinyProxy interface rather than individual container ports.
- **Registry support:** images can be built locally or supplied through a Docker registry.
- **Useful for infrastructure learning:** it exposes the relationship between images, containers, application ports, Java services, Docker permissions, reverse proxies, and databases.

## Disadvantages and limitations

- **More moving parts:** ShinyProxy adds Java, Docker, image builds, container networking, lifecycle management, and additional logs.
- **You manage the platform:** the organisation remains responsible for updates, backups, HTTPS, identity integration, secrets, monitoring, capacity, and incident response.
- **Images must be maintained:** operating-system packages, R packages, and application dependencies need versioning and security updates.
- **Docker access is privileged:** compromise of a process with Docker control can have serious consequences for the host.
- **Container startup adds latency:** a user may need to wait while an image is pulled or a container starts.
- **State requires deliberate design:** local container files are not a suitable default location for durable shared data.
- **Configuration errors can prevent app launch:** invalid YAML, an unavailable image, the wrong internal port, or a failing startup command can block the application.
- **Resource planning remains necessary:** each active application container consumes memory, CPU, and host capacity.

## When is it a good fit?

ShinyProxy can be a good fit when:

- applications are already packaged as container images;
- different applications need different R, Python, or system dependencies;
- per-session or isolated application containers are useful;
- a team is prepared to maintain Docker and the ShinyProxy service;
- a reverse proxy, HTTPS, identity, logging, and monitoring design is available;
- deployment should be driven by images and configuration rather than copying files into a shared application directory.

Consider a simpler Shiny Server deployment when container isolation is unnecessary and direct directory-based hosting is sufficient. Consider a managed or commercial platform when the operational burden should be transferred to a platform provider.

## Troubleshooting sequence

Work through the layers in order:

```text
Nginx
  -> ShinyProxy service
  -> application.yml
  -> Docker Engine
  -> application image
  -> application container
  -> application process
  -> PostgreSQL or another dependency
```

Useful checks include:

```bash
systemctl is-active nginx
systemctl is-active shinyproxy
sudo nginx -t
sudo journalctl -u shinyproxy -n 100 --no-pager
docker info
docker images
docker ps -a
```

If a container was created but stopped, inspect it:

```bash
docker logs CONTAINER_NAME
```

If no container was created, inspect ShinyProxy's configuration and service log first.

## Check your understanding

- What is the difference between Shiny and ShinyProxy?
- What must exist before ShinyProxy can start an application container?
- How does an application specification connect a URL entry to an image?
- Why does ShinyProxy need access to Docker Engine?
- Why does the workshop place Nginx in front of ShinyProxy?
- What is the difference between port `8081` and the application's container port?
- Why should database passwords not be stored in the image?
- When might open-source Shiny Server be simpler than ShinyProxy?

## Key takeaway

ShinyProxy is a publishing gateway for containerised applications. It maps configured application entries to images, asks a container backend to start application instances, and routes users to the correct container. Docker supplies the packaging and runtime isolation, while production concerns such as HTTPS, identity, secrets, monitoring, image maintenance, and host security still require deliberate design.
