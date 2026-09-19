"""Demo product service source for Cascade RCA."""

SERVICE_NAME = "product-service"

def get_product(product_id: str) -> dict:
    return {"product_id": product_id, "available": True}
