---
id: fastapi-introduction
title: Introduction to FastAPI
slug: "fastapi-introduction"
order: 300
section: FastAPI
section_order: 300
summary: "Understand what FastAPI is, how it works, and when to use it"
level: "Beginner"
estimated_minutes: 15
---

## What you will learn

By the end of this page, you should be able to:

- explain what an API is;
- describe the role of FastAPI;
- create and run a small FastAPI application;
- explain how type hints support validation and documentation;
- identify the roles of FastAPI, Uvicorn, systemd, and Nginx;
- describe FastAPI's main advantages and disadvantages;
- identify situations where another framework may be more suitable.

## What is an API?

An **application programming interface**, or **API**, allows software systems to communicate through a defined set of requests and responses.

A web API normally exposes **endpoints** through URLs. A client sends an HTTP request to an endpoint, and the API returns an HTTP response.

For example:

```text
Request
GET /airports/MAN/routes?limit=5

Response
200 OK
Content-Type: application/json

[
  {
    "destination_code": "AMS",
    "destination_city": "Amsterdam"
  }
]
```

The client could be:

- a web browser;
- a command-line program such as `curl`;
- a Shiny application;
- a Python or R script;
- another web service;
- a mobile application.

## What is FastAPI?

**FastAPI** is an open source Python framework for building web APIs. It uses standard Python type hints and is built around the OpenAPI and JSON Schema standards.

FastAPI is responsible for application-level features such as:

- matching URLs to Python functions;
- reading path, query, header, and body values;
- validating request data;
- converting Python results into JSON responses;
- reporting structured validation errors;
- generating an OpenAPI description;
- generating interactive API documentation;
- providing a dependency-injection system;
- supporting synchronous and asynchronous endpoint functions.

FastAPI is a framework, not a database and not a complete web server deployment by itself.

## A minimal FastAPI application

Create a file called `main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Hello API")


@app.get("/")
def root():
    return {"message": "Hello from FastAPI"}


@app.get("/airports/{airport_code}")
def airport(airport_code: str):
    return {"airport_code": airport_code.upper()}
```

The decorator:

```python
@app.get("/airports/{airport_code}")
```

connects an HTTP `GET` request to the Python function below it.

The value in `{airport_code}` is a **path parameter**. FastAPI passes it to the function's `airport_code` argument.

## How FastAPI uses Python type hints

Consider this endpoint:

```python
from typing import Annotated

from fastapi import FastAPI, Query

app = FastAPI()


@app.get("/routes")
def routes(
    source_code: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return {
        "source_code": source_code.upper(),
        "limit": limit,
    }
```

The declaration communicates that:

- `source_code` must be supplied as text;
- `limit` must be an integer;
- `limit` defaults to `20`;
- `limit` must be between `1` and `100`.

FastAPI uses this information to validate requests and describe the parameter in the generated API documentation.

For example:

```text
/routes?source_code=MAN&limit=10
```

is valid, while:

```text
/routes?source_code=MAN&limit=zero
```

fails integer validation.

## Request and response models

Pydantic models can describe structured request and response data:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Airport(BaseModel):
    code: str
    name: str
    country: str | None = None


@app.get("/airport", response_model=Airport)
def airport():
    return {
        "code": "MAN",
        "name": "Manchester Airport",
        "country": "United Kingdom",
    }
```

The response model documents the JSON structure and checks that the returned data matches it.

## How a FastAPI request works

A simplified application flow is:

```text
HTTP request
    |
    v
ASGI server, such as Uvicorn
    |
    v
FastAPI routing
    |
    v
Parameter parsing and validation
    |
    v
Python endpoint function
    |
    +---- optional database or service call
    |
    v
Response validation and JSON conversion
    |
    v
HTTP response
```

FastAPI defines the application. An **ASGI (Asynchronous Server Gateway Interface) server**, commonly Uvicorn, listens for network requests and runs that application.

In the workshop deployment, the larger path is:

```text
Browser or curl
    |
    | HTTPS
    v
Nginx
    |
    | HTTP on 127.0.0.1:8000
    v
Uvicorn
    |
    v
FastAPI
    |
    v
PostgreSQL
```

The components have different responsibilities:

- **Nginx** accepts public HTTPS traffic and proxies `/api/` requests;
- **Uvicorn** runs the Python ASGI application;
- **FastAPI** handles API routes, validation, and responses;
- **PostgreSQL** stores and queries the flight data;
- **systemd** starts, stops, and monitors the Uvicorn service.

## Installing FastAPI

Use a Python virtual environment so that the project's packages are isolated from the operating system and other projects.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn
```

> **Important**: as with {renv} for managing R dependencies, we favour `uv` over `pip`+other for fast python package/project management but ommitted it here for a slightly more streamlined design. Checkout the [workshop repo](https://github.com/cityandguilds/earl-workshop26) and [`uv` docs](https://docs.astral.sh/uv/) for more info.

A standard FastAPI installation includes the FastAPI command-line interface and the Uvicorn ASGI app.

A project that connects directly to PostgreSQL also needs a PostgreSQL driver. For example:

```bash
python -m pip install "psycopg2[binary]"
```

Record project dependencies in a project configuration or requirements file so the environment can be reproduced (or, as above, let `uv` take care of this for you).

For example:

```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
psycopg2[binary]>=3.2,<4.0
```

The specific versions used in a real project should be selected, tested, and updated through the project's dependency-management process.

## Running the application during development

With `main.py` in the current directory, run:

```bash
fastapi dev main.py
```

Alternatively, run Uvicorn directly:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

In `main:app`:

- `main` refers to `main.py`;
- `app` refers to the `FastAPI()` object inside the file.

The `--reload` option restarts the process when source files change. **It is useful during development and should not be treated as a production process manager**.

## Automatic API documentation

FastAPI creates an OpenAPI description from the application. It includes two documentation interfaces by default:

```text
/docs   Swagger UI
/redoc  ReDoc
```

Swagger UI lets developers:

- inspect endpoints;
- see required parameters;
- review request and response schemas;
- submit test requests from a browser;
- inspect response codes, headers, and bodies.

The underlying machine-readable OpenAPI document is normally available at:

```text
/openapi.json
```

In this workshop, Nginx publishes the application below `/api`, so the public paths are:

```text
/api/docs
/api/redoc
/api/openapi.json
```

## Where are the official docs?

Use these official starting points:

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [FastAPI features](https://fastapi.tiangolo.com/features/)
- [FastAPI deployment guidance](https://fastapi.tiangolo.com/deployment/)
- [FastAPI source repository](https://github.com/fastapi/fastapi)
- [Pydantic documentation](https://docs.pydantic.dev/)
- [Uvicorn documentation](https://www.uvicorn.org/)

The tutorial is a good entry point for beginners. The reference section is useful when you already know the feature or function you need.

## FastAPI position in the market

FastAPI occupies the Python API-framework part of the web-development market. It is designed primarily for API-first services rather than for providing a complete website platform with every feature built in.

It is often considered alongside:

- Flask: small, flexible Python web framework. It provides a simple foundation, while validation, API schemas, and documentation are usually added through other libraries or extensions. FastAPI provides type-driven validation and OpenAPI documentation as central framework features.
- Django and Django REST Framework: Django is a broader web framework with features such as an ORM (Object-Relational Mapping which reduces raw SQL requirement), migrations, administration interfaces, authentication, templates, and forms. Django REST Framework adds extensive API capabilities to Django.

FastAPI is narrower and API-focused (no built-in ORM or Django-style administration site).

### Other API technologies

FastAPI competes indirectly with API stacks in JavaScript or TypeScript, Java, C#, Go, and other languages. The choice usually depends on an organisation's existing skills, libraries, operations, performance needs, and wider architecture.

FastAPI is particularly relevant when an organisation already uses Python for data science, machine learning, automation, or data engineering and wants to expose Python functionality through an HTTP API.

## Advantages

- Familiar Python syntax: Endpoints use ordinary Python functions, decorators, and type hints rather than a separate interface-definition language.
- Automatic validation: FastAPI interprets declared types and constraints, converts compatible input values, and returns structured errors for invalid requests.
- Automatic documentation: OpenAPI, Swagger UI, and ReDoc are generated from the same declarations used by the application.
- Strong editor support: Standard type hints support completion, navigation, and static-analysis features in modern Python editors.
- Clear data contracts: Pydantic request and response models make expected JSON structures explicit.
- Async support: FastAPI supports both `def` and `async def` endpoints, allowing it to work with synchronous and asynchronous libraries.
- Dependency injection: Dependencies can provide shared facilities such as database connections, authentication checks, and configuration.
- Standards based: FastAPI uses OpenAPI and JSON Schema, supporting interoperable documentation and client-generation workflows.

## Disadvantages/limitations

- Not a complete deployment platform: FastAPI does not by itself provide HTTPS termination, operating-system service management, deployment automation, monitoring, backups, or firewall configuration. Other components must supply these capabilities.
- No built-in database layer: FastAPI does not require or include one database system or ORM. You must select, configure, and operate an appropriate database library.
- Async code adds complexity: Asynchronous programming can improve concurrency for suitable workloads, but mixing synchronous and asynchronous libraries requires care. Beginners should not add `async` merely because it is available.
- Production operation requires additional decisions: A deployed API still needs decisions about:

    + authentication and authorisation;
    + dependency versions;
    + secrets management;
    + database connection management;
    + logging and monitoring;
    + testing;
    + rate limiting;
    + error handling;
    + worker processes and scaling;
    + reverse proxies and HTTPS.

- Type declarations require discipline: FastAPI's validation and documentation are most useful when types and models accurately describe the API. Incorrect or overly loose models weaken those benefits.
- It may be too narrow for a full website: For an application needing a built-in administration interface, server-rendered forms, a tightly integrated ORM, and a complete website framework, Django may provide more of the required structure.
- Small services can still become complex: FastAPI makes a first endpoint easy to create, but a maintainable service still needs sensible modules, tests, configuration, and operational practices.

## When is FastAPI a good fit?

FastAPI can be a good choice when:

- the main product is an HTTP API, e.g. we have added a shiny front-end to a FastAPI 'engine' for a high-stakes C&G system;
- the team is comfortable with Python;
- typed request and response models are valuable;
- automatic OpenAPI documentation is useful;
- the service integrates with Python data or machine-learning code;
- the team is prepared to choose its own database and deployment components.

Consider another approach when:

- a broad, integrated website framework is required;
- the team has stronger expertise in another platform;
- an existing organisational standard already solves the problem;
- the task is so small that a separate network API would add unnecessary complexity.

## FastAPI in this workshop

Our flights API exposes read-only endpoints backed by PostgreSQL:

```text
GET /health
GET /airports
GET /airports/{source_code}/routes
GET /airports/{source_code}/countries
```

The core request path is:

```text
Client
  -> Nginx
  -> Uvicorn
  -> FastAPI endpoint
  -> parameterised PostgreSQL query
  -> validated JSON response
```

The exercise therefore connects concepts from earlier workshop sections:

- Linux services and ports;
- Nginx reverse proxying;
- PostgreSQL and SQL;
- configuration and credentials;
- application deployment;
- browser and command-line clients.

## Check your understanding

1. What is the difference between FastAPI and Uvicorn?
2. What does `@app.get()` do?
3. How does FastAPI use Python type hints?
4. What is OpenAPI?
5. Where is Swagger UI normally available?
6. Why should development reload mode not be treated as a production process manager?
7. Which deployment responsibilities are outside FastAPI?
8. When might Django be a more suitable choice?

## Key takeaway

FastAPI is a focused Python framework for building typed, validated, standards-based web APIs. It makes endpoint development and documentation approachable, but a reliable deployed service still depends on database, security, testing, process-management, networking, and operational choices around it.
