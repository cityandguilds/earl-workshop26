---
id: postgresql-open-data-solutions
title: PostgreSQL open-data exercise solutions
slug: "postgresql-open-data-solutions"
order: 110
section: PostgreSQL
section_order: 110
summary: "Suggested solutions using the flights schema"
level: "Beginner"
estimated_minutes: 10
---

## Exercise 1

1. One row represents one airport, airline, or route.
2. `source_airport_id` and `destination_airport_id` connect routes to airports.
3. `airline_id` connects routes to airlines.
4. The schema groups the workshop's flight tables and view under `flights`.

## Selected airport codes

```sql
SELECT airport_id, name, city, country, iata
FROM flights.airports
WHERE iata IN ('LHR', 'MAN', 'EDI')
ORDER BY iata;
```

## Countries with the most airports

```sql
SELECT country, COUNT(*) AS airport_count
FROM flights.airports
GROUP BY country
ORDER BY airport_count DESC, country
LIMIT 10;
```

## Destinations from Edinburgh

```sql
SELECT DISTINCT
  destination.iata,
  destination.name,
  destination.city,
  destination.country
FROM flights.routes AS route
JOIN flights.airports AS source
  ON route.source_airport_id = source.airport_id
JOIN flights.airports AS destination
  ON route.destination_airport_id = destination.airport_id
WHERE source.iata = 'EDI'
ORDER BY destination.country, destination.city, destination.name;
```

## Routes leaving UK airports

```sql
SELECT
  source.iata,
  source.name,
  source.city,
  COUNT(*) AS route_count
FROM flights.routes AS route
JOIN flights.airports AS source
  ON route.source_airport_id = source.airport_id
WHERE source.country = 'United Kingdom'
GROUP BY source.airport_id, source.iata, source.name, source.city
ORDER BY route_count DESC, source.name;
```

## Airlines operating from Manchester

```sql
SELECT airline.name AS airline, COUNT(*) AS route_count
FROM flights.routes AS route
JOIN flights.airports AS source
  ON route.source_airport_id = source.airport_id
JOIN flights.airlines AS airline
  ON route.airline_id = airline.airline_id
WHERE source.iata = 'MAN'
GROUP BY airline.airline_id, airline.name
ORDER BY route_count DESC, airline.name
LIMIT 15;
```

## Optional psql practice

```bash
set -a
source ~/.config/dsi/database.env
set +a
psql
```

```text
\dn
\dt flights.*
\d flights.airports
\dv flights.*
\q
```
