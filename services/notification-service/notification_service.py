"""Demo notification service source for Cascade RCA."""

SERVICE_NAME = "notification-service"

RETRY_LIMIT = 3

def send_notification(user_id: str, message: str) -> dict:
    return {
        "user_id": user_id,
        "message": message,
        "status": "queued",
    }
