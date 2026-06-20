---
title: AI Price Review Agent
colorFrom: purple
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# AI Price Review Agent

ReAct agent that reviews end-of-day prices against desk rules. FastAPI UI, Google Gemini, synthetic prices, **deterministic desk market context** for stage demos.

![CI](https://github.com/yassir-elkobi/ai-price-review-agent/actions/workflows/ci.yml/badge.svg)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # GOOGLE_API_KEY required
```

**Optional live news:** set `OPTIONAL_FINNHUB_API_KEY` to append real Finnhub headlines - results may diverge from announced expected outcomes.

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
├── api/          FastAPI app, schemas, trace
├── agent/        LangGraph ReAct agent + Gemini client
├── config/       Settings
├── market/       Desk demo fixtures + optional Finnhub
├── scenarios/    Demo scenario catalog
├── tools/        Agent tools
└── paths.py      Data file locations
data/
├── prices.json
├── rules.txt
├── scenarios.json
└── market_context.json   # curated desk events (deterministic demo)
static/           UI (app.html, css/, js/, svg/)
```

Rules in `data/rules.txt` are read at runtime. Edit them in the UI without changing code.

## Docker

```bash
docker build -t ai-price-review-agent .
docker run -p 7860:7860 -e GOOGLE_API_KEY=... ai-price-review-agent
```

## Deploy (Hugging Face Space)

Live Space: https://huggingface.co/spaces/yassir-elkobi/ai-price-review-agent

On every push to `main`, CI runs tests, builds Docker, then uploads to the Space.

**GitHub repo secret** (Settings → Secrets → Actions):

| Secret | Purpose |
|--------|---------|
| `HF_TOKEN` | Write token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |

**Space secrets** (Settings → Secrets):

| Secret | Purpose |
|--------|---------|
| `GOOGLE_API_KEY` | Gemini API key (required) |
| `OPTIONAL_FINNHUB_API_KEY` | Optional - omit for deterministic stage demo |

Verify: `curl https://yassir-elkobi-ai-price-review-agent.hf.space/health` → `"optional_finnhub_enabled": false`
