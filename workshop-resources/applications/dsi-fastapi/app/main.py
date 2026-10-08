from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query

from .database import get_connection
from .models import Airport, CountrySummary, HealthResponse, Route

app = FastAPI(
    title="Flights API",
    description=(
        "A read-only workshop API backed by the PostgreSQL "
        "flights.route_details view."
    ),
    version="1.0.0",
    root_path="/api",
)

Connection = Annotated[psycopg.Connection, Depends(get_connection)]


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {
        "name": "Flights API",
        "docs": "/api/docs",
        "health": "/api/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health(connection: Connection) -> HealthResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database() AS database")
        row = cursor.fetchone()

    return HealthResponse(status="ok", database=row["database"])


@app.get("/airports", response_model=list[Airport], tags=["flights"])
def list_airports(
    connection: Connection,
    country: Annotated[
        str | None,
        Query(description="Optional exact source-country filter"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Airport]:
    query = """
        SELECT DISTINCT
            source_code,
            source_airport,
            source_city,
            source_country
        FROM flights.route_details
        WHERE source_code IS NOT NULL
          AND (%s IS NULL OR source_country = %s)
        ORDER BY source_country, source_city, source_airport
        LIMIT %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (country, country, limit))
        return [Airport(**row) for row in cursor.fetchall()]


@app.get(
    "/airports/{source_code}/routes",
    response_model=list[Route],
    tags=["flights"],
)
def routes_from_airport(
    source_code: str,
    connection: Connection,
    destination_country: Annotated[
        str | None,
        Query(description="Optional exact destination-country filter"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Route]:
    source_code = source_code.strip().upper()

    query = """
        SELECT DISTINCT
            destination_code,
            destination_airport,
            destination_city,
            destination_country,
            airline_name,
            destination_latitude,
            destination_longitude
        FROM flights.route_details
        WHERE source_code = %s
          AND (%s IS NULL OR destination_country = %s)
        ORDER BY destination_country, destination_city,
                 destination_airport, airline_name
        LIMIT %s
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                source_code,
                destination_country,
                destination_country,
                limit,
            ),
        )
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No routes found for source airport {source_code}",
        )

    return [Route(**row) for row in rows]


@app.get(
    "/airports/{source_code}/countries",
    response_model=list[CountrySummary],
    tags=["flights"],
)
def route_countries(
    source_code: str,
    connection: Connection,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CountrySummary]:
    source_code = source_code.strip().upper()

    query = """
        SELECT
            destination_country,
            COUNT(*)::integer AS route_count,
            COUNT(DISTINCT destination_code)::integer AS destination_count
        FROM flights.route_details
        WHERE source_code = %s
          AND destination_country IS NOT NULL
        GROUP BY destination_country
        ORDER BY route_count DESC, destination_country
        LIMIT %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (source_code, limit))
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No route countries found for source airport {source_code}",
        )

    return [CountrySummary(**row) for row in rows]
