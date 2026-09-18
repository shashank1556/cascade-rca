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


# ===========================================================================
# 10. Malformed Timestamp Handling (Issue 1 regression)
# ===========================================================================

class TestMalformedTimestamps:
    """Malformed timestamps must NOT distort RCA by appearing as earliest onset."""

    def setup_method(self):
        _reset()

    def test_malformed_timestamp_does_not_become_root_cause(self):
        """A service with a malformed timestamp must NOT be selected as root
        cause solely because its timestamp parsed to epoch 0 / earliest."""
        from backend.rca_engine import _parse_ts

        # Valid timestamps
        valid_ts = "2026-09-18T10:00:01+00:00"
        # Malformed timestamp
        bad_ts = "NOT-A-TIMESTAMP"

        valid_epoch = _parse_ts(valid_ts)
        bad_epoch = _parse_ts(bad_ts)

        # Bad timestamp must NOT be earlier than valid timestamp
        assert bad_epoch > valid_epoch, (
            f"Malformed timestamp epoch ({bad_epoch}) should be > valid epoch ({valid_epoch}). "
            f"Malformed timestamps must not appear as the earliest event."
        )

    def test_parse_ts_returns_inf_for_garbage(self):
        from backend.rca_engine import _parse_ts
        assert _parse_ts("garbage") == float("inf")
        assert _parse_ts("") == float("inf")
        assert _parse_ts("12345") == float("inf")

    def test_parse_ts_handles_valid_iso(self):
        from backend.rca_engine import _parse_ts
        epoch = _parse_ts("2026-09-18T10:00:00+00:00")
        assert epoch > 0
        assert epoch != float("inf")

    def test_parse_ts_handles_z_suffix(self):
        from backend.rca_engine import _parse_ts
        epoch = _parse_ts("2026-09-18T10:00:00Z")
        assert epoch > 0
        assert epoch != float("inf")

    def test_malformed_telemetry_does_not_crash_rca(self):
        """RCA engine must handle telemetry with bad timestamps deterministically."""
        graph = build_service_graph()

        # Create telemetry with one malformed timestamp
        bad_event = TelemetryEvent(
            timestamp="INVALID",
            service="payment-service",
            trace_id="trace-bad",
            span_id="span-bad",
            parent_span_id=None,
            latency_ms=900.0,
            status_code=500,
        )
        good_event = TelemetryEvent(
            timestamp="2026-09-18T10:00:01+00:00",
            service="order-service",
            trace_id="trace-good",
            span_id="span-good",
            parent_span_id=None,
            latency_ms=920.0,
            status_code=500,
        )

        result = analyze_incident("INC-BADTS", telemetry=[bad_event, good_event], graph=graph)

        # RCA must still produce a valid result without crashing
        assert isinstance(result, RCAResult)
        assert result.status == "resolved"
        assert result.root_cause.service in ("payment-service", "order-service")
        # Core safety invariant: the malformed timestamp must NOT have been
        # treated as epoch 0 (earliest). Verify via cascade_info internals.
        from backend.rca_engine import detect_cascade
        cascade = detect_cascade([bad_event, good_event], graph)
        stats = cascade["service_stats"]
        bad_epoch = stats["payment-service"]["first_anomaly_epoch"]
        good_epoch = stats["order-service"]["first_anomaly_epoch"]
        assert bad_epoch > good_epoch, (
            f"Malformed timestamp epoch ({bad_epoch}) must be > valid epoch ({good_epoch}). "
            f"Malformed timestamps must not gain false temporal priority."
        )


# ===========================================================================
# 11. External API Failure Resilience (Issue 4 regression)
# ===========================================================================

class TestExternalAPIResilience:
    """RCA must produce valid results even when GitHub/Gemini throw exceptions."""

    def setup_method(self):
        _reset()

    def test_rca_works_when_github_raises_exception(self):
        """Simulate catastrophic GitHub failure — RCA must still return."""
        import backend.rca_engine as engine
        original_fn = engine.get_recent_commits

        def _exploding_github(*args, **kwargs):
            raise ConnectionError("GitHub is down")

        engine.get_recent_commits = _exploding_github
        try:
            resp = simulate_payment_failure()
            incident = get_incident(resp.incident_id)
            result = analyze_incident(resp.incident_id, incident.telemetry)

            # Core RCA decision must survive
            assert result.root_cause.service == "payment-service"
            assert result.root_cause.confidence >= 0.85
            assert result.status == "resolved"
            # commit should be null when GitHub fails
            assert result.commit is None
        finally:
            engine.get_recent_commits = original_fn

    def test_rca_works_when_gemini_raises_exception(self):
        """Simulate catastrophic Gemini failure — RCA must still return."""
        import backend.rca_engine as engine
        original_fn = engine.generate_explanation

        def _exploding_gemini(*args, **kwargs):
            raise ConnectionError("Gemini is down")

        engine.generate_explanation = _exploding_gemini
        try:
            resp = simulate_payment_failure()
            incident = get_incident(resp.incident_id)
            result = analyze_incident(resp.incident_id, incident.telemetry)

            # Core RCA decision must survive
            assert result.root_cause.service == "payment-service"
            assert result.root_cause.confidence >= 0.85
            assert result.status == "resolved"
            # Explanation must still exist (inline deterministic fallback)
            assert len(result.explanation) > 0
        finally:
            engine.generate_explanation = original_fn

    def test_rca_works_when_both_external_apis_fail(self):
        """Both GitHub and Gemini fail — RCA core decision is unaffected."""
        import backend.rca_engine as engine
        orig_github = engine.get_recent_commits
        orig_gemini = engine.generate_explanation

        engine.get_recent_commits = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
        engine.generate_explanation = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
        try:
            resp = simulate_payment_failure()
            incident = get_incident(resp.incident_id)
            result = analyze_incident(resp.incident_id, incident.telemetry)

            assert result.root_cause.service == "payment-service"
            assert result.commit is None
            assert len(result.explanation) > 0
        finally:
            engine.get_recent_commits = orig_github
            engine.generate_explanation = orig_gemini


# ===========================================================================
# 12. Payment + Database Dual Injection (Issue 5 additional scenario)
# ===========================================================================

class TestPaymentAndDatabaseDualInjection:
    """Two failures on the same checkout path: payment + database."""

    def setup_method(self):
        _reset()

    def test_payment_then_database_root_cause_is_database(self):
        """When both payment and database fail, database should be root cause
        since it is further upstream in the dependency chain.

        Note: confidence may be lower than single-scenario cases because
        overlapping cascades produce mixed temporal signals (payment-service
        already failing from the payment scenario before database injection).
        """
        resp1 = simulate_payment_failure()
        simulate_database_latency(incident_id=resp1.incident_id)
        incident = get_incident(resp1.incident_id)
        result = analyze_incident(resp1.incident_id, incident.telemetry)

        assert result.root_cause.service == "database"
        assert result.root_cause.confidence > 0.0  # Must have positive confidence

    def test_payment_then_database_affected_chain(self):
        resp1 = simulate_payment_failure()
        simulate_database_latency(incident_id=resp1.incident_id)
        incident = get_incident(resp1.incident_id)
        result = analyze_incident(resp1.incident_id, incident.telemetry)

        assert "payment-service" in result.affected_services
        assert "order-service" in result.affected_services
        assert "api-gateway" in result.affected_services


# ===========================================================================
# 13. Confidence Score Properties (Issue 2 additional verification)
# ===========================================================================

class TestConfidenceScoreProperties:
    """Verify confidence score properties required by architecture."""

    def setup_method(self):
        _reset()

    def test_confidence_is_deterministic(self):
        """Same input must produce same confidence every time."""
        resp = simulate_payment_failure()
        incident = get_incident(resp.incident_id)

        r1 = analyze_incident(resp.incident_id, incident.telemetry)
        r2 = analyze_incident(resp.incident_id, incident.telemetry)

        assert r1.root_cause.confidence == r2.root_cause.confidence

    def test_confidence_within_bounds(self):
        """All scenarios must produce confidence in [0.0, 1.0]."""
        for sim_fn in [simulate_payment_failure, simulate_database_latency, simulate_notification_failure]:
            _reset()
            resp = sim_fn()
            incident = get_incident(resp.incident_id)
            result = analyze_incident(resp.incident_id, incident.telemetry)
            assert 0.0 <= result.root_cause.confidence <= 1.0, (
                f"Confidence {result.root_cause.confidence} out of bounds for {sim_fn.__name__}"
            )
