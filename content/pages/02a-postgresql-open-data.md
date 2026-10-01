---
id: postgresql-open-data
title: PostgreSQL with open relational data
slug: "postgresql-open-data"
order: 100
section: PostgreSQL
section_order: 100
summary: "Download open aviation data, load it into a PostgreSQL schema, and answer questions with SQL"
level: "Beginner"
estimated_minutes: 30
---

# PostgreSQL with open relational data

## Session goal

In this session you will download three related OpenFlights datasets, write them to a PostgreSQL schema called `flights`, and query them with SQL. The tables will also support a later Shiny application.

## Learning outcomes

By the end, you should be able to:

- explain tables, rows, primary keys, foreign keys, and schemas;
- connect to PostgreSQL from R;
- download tabular data to your VM;
- write data frames into the `flights` schema;
- use `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY`, and `JOIN`;
- create a reusable view for Shiny.

## Databases and database management systems
### What is a database?

A **database** is an organised collection of data. It provides a dependable way to store information, find it again, update it, and share it between applications.

You could store data in CSV or Excel files, but files become harder to manage when:

- several tables are related;
- multiple people or applications need access;
- data must be updated safely;
- duplicate or invalid records must be prevented;
- queries need to combine and summarise large amounts of data.

A database management system helps solve these problems.

### What is a DBMS?

A **database management system**, or **DBMS**, is software that manages databases.

It is responsible for tasks such as:

- storing and retrieving data;
- accepting queries;
- managing simultaneous users;
- checking permissions;
- enforcing data rules;
- completing updates safely;
- recovering data after failures.

Examples include PostgreSQL, MySQL, MariaDB, SQLite, Microsoft SQL Server, and Oracle Database.

### What is PostgreSQL?

**PostgreSQL**, often shortened to **Postgres**, is a free and open source relational database management system. It uses and extends SQL and is designed around reliability, data integrity, extensibility, and support for complex workloads.

A **relational database** organises data into tables:

```text
airports
+------------+----------------------+------+
| airport_id | name                 | iata |
+------------+----------------------+------+
| 507        | London Heathrow      | LHR  |
| 478        | Manchester Airport   | MAN  |
+------------+----------------------+------+
```

Each table contains:

- **columns**, which define the properties being stored;
- **rows**, which contain individual records;
- **primary keys**, which uniquely identify rows;
- **foreign keys**, which connect rows in related tables.

PostgreSQL can enforce rules including primary keys, foreign keys, and constraints (e.g. `UNIQUE` or `NOT NULL`).

### PostgreSQL and SQL are not the same thing

**SQL**, or Structured Query Language, is a language used to work with relational databases.

**PostgreSQL** is a DBMS that understands SQL and provides the software responsible for storing and managing the data.

For example:

```sql
SELECT name, city, country
FROM flights.airports
WHERE country = 'United Kingdom'
ORDER BY city;
```

The text above is SQL. PostgreSQL receives it, plans how to perform it, reads the relevant data, and returns the result.

### Database, schema, and table

PostgreSQL organises information at several levels:

```text
PostgreSQL server
└── database
    └── schema
        └── table
```

For this workshop, we will work as follows:

```text
PostgreSQL server
└── workshop_db
    └── flights
        ├── airports
        ├── airlines
        ├── routes
        └── route_details
```

A **database** is a separate collection of data and database objects.

A **schema** is a named container inside a database. It helps organise related objects and avoid name collisions.

A **table** stores rows and columns.

The fully qualified name:

```sql
flights.airports
```

means the `airports` table, inside the `flights` schema.

### Database *Views*

A **view** is a saved SQL query that can be used like a table.

For example, this view combines routes, airports, and airlines:

```sql
CREATE VIEW flights.route_details AS
SELECT
  source.iata AS source_code,
  destination.iata AS destination_code,
  destination.city AS destination_city,
  destination.country AS destination_country,
  airline.name AS airline_name
FROM flights.routes AS route
JOIN flights.airports AS source
  ON route.source_airport_id = source.airport_id
JOIN flights.airports AS destination
  ON route.destination_airport_id = destination.airport_id
LEFT JOIN flights.airlines AS airline
  ON route.airline_id = airline.airline_id;
```

You can then query it as though it were a table:

```sql
SELECT *
FROM flights.route_details
WHERE source_code = 'MAN';
```

A normal view does not store a separate copy of the results. PostgreSQL runs the underlying query whenever the view is referenced.

Views are useful because they can:

- hide complicated joins behind a simple name;
- present readable column names;
- provide a consistent interface for applications;
- reduce repeated SQL;
- limit which columns users or applications can access.

For this workshop, the Shiny application can query `flights.route_details` without needing to repeat all the joins between the underlying tables.

### PostgreSQL uses a client-server model

PostgreSQL runs as a background service. Other programs connect to it as clients.

In this workshop, possible clients include:

- the `psql` command-line program;
- an R session using `DBI` and `RPostgres`;
- a Shiny application using the same;
- a Python or FastAPI application.

```text
R, Shiny, FastAPI, or psql
              |
              | SQL connection
              v
         PostgreSQL
              |
              v
     tables and schemas
```

The PostgreSQL server decides whether a client may connect and what it is permitted to do.

On your workshop VM, PostgreSQL listens **only on the local network interface**. It is not exposed directly to the public internet.

### How does PostgreSQL differ from other database systems?

Most relational DBMSs share important concepts:

- tables, rows, and columns;
- SQL queries;
- keys and relationships;
- indexes;
- users and permissions;
- transactions.

The differences are usually found in licensing, architecture, administration tools, supported data types, extensions, and SQL syntax.

#### PostgreSQL and SQLite

SQLite stores a database in a local file and runs inside the application using it.

It is useful for:

- small applications;
- embedded software;
- local analysis;
- prototypes;
- data mainly used by one process.

PostgreSQL runs as a separate server process. It is better suited to applications where multiple users or services need controlled, concurrent access.

#### PostgreSQL and MySQL or MariaDB

MySQL, MariaDB, and PostgreSQL are open source relational database systems.

They share much of the basic SQL model but differ in areas such as available data types, extensions, configuration, SQL behaviour, and administration. SQL written for one system *may therefore require changes* before it works on another.

PostgreSQL places particular emphasis on standards-oriented SQL, data integrity, advanced data types, and extensibility. It supports relational data alongside types such as arrays, ranges, UUIDs, JSON, JSONB, XML, and geometric values.

#### PostgreSQL and proprietary DBMSs

Microsoft SQL Server and Oracle Database are commercial database platforms with their own ecosystems, management tools, SQL extensions, and licensing arrangements.

The main relational ideas remain transferable:

- a table is still a table;
- a primary key still identifies a row;
- a join still combines related data;
- a transaction still groups related changes.

Product-specific commands and features are not always portable.

### Transactions and data safety

A **transaction** treats several related operations as one unit of work.

For example, transferring money might require:

1. subtracting an amount from one account;
2. adding it to another account.

The database should not save only half of that operation.

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 50
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 50
WHERE account_id = 2;

COMMIT;
```

If a problem occurs, the transaction can be rolled back instead of leaving incomplete changes.

PostgreSQL supports ACID transactions:

- **Atomicity:** all operations succeed, or none are saved;
- **Consistency:** database rules remain satisfied;
- **Isolation:** simultaneous transactions do not interfere incorrectly;
- **Durability:** committed changes survive a system failure.

### Why use PostgreSQL in this workshop?

PostgreSQL gives us an open source database that can be shared by several open source tools.

We will use it to:

1. store related airport, airline, and route tables;
2. practise filtering, grouping, and joining with SQL;
3. access the same data from R;
4. query it from a Shiny application;
5. show how an application and database operate as separate services.

The important idea is not to memorise PostgreSQL commands. It is to understand how structured data can be stored once and then used safely by several applications.

### Check your understanding

1. What is the difference between SQL and PostgreSQL?
2. What is the purpose of a primary key?
3. What does a foreign key represent?
4. Where does the `airports` table live in `flights.airports`?
5. Why might PostgreSQL be more suitable than a CSV file for a deployed Shiny application?
6. What is the difference between PostgreSQL and SQLite?

## The relational model

A **schema** is a named container inside a database. We will use it to keep all workshop flight objects together:

```text
workshop_db
└── flights
    ├── airports
    ├── airlines
    ├── routes
    └── route_details
```

Our simplified relationships are:

```text
flights.airlines.airline_id
           |
           +---------- flights.routes.airline_id

flights.airports.airport_id
           |\
           | +--------- flights.routes.source_airport_id
           +----------- flights.routes.destination_airport_id
```

## 0 to 5 minutes: connect and create the schema

```bash
test -s ~/.config/dsi/database.env && echo "database configuration found"
R
```

```r
readRenviron("~/.config/dsi/database.env")
library(DBI)
library(RPostgres)

con <- dbConnect(
  RPostgres::Postgres(),
  host = Sys.getenv("PGHOST"),
  port = as.integer(Sys.getenv("PGPORT")),
  dbname = Sys.getenv("PGDATABASE"),
  user = Sys.getenv("PGUSER"),
  password = Sys.getenv("PGPASSWORD")
)

dbGetQuery(con, "SELECT current_database(), current_user")
dbExecute(con, "CREATE SCHEMA IF NOT EXISTS flights")
```

> Never print, publish, or commit the contents of `database.env`.

## 5 to 12 minutes: download and inspect the data
```bash
R
```

```r
dir.create("~/openflights", showWarnings = FALSE)
setwd("~/openflights")
base_url <- "https://raw.githubusercontent.com/lizardburns/shinyFlights/refs/heads/master/inst/extdata"

for (filename in c("airports.dat", "airlines.dat", "routes.dat")) {
  download.file(paste0(base_url, "/", filename), filename, mode = "wb")
}
```

```r
airports <- read.csv(
  "airports.dat", header = FALSE, na.strings = "\\N",
  stringsAsFactors = FALSE,
  col.names = c(
    "airport_id", "name", "city", "country", "iata", "icao",
    "latitude", "longitude", "altitude", "timezone", "dst",
    "tz_database", "type", "source"
  )
)

airlines <- read.csv(
  "airlines.dat", header = FALSE, na.strings = "\\N",
  stringsAsFactors = FALSE,
  col.names = c(
    "airline_id", "name", "alias", "iata", "icao", "callsign",
    "country", "active"
  )
)

routes <- read.csv(
  "routes.dat", header = FALSE, na.strings = "\\N",
  stringsAsFactors = FALSE,
  col.names = c(
    "airline_code", "airline_id", "source_airport_code",
    "source_airport_id", "destination_airport_code",
    "destination_airport_id", "codeshare", "stops", "equipment"
  )
)

dim(airports)
dim(airlines)
dim(routes)
head(airports[, c("airport_id", "name", "city", "country", "iata")])
```

### Exercise 1

1. What does one row represent in each data frame?
2. Which columns connect routes to airports?
3. Which column connects routes to airlines?
4. What does the `flights` schema help us organise?

## 12 to 17 minutes: write tables to the schema

`DBI::Id()` identifies both the schema and table explicitly.

```r
dbWriteTable(
  con, Id(schema = "flights", table = "airports"),
  airports, overwrite = TRUE, row.names = FALSE
)
dbWriteTable(
  con, Id(schema = "flights", table = "airlines"),
  airlines, overwrite = TRUE, row.names = FALSE
)
dbWriteTable(
  con, Id(schema = "flights", table = "routes"),
  routes, overwrite = TRUE, row.names = FALSE
)
```

```r
dbExecute(con, "CREATE INDEX flights_routes_airline_idx ON flights.routes (airline_id)")
dbExecute(con, "CREATE INDEX flights_routes_source_idx ON flights.routes (source_airport_id)")
dbExecute(con, "CREATE INDEX flights_routes_destination_idx ON flights.routes (destination_airport_id)")
dbExecute(con, "CREATE INDEX flights_airports_country_idx ON flights.airports (country)")
```

```r
dbListTables(con)

dbGetQuery(con, "
  SELECT 'airports' AS table_name, COUNT(*) AS rows FROM flights.airports
  UNION ALL
  SELECT 'airlines', COUNT(*) FROM flights.airlines
  UNION ALL
  SELECT 'routes', COUNT(*) FROM flights.routes
")
```

> `overwrite = TRUE` replaces an existing table. Use it carefully outside a disposable workshop database.

## 17 to 25 minutes: query the database

```r
dbGetQuery(con, "
  SELECT airport_id, name, city, iata
  FROM flights.airports
  WHERE country = 'United Kingdom'
  ORDER BY city, name
  LIMIT 20
")
```

```r
dbGetQuery(con, "
  SELECT country, COUNT(*) AS airport_count
  FROM flights.airports
  GROUP BY country
  ORDER BY airport_count DESC, country
  LIMIT 15
")
```

```r
dbGetQuery(con, "
  SELECT
    source.iata AS source_code,
    destination.iata AS destination_code,
    destination.name AS destination_airport,
    destination.city AS destination_city,
    destination.country AS destination_country,
    airline.name AS airline
  FROM flights.routes AS route
  JOIN flights.airports AS source
    ON route.source_airport_id = source.airport_id
  JOIN flights.airports AS destination
    ON route.destination_airport_id = destination.airport_id
  LEFT JOIN flights.airlines AS airline
    ON route.airline_id = airline.airline_id
  WHERE source.iata = 'MAN'
  ORDER BY destination_country, destination_city, airline
")
```

### Exercise 2

1. Which airports have the IATA codes `LHR`, `MAN`, and `EDI`?
2. Which 10 countries have the most airports?
3. Which destinations can be reached directly from Edinburgh (`EDI`)?
4. How many routes leave each UK airport?
5. Stretch: which airlines operate the most routes from Manchester (`MAN`)?

## 25 to 30 minutes: prepare for Shiny

```r
dbExecute(con, "DROP VIEW IF EXISTS flights.route_details")

dbExecute(con, "
  CREATE VIEW flights.route_details AS
  SELECT
    route.airline_id,
    airline.name AS airline_name,
    source.airport_id AS source_airport_id,
    source.iata AS source_code,
    source.name AS source_airport,
    source.city AS source_city,
    source.country AS source_country,
    destination.airport_id AS destination_airport_id,
    destination.iata AS destination_code,
    destination.name AS destination_airport,
    destination.city AS destination_city,
    destination.country AS destination_country,
    destination.latitude AS destination_latitude,
    destination.longitude AS destination_longitude
  FROM flights.routes AS route
  JOIN flights.airports AS source
    ON route.source_airport_id = source.airport_id
  JOIN flights.airports AS destination
    ON route.destination_airport_id = destination.airport_id
  LEFT JOIN flights.airlines AS airline
    ON route.airline_id = airline.airline_id
")
```

```r
dbGetQuery(con, "
  SELECT *
  FROM flights.route_details
  WHERE source_code = 'MAN'
  ORDER BY destination_country, destination_city
  LIMIT 20
")
```

Then, later, our Shiny app can offer an airport selector, destination table, airline filter, route chart, and map.

```r
dbDisconnect(con)
q(save = "no")
```

## Check your understanding

1. What is a PostgreSQL schema?
2. Why does the route query join `flights.airports` twice?
3. What does `GROUP BY` do?
4. Why should the Shiny app query `flights.route_details` rather than load every source file?

## Data source

- [OpenFlights data documentation](https://openflights.org/data.php)
- [OpenFlights source repository](https://github.com/jpatokal/openflights)
