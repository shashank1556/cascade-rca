"""Demo payment service source for Cascade RCA."""

SERVICE_NAME = "payment-service"

PAYMENT_GATEWAY_TIMEOUT_MS = 3000

def process_payment(order_id: str, amount: float) -> dict:
    return {
        "order_id": order_id,
        "amount": amount,
        "status": "authorized",
    }
