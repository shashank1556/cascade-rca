# Cascade RCA — Team Architecture Contract
Version: 1.0 — LOCKED

## 1. Core flow
Telemetry → Service Dependency Graph → Cascade Detection → Causal Scoring → Root Cause → GitHub Commit/Diff → Human-readable Explanation.

## 2. Source of truth
Before coding, every developer/coding agent MUST read this file and `backend/contracts.py`.
Do not invent alternative module names, public function names, API endpoints, service names, or JSON fields.
Do not rename contract items without agreement from the integration owner.
Inspect current code before creating files.

## 3. Locked repository structure
cascade-rca/
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── contracts.py
│   ├── telemetry.py
│   ├── simulator.py
│   ├── rca_engine.py
│   ├── github_service.py
│   └── gemini_service.py
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       └── components/
│           ├── ServiceGraph.tsx
│           ├── IncidentPanel.tsx
│           ├── RCAResult.tsx
│           ├── Timeline.tsx
│           └── CommitCard.tsx
├── tests/
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
└── README.md

Do not create duplicates such as `root_cause.py`, `rca.py`, `git_service.py`, etc.

## 4. Locked module ownership
Backend/RCA: telemetry.py, simulator.py, rca_engine.py, models.py, contracts.py
Frontend: frontend/
External services: github_service.py, gemini_service.py
Integration owner: main.py and final integration
Testing owner: tests/

Everyone may read all code. Avoid modifying another owner's module unless coordinated.

## 5. Locked public functions
telemetry.py:
- generate_telemetry(...)
- get_recent_telemetry(...)

simulator.py:
- simulate_payment_failure(...)
- simulate_database_latency(...)
- simulate_notification_failure(...)

rca_engine.py:
- build_service_graph(...)
- detect_cascade(...)
- calculate_causal_score(...)
- analyze_incident(...)

github_service.py:
- get_recent_commits(...)
- get_commit_diff(...)

gemini_service.py:
- generate_explanation(...)

Local variable names inside functions may differ. Public keyword parameters and return models must follow `contracts.py`.

Do not create competing public aliases such as `find_root_cause()`, `run_rca()`, or `root_cause_analysis()`.

## 6. Locked API endpoints
POST /simulate/payment-failure
POST /simulate/database-latency
POST /simulate/notification-failure
GET /graph
GET /incident/{incident_id}
GET /rca/{incident_id}
GET /health

## 7. Telemetry fields — exact names
timestamp
service
trace_id
span_id
parent_span_id
latency_ms
status_code

Example:
{
  "timestamp": "2026-09-18T10:00:01Z",
  "service": "payment-service",
  "trace_id": "trace-001",
  "span_id": "span-101",
  "parent_span_id": "span-100",
  "latency_ms": 850,
  "status_code": 500
}

Prototype uses OTel-compatible/OTel-shaped telemetry. It does not claim to implement a complete production OTel Collector.

## 8. Locked service names
api-gateway
user-service
order-service
product-service
payment-service
notification-service
database

## 9. Locked dependency graph
api-gateway → user-service
api-gateway → order-service
api-gateway → product-service
order-service → payment-service
order-service → notification-service
payment-service → database

## 10. RCA result contract
{
  "incident_id": "INC-001",
  "status": "resolved",
  "root_cause": {
    "service": "payment-service",
    "confidence": 0.91
  },
  "affected_services": ["order-service", "api-gateway"],
  "timeline": [],
  "commit": null,
  "explanation": ""
}

Required top-level fields:
incident_id, status, root_cause, affected_services, timeline, commit, explanation

Root cause fields:
service, confidence

Confidence is a prototype score from 0.0–1.0, NOT a statistically calibrated probability.

## 11. Commit contract
When GitHub correlation succeeds:
{
  "sha": "8f31c2a",
  "message": "Update payment timeout handling",
  "url": "https://github.com/...",
  "author": "..."
}

`commit` may be null if no matching commit is found or GitHub is unavailable.
Never expose GitHub tokens to the frontend.

## 12. Explanation contract
Gemini receives structured RCA evidence and returns concise narration.
The RCA engine remains authoritative for root-cause candidate, confidence, affected services and timeline.
Gemini is only the explanation layer.
If Gemini fails, return a deterministic fallback explanation. The app must remain usable without Gemini.

## 13. Failure scenarios
Payment failure: payment-service → order-service → api-gateway
Database latency: database → payment-service → order-service → api-gateway
Notification failure: notification-service fails without becoming the root cause of unrelated API/order failures.

## 14. Frontend rule
Frontend consumes backend contracts. It may format/display data but must not implement a second RCA algorithm.

## 15. Environment variables
GITHUB_TOKEN
GITHUB_OWNER
GITHUB_REPO
GEMINI_API_KEY

Commit `.env.example`; NEVER commit `.env`.

## 16. Integration rules
Before pushing:
- run backend tests
- run frontend build
- verify API contract
- verify existing demo scenario

Do not commit secrets, node_modules, caches, or local databases.

## 17. MVP definition of done
1. Dashboard opens with healthy topology.
2. User clicks Inject Payment Failure.
3. Cascade appears.
4. Ranked RCA result appears.
5. Causal timeline appears.
6. GitHub commit correlation appears.
7. Human-readable explanation appears.
8. Explanation still works if Gemini is unavailable.

## 18. Coding-agent instruction
Read ARCHITECTURE.md and backend/contracts.py first.
Inspect current repository.
Make the smallest necessary changes.
Preserve locked names/contracts.
Do not silently redesign the architecture.
Report changed files and tests performed.
