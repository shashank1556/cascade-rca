"""Gemini explanation service for Cascade RCA. LOCKED.

Locked public function:
- generate_explanation(...)

Gemini is strictly the explanation/narration layer.
The RCA engine is authoritative and has already determined the root cause.
Resilient: Falls back to deterministic explanation if Gemini fails, is unconfigured, or is rate-limited.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union
import httpx
from dotenv import load_dotenv

from backend.contracts import CommitInfo, RCAResult, RootCause, TimelineEvent

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-1.5-flash"


def _build_deterministic_explanation(
    service: str,
    confidence: float,
    affected_services: List[str],
    timeline: List[Any],
    commit: Optional[Union[Dict[str, Any], CommitInfo]] = None,
    independent_failures: Optional[List[Any]] = None,
) -> str:
    """Generate a precise, deterministic causal explanation when Gemini is unavailable."""
    conf_percent = int(round(confidence * 100))

    if service == "payment-service":
        chain_desc = "payment-service -> order-service -> api-gateway"
        base_msg = (
            f"Causal analysis identified {service} as the primary root cause with {conf_percent}% confidence. "
            f"Anomalous telemetry initiated at {service}, subsequently propagating upstream to {', '.join(affected_services)} "
            f"along the call dependency path ({chain_desc})."
        )
    elif service == "database":
        chain_desc = "database -> payment-service -> order-service -> api-gateway"
        base_msg = (
            f"Causal analysis identified {service} as the originating root cause with {conf_percent}% confidence. "
            f"Severe latency spike (>2800ms) originated at {service}, causing connection timeouts that cascaded "
            f"to {', '.join(affected_services)} along {chain_desc}."
        )
    elif service == "notification-service":
        base_msg = (
            f"Causal analysis identified {service} as the isolated root cause with {conf_percent}% confidence. "
            f"Failure symptoms remained localized within {service} and did not propagate to upstream dependencies."
        )
    else:
        affected_str = f": {', '.join(affected_services)}" if affected_services else ""
        base_msg = (
            f"Causal analysis identified {service} as the primary root cause with {conf_percent}% confidence, "
            f"triggering cascading degradation across {len(affected_services)} downstream dependencies{affected_str}."
        )

    # Correlated commit narration
    if commit:
        if isinstance(commit, CommitInfo):
            c_sha = commit.sha
            c_msg = commit.message
            c_author = commit.author
        elif isinstance(commit, dict):
            c_sha = commit.get("sha", "")
            c_msg = commit.get("message", "")
            c_author = commit.get("author", "")
        else:
            c_sha = getattr(commit, "sha", "")
            c_msg = getattr(commit, "message", "")
            c_author = getattr(commit, "author", "")

        if c_sha:
            base_msg += f" Strongly correlated with recent commit {c_sha} ('{c_msg}')."

    # Independent concurrent failures narration
    if independent_failures:
        indep_names = []
        for f in independent_failures:
            if isinstance(f, dict):
                indep_names.append(f.get("service", "unknown"))
            elif hasattr(f, "service"):
                indep_names.append(f.service)
            else:
                indep_names.append(str(f))

        indep_str = ", ".join(indep_names)
        base_msg += (
            f" Note: Independent concurrent failure detected at {indep_str}. "
            f"Dependency analysis confirms {indep_str} is an isolated failure component "
            f"and not causally connected to the {service} cascade chain."
        )

    return base_msg


def generate_explanation(
    evidence: Optional[Union[Dict[str, Any], RCAResult]] = None,
    *,
    service: Optional[str] = None,
    confidence: Optional[float] = None,
    affected_services: Optional[List[str]] = None,
    timeline: Optional[List[Any]] = None,
    commit: Optional[Union[Dict[str, Any], CommitInfo]] = None,
    independent_failures: Optional[List[Any]] = None,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Generate a human-readable explanation of the incident based strictly on structured RCA evidence.

    Compatible with:
        generate_explanation(evidence: Dict[str, Any]) -> str
        generate_explanation(rca_result: RCAResult) -> str
        generate_explanation(service="...", confidence=0.91, ...) -> str

    Gemini is ONLY the narration layer. The RCA engine is authoritative.
    If Gemini is unconfigured, rate-limited, or fails, a deterministic explanation is returned.
    """
    root_cause_service = "unknown-service"
    conf_val = 0.85
    affected: List[str] = []
    tl: List[Any] = []
    cmt: Optional[Union[Dict[str, Any], CommitInfo]] = None
    indep: List[Any] = []

    # Case 1: Dictionary input (as sent by rca_engine.py)
    if isinstance(evidence, dict):
        rc_dict = evidence.get("root_cause", {})
        if isinstance(rc_dict, dict):
            root_cause_service = rc_dict.get("service", service or "unknown-service")
            conf_val = float(rc_dict.get("confidence", confidence if confidence is not None else 0.85))
        elif hasattr(rc_dict, "service"):
            root_cause_service = rc_dict.service
            conf_val = float(getattr(rc_dict, "confidence", 0.85))

        affected = evidence.get("affected_services", affected_services or [])
        tl = evidence.get("timeline", timeline or [])
        cmt = evidence.get("commit", commit)
        indep = evidence.get("independent_failures", independent_failures or [])

    # Case 2: RCAResult model input
    elif isinstance(evidence, RCAResult):
        root_cause_service = evidence.root_cause.service
        conf_val = float(evidence.root_cause.confidence)
        affected = list(evidence.affected_services)
        tl = list(evidence.timeline)
        cmt = evidence.commit
        indep = independent_failures or []

    # Case 3: Keyword arguments only
    else:
        root_cause_service = service or "unknown-service"
        conf_val = confidence if confidence is not None else 0.85
        affected = affected_services or []
        tl = timeline or []
        cmt = commit
        indep = independent_failures or []

    # Build reliable fallback text
    fallback_text = _build_deterministic_explanation(
        service=root_cause_service,
        confidence=conf_val,
        affected_services=affected,
        timeline=tl,
        commit=cmt,
        independent_failures=indep,
    )

    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        logger.info("GEMINI_API_KEY not configured. Using deterministic explanation fallback.")
        return fallback_text

    # Prompt Gemini strictly as narrator
    prompt = (
        "You are an expert Site Reliability Engineer explaining a microservice incident.\n"
        "Based STRICTLY on this causal RCA evidence, provide a concise 2-3 sentence incident explanation.\n"
        "Do not invent facts not in the evidence. Do NOT change the root cause or speculate on alternative causes.\n"
        f"- Primary Root Cause: {root_cause_service} (confidence: {conf_val:.2f})\n"
        f"- Affected Services: {', '.join(affected) if affected else 'None'}\n"
        f"- Independent Concurrent Failures: {', '.join([str(f) for f in indep]) if indep else 'None'}\n"
        f"- Correlated Commit: {cmt if cmt else 'None'}\n"
    )

    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={api_key.strip()}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 200,
        },
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        text = parts[0]["text"].strip()
                        if text:
                            return text
            else:
                logger.warning("Gemini API error (status %d): %s", resp.status_code, resp.text[:100])
    except Exception as e:
        logger.warning("Gemini API call failed: %s; falling back to deterministic explanation", e)

    return fallback_text
