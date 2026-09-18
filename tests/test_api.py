"""API endpoint integration tests for Cascade RCA.

Tests cover:
- GET /health
- GET /graph (healthy and with failures)
- POST /simulate/* endpoints
- GET /rca/{incident_id}
- GET /incident/{incident_id}
- POST /simulate/reset
- Dual injection API flow
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.main import app
from backend.simulator import reset_simulation
from backend.telemetry import clear_telemetry


client = TestClient(app)


def _reset():
    """Reset all state between tests."""
    reset_simulation()
    clear_telemetry()


# ===========================================================================
# 1. Health Endpoint
# ===========================================================================

class TestHealthEndpoint:

    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_structure(self):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["services_count"] == 7
        assert data["dependencies_count"] == 6


# ===========================================================================
# 2. Graph Endpoint
# ===========================================================================

class TestGraphEndpoint:

    def setup_method(self):
        _reset()

    def test_graph_returns_200(self):
        resp = client.get("/graph")
        assert resp.status_code == 200

    def test_graph_has_seven_nodes(self):
        resp = client.get("/graph")
        data = resp.json()
        assert len(data["nodes"]) == 7

    def test_graph_has_six_edges(self):
        resp = client.get("/graph")
        data = resp.json()
        assert len(data["edges"]) == 6

    def test_graph_all_healthy_initially(self):
        resp = client.get("/graph")
        data = resp.json()
        for node in data["nodes"]:
            assert node["status"] == "healthy"

    def test_graph_shows_failures_after_injection(self):
        client.post("/simulate/payment-failure")
        resp = client.get("/graph")
        data = resp.json()

        statuses = {n["id"]: n["status"] for n in data["nodes"]}
        # payment-service should be root_cause
        assert statuses["payment-service"] == "root_cause"
        # order-service and api-gateway should be critical
        assert statuses["order-service"] == "critical"
        assert statuses["api-gateway"] == "critical"
        # Unaffected services stay healthy
        assert statuses["user-service"] == "healthy"
        assert statuses["product-service"] == "healthy"


# ===========================================================================
# 3. Simulation Endpoints
# ===========================================================================

class TestSimulationEndpoints:

    def setup_method(self):
        _reset()

    def test_payment_failure_returns_active(self):
        resp = client.post("/simulate/payment-failure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["incident_id"].startswith("INC-")

    def test_database_latency_returns_active(self):
        resp = client.post("/simulate/database-latency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    def test_notification_failure_returns_active(self):
        resp = client.post("/simulate/notification-failure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"


# ===========================================================================
# 4. RCA Endpoint
# ===========================================================================

class TestRCAEndpoint:

    def setup_method(self):
        _reset()

    def test_rca_payment_returns_correct_root_cause(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        assert rca_resp.status_code == 200

        data = rca_resp.json()
        assert data["root_cause"]["service"] == "payment-service"
        assert data["root_cause"]["confidence"] >= 0.85
        assert data["status"] == "resolved"

    def test_rca_database_returns_correct_root_cause(self):
        sim_resp = client.post("/simulate/database-latency")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()
        assert data["root_cause"]["service"] == "database"
        assert data["root_cause"]["confidence"] >= 0.85

    def test_rca_notification_returns_correct_root_cause(self):
        sim_resp = client.post("/simulate/notification-failure")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()
        assert data["root_cause"]["service"] == "notification-service"

    def test_rca_has_all_required_fields(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()

        required_keys = {
            "incident_id", "status", "root_cause",
            "affected_services", "timeline", "commit", "explanation",
        }
        assert required_keys.issubset(data.keys())

    def test_rca_timeline_not_empty(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()
        assert len(data["timeline"]) > 0

    def test_rca_explanation_not_empty(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()
        assert len(data["explanation"]) > 0


# ===========================================================================
# 5. Incident Endpoint
# ===========================================================================

class TestIncidentEndpoint:

    def setup_method(self):
        _reset()

    def test_unknown_incident_returns_404(self):
        resp = client.get("/incident/INC-NONEXISTENT")
        assert resp.status_code == 404

    def test_known_incident_returns_200(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        resp = client.get(f"/incident/{inc_id}")
        assert resp.status_code == 200

    def test_incident_has_telemetry(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        resp = client.get(f"/incident/{inc_id}")
        data = resp.json()
        assert len(data["telemetry"]) > 0

    def test_incident_has_scenarios(self):
        sim_resp = client.post("/simulate/payment-failure")
        inc_id = sim_resp.json()["incident_id"]

        resp = client.get(f"/incident/{inc_id}")
        data = resp.json()
        assert "payment_failure" in data["scenarios"]


# ===========================================================================
# 6. Reset Endpoint
# ===========================================================================

class TestResetEndpoint:

    def setup_method(self):
        _reset()

    def test_reset_returns_healthy(self):
        client.post("/simulate/payment-failure")
        resp = client.post("/simulate/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_reset_clears_graph_state(self):
        client.post("/simulate/payment-failure")
        client.post("/simulate/reset")

        resp = client.get("/graph")
        data = resp.json()
        for node in data["nodes"]:
            assert node["status"] == "healthy"


# ===========================================================================
# 7. Dual Injection API Flow
# ===========================================================================

class TestDualInjectionAPI:
    """End-to-end: inject payment + notification via API, verify RCA."""

    def setup_method(self):
        _reset()

    def test_dual_injection_rca_primary_is_payment(self):
        resp1 = client.post("/simulate/payment-failure")
        inc_id = resp1.json()["incident_id"]

        # Second injection on same incident
        client.post("/simulate/notification-failure")

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()

        assert data["root_cause"]["service"] == "payment-service"

    def test_dual_injection_both_scenarios_recorded(self):
        resp1 = client.post("/simulate/payment-failure")
        inc_id = resp1.json()["incident_id"]
        client.post("/simulate/notification-failure")

        inc_resp = client.get(f"/incident/{inc_id}")
        data = inc_resp.json()

        assert "payment_failure" in data["scenarios"]
        assert "notification_failure" in data["scenarios"]

    def test_dual_injection_notification_in_timeline(self):
        resp1 = client.post("/simulate/payment-failure")
        inc_id = resp1.json()["incident_id"]
        client.post("/simulate/notification-failure")

        rca_resp = client.get(f"/rca/{inc_id}")
        data = rca_resp.json()

        timeline_services = [e["service"] for e in data["timeline"]]
        assert "notification-service" in timeline_services
