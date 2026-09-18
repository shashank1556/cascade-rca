"""Gemini Generative AI narration service for Cascade RCA. LOCKED.

Converts structured root-cause analysis (RCA) evidence into clear, concise
human-readable explanations. 

CRITICAL PRINCIPLE:
Gemini is SOLELY a narration layer. The RCA engine is authoritative.
If Gemini is unavailable, unconfigured, or fails, a deterministic
rule-based explanation is returned immediately.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

from backend.contracts import CommitInfo, RCAResult, RootCause, TimelineEvent

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-1.5-flash"


def _generate_deterministic_fallback(
    root_cause_service: str,
    confidence: float,
    affected_services: List[str],
    timeline: List[TimelineEvent],
    commit: Optional[CommitInfo] = None,
    independent_failures: Optional[List[str]] = None,
) -> str:
    """Deterministic, resilient rule-based explanation when Gemini is unavailable."""
    conf_pct = int(confidence * 100)
    
    # Check if there are independent failures reported
    if independent_failures:
        independent_str = ", ".join(independent_failures)
        if affected_services:
            affected_str = " → ".join([root_cause_service] + affected_services)
            base_msg = (
                f"Causal analysis identified '{root_cause_service}' as the primary root cause "
                f"({conf_pct}% confidence), cascading along the dependency path: {affected_str}. "
                f"Concurrently, an independent failure was detected in '{independent_str}'; "
                f"service topology confirms it is isolated with no causal link to the primary cascade."
            )
        else:
            base_msg = (
                f"Causal analysis identified '{root_cause_service}' as the root cause "
                f"({conf_pct}% confidence). Concurrently, an independent failure was detected "
                f"in '{independent_str}' without cascading propagation."
            )
    elif affected_services:
        cascade_path = " → ".join([root_cause_service] + affected_services)
        base_msg = (
            f"Root-cause analysis isolated '{root_cause_service}' ({conf_pct}% confidence) "
            f"as the origin of the failure cascade propagating through {cascade_path}. "
            f"Downstream service alerts were caused by upstream dependency unavailability."
        )
    else:
        base_msg = (
            f"Root-cause analysis isolated '{root_cause_service}' with {conf_pct}% confidence. "
            f"The anomaly remained contained with no downstream propagation detected."
        )

    if commit:
        base_msg += f" Correlated with recent commit {commit.sha} by {commit.author}: \"{commit.message}\"."

    return base_msg


def generate_explanation(
    rca_result: Optional[RCAResult] = None,
    *,
    service: Optional[str] = None,
    confidence: Optional[float] = None,
    affected_services: Optional[List[str]] = None,
    timeline: Optional[List[TimelineEvent]] = None,
    commit: Optional[CommitInfo] = None,
    independent_failures: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> str:
    """Generate concise human-readable explanation from structured RCA evidence.

    Accepts either an RCAResult object or individual keyword arguments.
    Gracefully falls back to deterministic narration if Gemini API fails or is not configured.

    Args:
        rca_result: Canonical RCAResult instance.
        service: Name of root-cause service (if rca_result not provided).
        confidence: Confidence score 0.0-1.0 (if rca_result not provided).
        affected_services: List of affected downstream services.
        timeline: List of TimelineEvent items.
        commit: Optional CommitInfo instance.
        independent_failures: Optional list of independent concurrent failure services.
        api_key: Optional Gemini API key override (defaults to GEMINI_API_KEY env var).

    Returns:
        Concise, human-readable narrative string.
    """
    # Extract structured fields
    if rca_result is not None:
        root_cause_service = rca_result.root_cause.service
        conf_val = rca_result.root_cause.confidence
        affected = list(rca_result.affected_services)
        tl = list(rca_result.timeline)
        cmt = rca_result.commit or commit
    else:
        root_cause_service = service or "unknown-service"
        conf_val = confidence if confidence is not None else 0.85
        affected = affected_services or []
        tl = timeline or []
        cmt = commit

    # Always prepare deterministic fallback in advance
    fallback_text = _generate_deterministic_fallback(
        root_cause_service=root_cause_service,
        confidence=conf_val,
        affected_services=affected,
        timeline=tl,
        commit=cmt,
        independent_failures=independent_failures,
    )

    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        logger.info("GEMINI_API_KEY not set; using deterministic explanation fallback.")
        return fallback_text

    # Build prompt for Gemini narration
    timeline_summary = "; ".join([f"{e.timestamp}: [{e.service}] {e.event}" for e in tl[:5]])
    commit_summary = f"Commit {cmt.sha} (\"{cmt.message}\" by {cmt.author})" if cmt else "None"
    independent_str = f"Independent concurrent failure: {', '.join(independent_failures)}" if independent_failures else "None"

    prompt = (
        "You are an SRE incident narration assistant for Cascade RCA. "
        "The causal engine has already determined the authoritative root cause. "
        "Summarize the incident in exactly 2-3 concise, professional sentences for an engineer. "
        "Do NOT change the root cause, do NOT speculate on different causes, and adhere strictly to this evidence:\n"
        f"- Primary Root Cause: {root_cause_service} (confidence: {conf_val:.2f})\n"
        f"- Affected Cascaded Services: {', '.join(affected) if affected else 'None'}\n"
        f"- {independent_str}\n"
        f"- Key Timeline: {timeline_summary or 'Standard cascade onset'}\n"
        f"- Correlated Git Commit: {commit_summary}\n"
    )

    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={api_key.strip()}"
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

    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    if text_parts and "text" in text_parts[0]:
                        explanation = text_parts[0]["text"].strip()
                        if explanation:
                            return explanation
            else:
                logger.warning(
                    "Gemini API returned status %d: %s",
                    response.status_code,
                    response.text[:100],
                )
    except Exception as e:
        logger.error("Gemini API call failed: %s; falling back to deterministic explanation", e)

    return fallback_text
