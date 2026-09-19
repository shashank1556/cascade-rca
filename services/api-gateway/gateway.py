"""Demo API gateway service source for Cascade RCA."""

SERVICE_NAME = "api-gateway"

def route_request(path: str) -> str:
    return f"Routing request: {path}"
