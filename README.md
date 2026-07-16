---
title: AI Price Review Agent
colorFrom: purple
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# AI Price Review Agent

ReAct agent for **Let's Talk**, a two-part internal series on AI agents. Reviews
end-of-day prices instrument-by-instrument against desk rules that can change
at runtime.

- **Session 1** (*Comprendre et concevoir un agent*): solo ReAct agent, stateless, one instrument at a time.
- **Session 2** (*Du solo au système fiable*, this branch): the same agent grows memory, a multi-agent supervisor, an evaluation harness, and a prompt-injection guard.

![CI](https://github.com/yassir-elkobi/ai-price-review-agent/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/version-2.0.0-blue)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # ANTHROPIC_API_KEY required, everything else optional
```

## Run

```bash
uvicorn app:app --reload --port 7860
```

Open http://localhost:7860

## Tests

```bash
pytest tests/ -q
```

## Layout

```
price_review/
├── agent/          ReAct agent + Claude (Sonnet 5)
├── api/            FastAPI app, request/response schemas, trace extraction
├── tools/          6 agent tools (4 from Session 1 + 2 memory tools)
├── market/         Desk demo fixtures (market_context.json)
├── memory/         Qdrant decision history (RAG) + Neo4j sector graph (GraphRAG)
├── orchestration/  Supervisor + parallel asset-class sub-agents (LangGraph Send)
├── evaluation/     Scenario replay harness + scoring
├── security/       SecurityLayer (prompt-injection guard)
├── decisions.py    Shared parser: agent free text -> per-instrument verdicts
├── prices.py       Shared reader for data/prices.json
└── scenarios/      7 live demo presets + expected_outcomes
data/
├── prices.json           # 6 instruments
├── market_context.json   # news fixtures (demo target for live injection)
├── sector_graph.json      # GraphRAG local fallback / Neo4j seed
├── rules.txt              # editable at runtime
└── scenarios.json         # used by both the UI presets and the evaluation harness
docs/
└── MAESTRO.md              # layer-by-layer risk analysis
static/                     UI (4 tabs: Revue solo, Book, Évaluation, Sécurité)
```

## Memory (RAG + GraphRAG)

- `get_decision_history(instrument_id)` - recalls past desk decisions from **Qdrant**.
  Uses Qdrant Cloud when `QDRANT_URL` is set, otherwise an in-process in-memory
  Qdrant instance (zero setup, fully offline). Embeddings are a deterministic
  local hashing function (`price_review/memory/embeddings.py`) - no external
  model/API needed.
- `get_sector_context(instrument_id)` - GraphRAG over instrument/sector/event
  relations from **Neo4j Aura** (`NEO4J_URI` set) or the local
  `data/sector_graph.json` fixture otherwise. Answers "did a correlated peer
  or sector-wide event explain this move?" even with no direct news.
- Every `/validate` call best-effort persists parsed decisions back into
  Qdrant so later reviews can recall precedent.

## Multi-agent supervisor

`POST /validate/book` runs the whole book through a supervisor that fans out
to per-asset-class sub-agents (Equities, Fixed Income, FX) in **parallel**
via LangGraph's `Send` API, then a Synthesis agent aggregates the verdicts
into one desk report. See `price_review/orchestration/supervisor.py` and the
"Book" tab in the UI.

## Evaluation harness

`POST /evaluation/run` (UI tab "Évaluation") replays every scenario in
`data/scenarios.json` against the live agent, checking both **decision
correctness** (verdict + rule vs. `expected_outcomes`) and **completeness**
(was `escalate_to_human` actually called for every expected ESCALATE?).
Scored globally, per rule, and per asset class.

## Security (prompt injection)

`SecurityLayer` (`price_review/security/prompt_guard.py`) scans both the
incoming user query and every tool output (market context, decision history,
sector graph) for known injection patterns, redacting suspicious content and
forcing an escalation instead of letting it steer a decision. Toggle it live
via `GET/POST /security` or the "Sécurité" tab - with it off, an
injected instruction (e.g. edited into `data/market_context.json`) can steer
the unprotected agent. See `docs/MAESTRO.md` for the full layer-by-layer risk
analysis.

## Docker

```bash
docker build -t ai-price-review-agent .
docker run -p 7860:7860 -e ANTHROPIC_API_KEY=... ai-price-review-agent
```

## Deploy (Hugging Face Space)

Live Space: https://huggingface.co/spaces/yassir-elkobi/ai-price-review-agent

| Secret | Where | Purpose |
|--------|-------|---------|
| `HF_TOKEN` | GitHub Actions | CI deploy |
| `ANTHROPIC_API_KEY` | Space secrets | Claude (required) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Space secrets | Decision history (optional - falls back to in-memory) |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Space secrets | Sector graph (optional - falls back to local fixture) |
