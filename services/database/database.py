"""Demo database service source for Cascade RCA."""

SERVICE_NAME = "database"

QUERY_TIMEOUT_MS = 2800

def execute_query(query: str) -> dict:
    return {
        "query": query,
        "status": "completed",
    }
