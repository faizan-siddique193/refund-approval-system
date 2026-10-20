# Refund Approval System

## Project Overview

The Refund Approval System is a reliable, secure, and highly deterministic human-in-the-loop workflow engine for processing customer refund requests. By leveraging the advanced LangGraph framework, the system blends intelligent LLM analysis with a strict, code-based policy engine to ensure customer support operations can scale safely without compromising on compliance or financial security.

## Problem Statement

Automating financial transactions via LLMs introduces severe safety and security risks. LLMs can hallucinate context, be manipulated via prompt injection, or make unreliable decisions in complex scenarios. The core problem is scaling refund operations via AI while guaranteeing that the AI cannot independently authorize large or risky transactions, bypass security rules, or process fraudulent requests. 

This project solves that by confining the LLM to a strictly advisory and context-gathering role. A deterministic rules engine acts as the absolute authority, dictating if a refund auto-approves, requires human intervention (Reviewer/Manager), or must be declined outright. 

## Architecture

The system is designed as a state machine using LangGraph. The graph dictates the flow of execution, state persistence guarantees durability, and a mock payment processor acts as the sink.

```mermaid
graph TD
    A[Start] --> B[Fetch Context]
    B --> C{Context Complete?}
    C -- No --> D[Escalate]
    C -- Yes --> E[Analyze with LLM]
    E --> F[Evaluate Policy]
    F --> G{Route Action}
    
    G -- Decline --> H[Decline Refund]
    G -- Needs Info --> I[Needs Information]
    G -- Escalate --> D
    
    G -- Create Approval --> J[Create Approval Request]
    J --> K[Wait for Human Approval]
    K --> L{Approval Decision}
    L -- Rejected --> M[Reject]
    L -- Approved --> N[Execute Refund]
    
    G -- Auto-Approve --> N
    
    N --> O{Execution Success?}
    O -- Yes --> P[Completed]
    O -- No --> Q[Failed]
```

## Folder Structure

```
refund_approval_system/
├── src/
│   └── refund_approval_system/
│       ├── agent/         # LangGraph topology and state logic
│       ├── api/           # FastAPI entrypoints
│       ├── db/            # SQLite database and repository access
│       ├── edges/         # Graph routing edges (linear, conditional, terminal)
│       ├── models/        # Pydantic data models for typed schemas
│       ├── nodes/         # Graph node implementations
│       ├── prompts/       # LLM prompt templates
│       ├── tools/         # External dependency integrations
│       ├── policy.py      # Deterministic rules engine
│       └── __init__.py
├── tests/                 # Comprehensive Pytest suite
│   ├── test_acceptance.py # End-to-end acceptance tests
│   ├── test_api.py            
│   ├── test_workflow.py   # State machine transitions
│   └── ...
├── .env.example
├── pytest.ini
└── README.md
```

## Technology Choices

* **Language:** Python 3.10+
* **Workflow Engine:** LangGraph (for stateful, checkpointed agent workflows)
* **Web Framework:** FastAPI (for highly performant REST APIs)
* **LLM Provider:** Groq (for extremely fast, structured inference)
* **Data Validation:** Pydantic (for rigid state typing and LLM structured output)
* **Testing:** Pytest (for exhaustive deterministic test coverage)
* **Persistence:** SQLite (for zero-setup, durable audit logs and state checkpointing)

## Setup

1. **Install Dependencies:**
   The project uses `uv` for dependency management.
   ```bash
   uv sync
   ```
2. **Activate Virtual Environment:**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

## Environment Variables

Copy `.env.example` to `.env` and configure:
```ini
GROQ_API_KEY=gsk_your_groq_api_key
LLM_MODEL=openai/gpt-oss-20b
DATABASE_PATH=refund_approval.db
```

## Running the API

Start the FastAPI server:
```bash
uv run uvicorn refund_approval_system.api:app --reload --port 8000
```

## API Endpoints

* `POST /refunds` - Submit a new refund request.
* `GET /refunds/{refund_id}` - Check the status of a refund.
* `POST /approvals/{approval_id}` - Process a pending human approval.
* `GET /refunds/{refund_id}/audit` - Fetch the audit trail for a refund.

## Example Requests

**Submit a refund request:**
```bash
curl -X POST http://localhost:8000/refunds \
  -H "Content-Type: application/json" \
  -d '{
    "refund_id": "REF-123",
    "customer_id": "CUS-001",
    "order_id": "ORD-1001",
    "amount": 45.0,
    "reason": "Item arrived damaged."
  }'
```

**Process an approval:**
```bash
curl -X POST http://localhost:8000/approvals/APP-XYZ \
  -H "Content-Type: application/json" \
  -d '{
    "approval_id": "APP-XYZ",
    "decision": "approved",
    "reviewer_id": "REV-01",
    "reviewer_role": "reviewer",
    "refund_id": "REF-123",
    "order_id": "ORD-1001",
    "amount": 45.0
  }'
```

## Approval Workflow

1. **Auto-Approve:** Low-risk, low-value refunds (under $50) bypass human review and execute immediately.
2. **Reviewer Approval:** Mid-value ($50 - $500) or mildly risky refunds pause execution and generate an approval request requiring a `REVIEWER` role.
3. **Manager Approval:** High-value (over $500) or highly risky refunds pause execution and require a `MANAGER` role.
4. **Execution:** Once the human submits an approval decision matching the required request parameters (`refund_id`, `order_id`, `amount`, and required role level), the graph validates the record and executes the payment.

## Policy Rules

The `policy.py` engine defines strict numeric rules for routing:
* **Amount < $50:** Auto-approved (if no risk flags exist).
* **Amount $50 - $500:** Requires `REVIEWER` approval.
* **Amount > $500:** Requires `MANAGER` approval.

## Risk Rules

* **Risk A (Repeated Refunds):** Customer has ≥3 refunds in the last 30 days. Forces at least `REVIEWER` approval.
* **Risk B (Mismatch):** The `customer_id` does not own the `order_id`. Immediately routes to `ESCALATED`.
* **Risk C (Missing Evidence):** Refund lacks required photographic evidence. Forces at least `REVIEWER` approval.
* **Risk D (Suspicious Activity):** Customer account flagged for fraud. Forces `MANAGER` approval.

## Failure Handling

1. **Tool/Dependency Failure:** External calls (e.g. `get_order_details`) retry automatically up to 3 times in a retry loop. If failure persists, the workflow logs the error and safely `ESCALATES` rather than guessing missing context.
2. **Execution Failure:** If the payment gateway crashes during execution, the refund is explicitly flagged as `FAILED`. It is never falsely reported as `COMPLETED`.

## Security

* **Prompt Injection Defense:** The LLM's output (`RefundDecision`) only provides intent analysis. The deterministic policy engine intercepts any LLM hallucination or prompt injection bypass attempt.
* **Approval Tampering:** The system deterministically verifies that `amount`, `order_id`, and `refund_id` strictly match the pending database record through parameter equality checks. Expired approvals, insufficient roles, or modified amounts are rejected instantly.
* **Duplicate Execution:** A final check on the SQLite DB ensures a refund cannot be executed twice.

## Documentation & Verification Evidence

* **Technical Architecture & Design Document:** See [`technicalwriting.md`](technicalwriting.md) for the complete 2–4 page architectural whitepaper detailing the LangGraph topology, deterministic policy engine, approval hardening, and security model.
* **Acceptance Scenarios A–G Traces:** See [`docs/scenario_traces.md`](docs/scenario_traces.md) for full execution traces, inputs, outputs, state transitions, and audit logs for all 7 evaluation scenarios.
* **Test Dataset (JSON):** See [`docs/test_data.json`](docs/test_data.json) for ready-to-use JSON payloads for API requests and human approvals covering Scenarios A–G.

## Testing

The system boasts 170 unit, integration, and acceptance tests covering policy logic, repository transactions, approval pause/resume, and API endpoints.

**Run the full Pytest test suite:**
```bash
uv run pytest
```

**Run the Acceptance Scenario Runner (A–G) directly:**
```bash
python -X utf8 docs/test_scenarios.py
```


