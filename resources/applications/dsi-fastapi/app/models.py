from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str


class Airport(BaseModel):
    source_code: str
    source_airport: str
    source_city: str | None = None
    source_country: str | None = None


class Route(BaseModel):
    destination_code: str | None = None
    destination_airport: str
    destination_city: str | None = None
    destination_country: str | None = None
    airline_name: str | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None


class CountrySummary(BaseModel):
    destination_country: str
    route_count: int
    destination_count: int
