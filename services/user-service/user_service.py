"""Demo user service source for Cascade RCA."""

SERVICE_NAME = "user-service"

def get_user(user_id: str) -> dict:
    return {"user_id": user_id, "status": "active"}
