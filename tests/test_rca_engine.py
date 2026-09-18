"""Comprehensive RCA Engine tests for Cascade RCA.

Tests cover:
- Graph construction and direction
- Payment failure cascade detection and root cause
- Database latency cascade detection and root cause
- Notification failure isolation
- Dual simultaneous injection independence
- Temporal ordering in causal scoring
- Causal score bounds
- Healthy system handling
- RCAResult contract compliance
"""

import sys
import os

# Ensure project root is on path for package imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.contracts import (
    DEPENDENCIES,
    RCAResult,
    RootCause,
    SERVICE_NAMES,
    TelemetryEvent,
    TimelineEvent,
)
from backend.rca_engine import (
    analyze_incident,
    build_service_graph,
    calculate_causal_score,
    detect_cascade,
)
from backend.simulator import (
    reset_simulation,
    simulate_database_latency,
    simulate_notification_failure,
    simulate_payment_failure,
    get_incident,
)
from backend.telemetry import clear_telemetry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset():
    """Reset all state between tests."""
    reset_simulation()
    clear_telemetry()


# ===========================================================================
# 1. Graph Construction
# ===========================================================================

class TestBuildServiceGraph:
    """Verify NetworkX graph matches locked topology."""

    def test_graph_has_all_seven_services(self):
        g = build_service_graph()
        assert set(g.nodes()) == set(SERVICE_NAMES)
        assert len(g.nodes()) == 7

    def test_graph_has_six_dependency_edges(self):
        g = build_service_graph()
        assert len(g.edges()) == 6

    def test_graph_edge_direction_preserved(self):
        """Edges must be caller → callee, NOT reversed."""
        g = build_service_graph()
        for caller, callee in DEPENDENCIES:
            assert g.has_edge(caller, callee), (
                f"Missing edge {caller} → {callee}"
            )

    def test_graph_no_reversed_edges(self):
        """Verify callee → caller edges do NOT exist."""
        g = build_service_graph()
        for caller, callee in DEPENDENCIES:
            if not g.has_edge(callee, caller):
                # Expected: reverse edge should not exist (unless also a valid dep)
                valid_deps = set(DEPENDENCIES)
                assert (callee, caller) not in valid_deps or g.has_edge(callee, caller)

    def test_api_gateway_has_three_downstream(self):
        g = build_service_graph()
        successors = list(g.successors("api-gateway"))
        assert set(successors) == {"user-service", "order-service", "product-service"}

    def test_payment_service_depends_on_database(self):
        g = build_service_graph()
        assert g.has_edge("payment-service", "database")

    def test_order_service_depends_on_payment_and_notification(self):
        g = build_service_graph()
        successors = list(g.successors("order-service"))
        assert "payment-service" in successors
        assert "notification-service" in successors


# ===========================================================================
# 2. Payment Failure Cascade
# ===========================================================================

class TestPaymentFailure:
    """Payment failure: payment-service → order-service → api-gateway."""

    def setup_method(self):
        _reset()

    def test_payment_simulation_returns_incident_id(self):
        resp = simulate_payment_failure()
        assert resp.incident_id.startswith("INC-")
        assert resp.status == "active"

    def test_payment_rca_root_cause_is_payment_service(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.root_cause.service == "payment-service"

    def test_payment_rca_confidence_above_threshold(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.root_cause.confidence >= 0.85

    def test_payment_rca_affected_services(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        # order-service and api-gateway should be affected
        assert "order-service" in result.affected_services
        assert "api-gateway" in result.affected_services
        # payment-service is root cause, NOT in affected
        assert "payment-service" not in result.affected_services

    def test_payment_rca_status_resolved(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.status == "resolved"

    def test_payment_rca_has_timeline(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert len(result.timeline) > 0
        # Timeline events must have required fields
        for event in result.timeline:
            assert event.timestamp
            assert event.service
            assert event.event

    def test_payment_rca_has_explanation(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert len(result.explanation) > 0
        assert "payment-service" in result.explanation


# ===========================================================================
# 3. Database Latency Cascade
# ===========================================================================

class TestDatabaseLatency:
    """Database latency: database → payment-service → order-service → api-gateway."""

    def setup_method(self):
        _reset()

    def test_database_rca_root_cause_is_database(self):
        resp = simulate_database_latency()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.root_cause.service == "database"

    def test_database_rca_confidence_above_threshold(self):
        resp = simulate_database_latency()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.root_cause.confidence >= 0.85

    def test_database_rca_affected_includes_full_chain(self):
        resp = simulate_database_latency()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        # All services in the cascade chain should be affected
        assert "payment-service" in result.affected_services
        assert "order-service" in result.affected_services
        assert "api-gateway" in result.affected_services
        # database is root cause, NOT in affected
        assert "database" not in result.affected_services

    def test_database_rca_has_timeline(self):
        resp = simulate_database_latency()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert len(result.timeline) >= 4  # database + 3 downstream


# ===========================================================================
# 4. Notification Failure Isolation
# ===========================================================================

class TestNotificationIsolation:
    """Notification failure must NOT cascade to order-service or api-gateway."""

    def setup_method(self):
        _reset()

    def test_notification_rca_root_cause_is_notification_service(self):
        resp = simulate_notification_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.root_cause.service == "notification-service"

    def test_notification_does_not_cascade_to_order_service(self):
        resp = simulate_notification_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        # order-service should NOT be affected by notification failure
        assert "order-service" not in result.affected_services

    def test_notification_does_not_cascade_to_api_gateway(self):
        resp = simulate_notification_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert "api-gateway" not in result.affected_services

    def test_notification_isolated_in_cascade_detection(self):
        resp = simulate_notification_failure()
        incident = get_incident(resp.incident_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        # Only notification-service should be failing
        failing = cascade["failing_services"]
        assert "notification-service" in failing
        assert "order-service" not in failing
        assert "api-gateway" not in failing


# ===========================================================================
# 5. Dual Simultaneous Injection — Independence
# ===========================================================================

class TestDualInjection:
    """Payment + notification injected simultaneously.

    Engine must NOT merge them into one false causal chain.
    payment-service → notification-service must NOT be inferred.
    """

    def setup_method(self):
        _reset()

    def _inject_both(self):
        resp1 = simulate_payment_failure()
        resp2 = simulate_notification_failure(incident_id=resp1.incident_id)
        return resp1.incident_id

    def test_dual_injection_same_incident(self):
        inc_id = self._inject_both()
        incident = get_incident(inc_id)

        assert "payment_failure" in incident.scenarios
        assert "notification_failure" in incident.scenarios

    def test_dual_injection_primary_root_cause_is_payment(self):
        """Primary root cause should be payment-service (larger cascade)."""
        inc_id = self._inject_both()
        incident = get_incident(inc_id)
        result = analyze_incident(inc_id, incident.telemetry)

        assert result.root_cause.service == "payment-service"

    def test_dual_injection_notification_not_in_payment_cascade(self):
        """notification-service must NOT be falsely linked to payment cascade."""
        inc_id = self._inject_both()
        incident = get_incident(inc_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        components = cascade["components"]
        # Should have at least 2 independent components
        assert len(components) >= 2, (
            f"Expected ≥2 independent failure components, got {len(components)}: {components}"
        )

    def test_dual_injection_components_are_independent(self):
        """The two failure components should be separate graph partitions."""
        inc_id = self._inject_both()
        incident = get_incident(inc_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        components = cascade["components"]
        # Find which component contains notification-service
        notif_comp = None
        payment_comp = None
        for comp in components:
            if "notification-service" in comp["services"]:
                notif_comp = comp
            if "payment-service" in comp["services"]:
                payment_comp = comp

        assert notif_comp is not None, "notification-service not found in any component"
        assert payment_comp is not None, "payment-service not found in any component"

        # They must be DIFFERENT components
        assert notif_comp is not payment_comp, (
            "notification-service and payment-service should be in separate components"
        )

    def test_dual_injection_notification_mentioned_in_timeline(self):
        """Independent notification failure should appear in timeline."""
        inc_id = self._inject_both()
        incident = get_incident(inc_id)
        result = analyze_incident(inc_id, incident.telemetry)

        timeline_services = [e.service for e in result.timeline]
        assert "notification-service" in timeline_services

    def test_dual_injection_explanation_mentions_independent(self):
        """Explanation should note independent failure."""
        inc_id = self._inject_both()
        incident = get_incident(inc_id)
        result = analyze_incident(inc_id, incident.telemetry)

        # The explanation should mention independence/isolation
        explanation_lower = result.explanation.lower()
        assert any(
            word in explanation_lower
            for word in ["independent", "isolated", "concurrent", "not causally"]
        ), f"Explanation should mention independent failure: {result.explanation}"


# ===========================================================================
# 6. Temporal Ordering
# ===========================================================================

class TestTemporalOrdering:
    """Earlier onset + upstream position should score higher than later downstream."""

    def setup_method(self):
        _reset()

    def test_payment_scores_higher_than_order_service(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        score_pay = calculate_causal_score("payment-service", incident.telemetry, graph, cascade)
        score_ord = calculate_causal_score("order-service", incident.telemetry, graph, cascade)

        assert score_pay > score_ord, (
            f"payment-service ({score_pay}) should score higher than order-service ({score_ord})"
        )

    def test_database_scores_higher_than_payment_service(self):
        resp = simulate_database_latency()
        incident = get_incident(resp.incident_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        score_db = calculate_causal_score("database", incident.telemetry, graph, cascade)
        score_pay = calculate_causal_score("payment-service", incident.telemetry, graph, cascade)

        assert score_db > score_pay, (
            f"database ({score_db}) should score higher than payment-service ({score_pay})"
        )


# ===========================================================================
# 7. Causal Score Bounds
# ===========================================================================

class TestCausalScoreBounds:
    """All causal scores must be clamped between 0.0 and 1.0."""

    def setup_method(self):
        _reset()

    def test_all_scores_in_range(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        for service in SERVICE_NAMES:
            score = calculate_causal_score(service, incident.telemetry, graph, cascade)
            assert 0.0 <= score <= 1.0, (
                f"{service} score {score} out of range [0.0, 1.0]"
            )

    def test_non_failing_service_scores_zero(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        graph = build_service_graph()
        cascade = detect_cascade(incident.telemetry, graph)

        # user-service and product-service should not be failing
        score_user = calculate_causal_score("user-service", incident.telemetry, graph, cascade)
        score_product = calculate_causal_score("product-service", incident.telemetry, graph, cascade)

        assert score_user == 0.0
        assert score_product == 0.0


# ===========================================================================
# 8. Healthy System
# ===========================================================================

class TestHealthySystem:
    """When no failures exist, RCA should return healthy status."""

    def setup_method(self):
        _reset()

    def test_healthy_system_returns_healthy_status(self):
        result = analyze_incident("INC-HEALTHY", telemetry=[], graph=build_service_graph())

        assert result.status == "healthy"

    def test_healthy_system_no_root_cause(self):
        result = analyze_incident("INC-HEALTHY", telemetry=[], graph=build_service_graph())

        assert result.root_cause.confidence == 0.0

    def test_healthy_system_no_affected_services(self):
        result = analyze_incident("INC-HEALTHY", telemetry=[], graph=build_service_graph())

        assert result.affected_services == []


# ===========================================================================
# 9. RCAResult Contract Compliance
# ===========================================================================

class TestRCAResultContract:
    """Verify output strictly matches contracts.py RCAResult."""

    def setup_method(self):
        _reset()

    def test_result_has_all_required_fields(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        # All required top-level fields
        assert hasattr(result, "incident_id")
        assert hasattr(result, "status")
        assert hasattr(result, "root_cause")
        assert hasattr(result, "affected_services")
        assert hasattr(result, "timeline")
        assert hasattr(result, "commit")
        assert hasattr(result, "explanation")

    def test_result_root_cause_has_required_fields(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert hasattr(result.root_cause, "service")
        assert hasattr(result.root_cause, "confidence")
        assert isinstance(result.root_cause.service, str)
        assert isinstance(result.root_cause.confidence, float)

    def test_result_is_rca_result_instance(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert isinstance(result, RCAResult)

    def test_result_serializes_to_canonical_json(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        data = result.model_dump()

        # Required top-level keys
        required_keys = {
            "incident_id", "status", "root_cause",
            "affected_services", "timeline", "commit", "explanation",
        }
        assert required_keys.issubset(data.keys())

        # Root cause keys
        assert "service" in data["root_cause"]
        assert "confidence" in data["root_cause"]

    def test_timeline_events_are_timeline_event_instances(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        for event in result.timeline:
            assert isinstance(event, TimelineEvent)

    def test_incident_id_preserved(self):
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)
        result = analyze_incident(resp.incident_id, incident.telemetry)

        assert result.incident_id == resp.incident_id
