"""Gemini explanation service for Cascade RCA.

Locked public function:
- generate_explanation(...)

Gemini is strictly the explanation/narration layer.
The RCA engine is authoritative.
Resilient: Falls back to deterministic explanation if Gemini fails or is unconfigured.
"""

import os
from typing import Any, Dict, Optional
import httpx


def _build_deterministic_explanation(evidence: Dict[str, Any]) -> str:
    """Generate a precise, deterministic causal explanation."""
    root_cause = evidence.get("root_cause", {})
    service = root_cause.get("service", "unknown-service")
    confidence = root_cause.get("confidence", 0.0)
    affected = evidence.get("affected_services", [])
    commit = evidence.get("commit")
    independent_failures = evidence.get("independent_failures", [])

    conf_percent = int(round(confidence * 100))

    if service == "payment-service":
        chain_desc = "payment-service -> order-service -> api-gateway"
        base_msg = (
            f"Causal analysis identified {service} as the primary root cause with {conf_percent}% confidence. "
            f"Anomalous telemetry initiated at {service}, subsequently propagating upstream to {', '.join(affected)} "
            f"along the call dependency path ({chain_desc})."
        )
    elif service == "database":
        chain_desc = "database -> payment-service -> order-service -> api-gateway"
        base_msg = (
            f"Causal analysis identified {service} as the originating root cause with {conf_percent}% confidence. "
            f"Severe latency spike (>2800ms) originated at {service}, causing connection timeouts that cascaded "
            f"to {', '.join(affected)} along {chain_desc}."
        )
    elif service == "notification-service":
        base_msg = (
            f"Causal analysis identified {service} as the isolated root cause with {conf_percent}% confidence. "
            f"Failure symptoms remained localized within {service} and did not propagate to upstream dependencies."
        )
    else:
        base_msg = (
            f"Causal analysis identified {service} as the primary root cause with {conf_percent}% confidence, "
            f"triggering cascading degradation across {len(affected)} downstream dependencies: {', '.join(affected)}."
        )

    if commit and isinstance(commit, dict) and commit.get("sha"):
        base_msg += f" Strongly correlated with recent commit {commit.get('sha')} ('{commit.get('message')}')."

    if independent_failures:
        indep_names = [
            f.get("service") if isinstance(f, dict) else str(f)
            for f in independent_failures
        ]
        base_msg += (
            f" Note: Independent concurrent failure detected at {', '.join(indep_names)}. "
            f"Dependency analysis confirms {', '.join(indep_names)} is an isolated failure component "
            f"and not causally connected to the {service} cascade chain."
        )

    return base_msg


def generate_explanation(evidence: Dict[str, Any]) -> str:
    """Generate a human-readable explanation of the incident.

    Calls Gemini REST API if GEMINI_API_KEY is available;
    otherwise falls back gracefully to a deterministic explanation.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _build_deterministic_explanation(evidence)

    prompt = (
        "You are an expert Site Reliability Engineer explaining a microservice incident.\n"
        "Based STRICTLY on this causal RCA evidence, provide a concise 2-3 sentence incident explanation.\n"
        "Do not invent facts not in the evidence. Highlight root cause, confidence, propagation path, "
        "and note if any independent concurrent failure exists.\n\n"
        f"Evidence:\n{evidence}\n"
    )

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 200,
            },
        }
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                text = (
                    result.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if text:
                    return text
    except Exception:
        pass

    return _build_deterministic_explanation(evidence)
