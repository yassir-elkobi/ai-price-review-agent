# AI Price Review Agent

ReAct agent for **Let's Talk - Partie 1** (*Comprendre et concevoir un agent*). Reviews end-of-day prices instrument-by-instrument against desk rules that can change at runtime.

![CI](https://github.com/yassir-elkobi/ai-price-review-agent/actions/workflows/ci.yml/badge.svg)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # GOOGLE_API_KEY required
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
├── agent/        ReAct agent + Gemini
├── api/          FastAPI, trace
├── tools/        4 agent tools
├── market/       Desk demo fixtures
└── scenarios/    7 live demo presets
data/
├── prices.json           # 6 instruments
├── market_context.json
├── rules.txt
└── scenarios.json
static/           UI
```

## Docker

```bash
docker build -t ai-price-review-agent .
docker run -p 7860:7860 -e GOOGLE_API_KEY=... ai-price-review-agent
```

## Deploy (Hugging Face Space)

Live Space: https://huggingface.co/spaces/yassir-elkobi/ai-price-review-agent

| Secret | Where | Purpose |
|--------|-------|---------|
| `HF_TOKEN` | GitHub Actions | CI deploy |
| `GOOGLE_API_KEY` | Space secrets | Gemini (required) |
