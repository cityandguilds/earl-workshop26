---
id: postgresql-open-data-instructor
title: Instructor notes: PostgreSQL with OpenFlights
slug: "postgresql-open-data-instructor"
order: 900
section: Instructor resources
section_order: 900
summary: "Preparation and recovery notes for the flights-schema session"
level: "Instructor"
estimated_minutes: 30
---

# Instructor notes

## Schema

All lesson objects live in the `flights` schema:

- `flights.airports`
- `flights.airlines`
- `flights.routes`
- `flights.route_details`

The participant role must have permission to create a schema in its database. The provisioning script makes `workshop_user` the owner of `workshop_db`, so the intended workshop configuration should support this. Verify it on a disposable participant VM.

## Pre-flight test

```bash
sudo -u student Rscript --vanilla - <<'RS'
readRenviron("/home/student/.config/dsi/database.env")
library(DBI)
library(RPostgres)
con <- dbConnect(
  Postgres(),
  host = Sys.getenv("PGHOST"),
  port = as.integer(Sys.getenv("PGPORT")),
  dbname = Sys.getenv("PGDATABASE"),
  user = Sys.getenv("PGUSER"),
  password = Sys.getenv("PGPASSWORD")
)
dbExecute(con, "CREATE SCHEMA IF NOT EXISTS flights")
print(dbGetQuery(con, "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'flights'"))
dbDisconnect(con)
RS
```

## Running order

| Time             | Activity                                   |
|------------------|--------------------------------------------|
| 0 to 5 minutes   | Connect, explain schemas, create `flights` |
| 5 to 12 minutes  | Download and inspect data                  |
| 12 to 17 minutes | Write schema-qualified tables and indexes  |
| 17 to 25 minutes | Filter, aggregate, and join                |
| 25 to 30 minutes | Create `flights.route_details` for Shiny   |

## Teaching point

Explain the three-level name:

```text
database -> schema -> table
workshop_db -> flights -> airports
```

Schema-qualified SQL makes the location explicit and avoids relying on PostgreSQL's `search_path`.

## Shiny handoff

The app should query the view explicitly:

```sql
SELECT destination_code, destination_city, destination_country, airline_name
FROM flights.route_details
WHERE source_code = $1
ORDER BY destination_country, destination_city;
```

Use parameterised queries for values supplied by participants or app users.

## Troubleshooting

Check the schema and objects:

```bash
set -a
source ~/.config/dsi/database.env
set +a
psql -c '\dn'
psql -c '\dt flights.*'
psql -c '\dv flights.*'
```

If schema creation fails, confirm the role owns the database:

```bash
sudo -u postgres psql -c '\l+ workshop_db'
```

## Reset

```r
readRenviron("~/.config/dsi/database.env")
library(DBI)
library(RPostgres)
con <- dbConnect(
  Postgres(),
  host = Sys.getenv("PGHOST"),
  port = as.integer(Sys.getenv("PGPORT")),
  dbname = Sys.getenv("PGDATABASE"),
  user = Sys.getenv("PGUSER"),
  password = Sys.getenv("PGPASSWORD")
)
dbExecute(con, "DROP SCHEMA IF EXISTS flights CASCADE")
dbDisconnect(con)
```

`CASCADE` removes every object inside the schema, so reserve this reset for disposable workshop databases.
