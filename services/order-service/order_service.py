"""Demo order service source for Cascade RCA."""

SERVICE_NAME = "order-service"

def create_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "created"}
