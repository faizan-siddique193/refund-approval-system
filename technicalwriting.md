# Refund Approval System Technical Docs

## Architecture
- LangGraph state machine
- FastAPI REST API
- SQLite persistence
- Pydantic validation
- Groq LLM inference

## Components
- Agent: LangGraph topology
- Policy: Deterministic rules
- LLM: Advisory role
- Database: Audit logs, state tracking

## Workflows
- Auto-Approve: < $50, zero risk
- Reviewer: $50-$500, medium risk
- Manager: > $500, high risk
- Decline: Fraud, mismatch

## Endpoints
- POST /refunds: Submit
- GET /refunds/{id}: Status
- POST /approvals/{id}: Approve
- GET /refunds/{id}/audit: Audit logs

## Security
- Policy overrides LLM
- Strict cryptographic parameter binding
- Duplicate execution blocking
- Exponential backoff retries

## Setup
- uv sync
- source .venv/bin/activate
- copy .env.example to .env
- uv run uvicorn refund_approval_system.api:app --reload --port 8000
- uv run pytest
