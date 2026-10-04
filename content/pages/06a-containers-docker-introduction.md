---
id: containers-docker-introduction
title: "Containers and an introduction to Docker"
slug: "containers-docker-introduction"
order: 500
section: "Docker and ShinyProxy"
section_order: 500
summary: "Understand containers, images, Dockerfiles, registries, ports, and the Docker workflow"
level: "Beginner"
estimated_minutes: 15
---

## Session goal

This page introduces containers and the main Docker concepts needed for the final workshop activity. You will inspect the Docker installation, run a small container, and learn how application source code becomes a reusable container image.

## Learning outcomes

By the end of this introduction, you should be able to:

- explain the purpose of a software container;
- distinguish an image from a container;
- explain the role of Docker Engine, a Dockerfile, and an image registry;
- describe container port publishing;
- use basic Docker commands to inspect, run, stop, and remove containers;
- explain how containers differ from virtual machines;
- recognise where Docker fits into the workshop architecture.

## Why containers?

An application normally depends on more than its source code. It may need a particular language runtime, operating-system libraries, packages, configuration, and a startup command.

A container image packages these requirements into a standard unit. When Docker starts that image, it creates a container: an isolated process with its own filesystem and network view. Docker describes a container image as a lightweight, standalone executable package containing the code, runtime, system tools, libraries, and settings required by an application.

This makes the deployment unit more explicit:

```text
Application code
    + runtime
    + packages
    + system libraries
    + default configuration
    + startup command
    = container image
```

The official Docker introductory material focuses on running a container, building an image, and sharing a containerised application. citeturn38search225turn38search227

## Images and containers

The terms **image** and **container** are related but not interchangeable.

### Image

An image is the packaged template used to create containers. It contains the application filesystem and metadata such as the default process to run.

An image is identified by a name and usually a tag:

```text
nginx:latest
rocker/shiny:4.4.2
shiny-flights:1.0
```

The part after the colon is the tag. Tags are commonly used to distinguish versions or variants.

### Container

A container is an instance of an image. It can be running or stopped.

```text
Image: shiny-flights:1.0
        |
        +----> Container: shiny-flights-a
        +----> Container: shiny-flights-b
```

Two containers created from the same image begin with the same packaged application, but they are separate runtime instances.

## Containers and virtual machines

Your participant environment is already a virtual machine. Docker then runs containers inside that VM.

```text
Physical cloud host
    |
    v
Participant Ubuntu VM
    |
    +----> Nginx
    +----> PostgreSQL
    +----> Docker Engine
               |
               +----> application container
```

A virtual machine includes a complete guest operating system and virtualised hardware. Containers instead share the host operating-system kernel while running isolated processes.

| Virtual machine | Container |
|---|---|
| Virtualises a computer | Isolates an application process |
| Includes a guest operating system | Shares the host kernel |
| Created from a VM image or snapshot | Created from a container image |
| Suitable for a complete server environment | Suitable for packaging an application and its dependencies |

Containers do not replace virtual machines in this workshop. They provide an additional application packaging and deployment layer inside the participant VM.

## Core Docker components

### Docker command-line client

The `docker` command is the interface you use in the terminal:

```bash
docker version
docker ps
docker run hello-world
```

### Docker Engine

Docker Engine manages images, containers, networks, and volumes on the host. The Docker client sends requests to it.

### Dockerfile

A `Dockerfile` is a text file containing image build instructions. A simple Dockerfile might:

1. select a base image;
2. install packages;
3. copy application files;
4. define a working directory;
5. specify the command that starts the application.

Example structure:

```dockerfile
FROM rocker/shiny:4.4.2

RUN install2.r DBI RPostgres

COPY app/ /srv/shiny-server/

EXPOSE 3838

CMD ["/usr/bin/shiny-server"]
```

The exact Dockerfile used later in the workshop may differ, but the build process follows this pattern.

### Image registry

A registry stores and distributes container images. A host can pull an existing image from a registry, and image authors can push images for reuse elsewhere.

```text
Registry
   |
   | docker pull
   v
Local image store
   |
   | docker run
   v
Container
```

## The basic Docker workflow

```text
Dockerfile + application files
             |
             | docker build
             v
           Image
             |
             | docker run
             v
         Container
```

Common commands include:

| Command | Purpose |
|---|---|
| `docker build` | Build an image from a Dockerfile |
| `docker images` | List local images |
| `docker run` | Create and start a container |
| `docker ps` | List running containers |
| `docker ps -a` | List running and stopped containers |
| `docker logs` | Read a container's output |
| `docker stop` | Stop a running container |
| `docker rm` | Remove a container |
| `docker rmi` | Remove a local image |

## Check Docker on the VM

Confirm that the client and engine are available:

```bash
docker --version
docker version
docker info --format '{{.ServerVersion}}'
```

Check the service:

```bash
systemctl is-active docker
```

Expected output:

```text
active
```

Confirm that your user can access Docker:

```bash
id
docker ps
```

If `docker ps` succeeds without `sudo`, the `student` account has access to the Docker socket through its group membership.

> **Security note:** access to the Docker daemon is highly privileged. Only trusted users should receive it.

## Run a first container

Run Docker's test image:

```bash
docker run --rm hello-world
```

This command:

1. looks for the image locally;
2. pulls it if it is not present;
3. creates a container;
4. starts the container's configured process;
5. displays its output;
6. removes the stopped container because `--rm` was supplied.

Inspect the local images afterwards:

```bash
docker images
```

## Run a background web container

Start a small Nginx container bound only to the VM's loopback interface:

```bash
docker run   --detach   --name docker-intro   --publish 127.0.0.1:8082:80   nginx:alpine
```

The port mapping has this form:

```text
host-address:host-port:container-port
127.0.0.1:8082:80
```

This means:

```text
VM request to 127.0.0.1:8082
              |
              v
container port 80
```

Binding to `127.0.0.1` keeps this demonstration local to the VM. It does not add a new public workshop port.

Test the container:

```bash
curl --head http://127.0.0.1:8082/
```

Inspect it:

```bash
docker ps
docker logs docker-intro
docker inspect docker-intro   --format '{{.Config.Image}} {{.State.Status}}'
```

## Stop and remove the demonstration

```bash
docker stop docker-intro
docker rm docker-intro
```

Confirm that it has gone:

```bash
docker ps -a   --filter name=docker-intro
```

The downloaded image remains in the local image store unless you remove it separately.

## Container data and lifecycle

A container should usually be treated as replaceable. If important data exists only in its writable container layer, removing the container removes that data.

Docker provides two common ways to keep data outside that layer:

- **volumes**, managed by Docker;
- **bind mounts**, which expose a host file or directory inside a container.

In production designs, databases and other stateful data require deliberate persistence, backup, permission, and recovery planning. In this workshop, PostgreSQL continues to run directly on the VM, while the application is containerised.

## Configuration and secrets

Do not bake participant passwords into a Dockerfile or image. Runtime configuration can instead be supplied through environment variables, mounted files, or a platform's secret-management facility.

The distinction is:

```text
Image
  application and reusable dependencies

Runtime configuration
  participant-specific hostname, password, database settings
```

This follows the same separation already used elsewhere in the workshop: reusable software is prepared once, while participant-specific credentials are added during provisioning or at runtime.

## Docker in this workshop

The final application path will be similar to:

```text
Browser
   |
   | HTTPS
   v
Nginx
   |
   v
ShinyProxy
   |
   v
Docker container
   |
   v
Shiny application
```

The public connection still enters through Nginx on HTTPS port `443`. ShinyProxy manages the application container behind that gateway.

## Troubleshooting

### Docker service is not active

```bash
sudo systemctl start docker
systemctl status docker --no-pager
```

### Permission denied for the Docker socket

Check group membership:

```bash
id
getent group docker
```

If your account was newly added to the group, the login session may need to be restarted before the new membership applies.

### A container exits immediately

A container normally stops when its main process exits. Inspect its status and logs:

```bash
docker ps -a
docker logs CONTAINER_NAME
```

### A host port is already in use

```bash
sudo ss -lntp
```

Choose an unused local host port or stop the process already using the required port.

### Clean up a failed demonstration

```bash
docker rm --force docker-intro 2>/dev/null || true
```

## Check your understanding

1. What is the difference between an image and a container?
2. What does a Dockerfile describe?
3. Why does a container usually stop when its main process exits?
4. What does `127.0.0.1:8082:80` mean?
5. Why is the example bound to `127.0.0.1` rather than every network interface?
6. Where should participant-specific database passwords be supplied?
7. How does a container differ from the participant VM?
8. Which component provides the public HTTPS entry point in this workshop?

## Key takeaway

A container is a replaceable runtime instance created from an image. Docker provides the tools to build images, start containers, connect them to networks, supply runtime configuration, inspect their behaviour, and remove them cleanly. In the workshop, Docker packages the application while the existing VM, Nginx gateway, PostgreSQL database, and security controls remain in place.
