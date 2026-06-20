import logging
from collections import deque
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from price_review.agent import build_agent
from price_review.agent.llm import format_llm_error
from price_review.api.logging_setup import setup_logging
from price_review.api.schemas import RulesRequest, ValidateRequest
from price_review.api.trace import extract_trace
from price_review.config import get_settings
from price_review import paths
from price_review.scenarios import load_scenarios
from price_review.tools import get_escalations_snapshot

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Price Review Agent")
app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")

_HISTORY_MAXLEN = 50
_history: deque = deque(maxlen=_HISTORY_MAXLEN)
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def _read_rules() -> str:
    try:
        return paths.RULES_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read rules from %s: %s", paths.RULES_PATH, exc)
        raise


def _write_rules(content: str) -> None:
    try:
        paths.RULES_PATH.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write rules to %s: %s", paths.RULES_PATH, exc)
        raise


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        return (paths.STATIC_DIR / "app.html").read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read app.html: %s", exc)
        return HTMLResponse("UI unavailable.", status_code=500)


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "provider": "gemini",
        "model": settings.llm_model,
        "has_key": settings.has_llm_key,
        "market_context": "desk_demo_fixtures",
        "optional_finnhub_enabled": settings.optional_finnhub_enabled,
    }


@app.get("/rules")
def read_rules():
    return {"rules": _read_rules()}


@app.post("/rules")
def write_rules(req: RulesRequest):
    _write_rules(req.rules)
    logger.info("Rules updated.")
    return {"status": "saved"}


@app.post("/validate")
def validate(req: ValidateRequest):
    logger.info("Review request: %s", req.query[:120])
    try:
        agent = get_agent()
    except Exception as exc:
        logger.exception("Failed to build agent")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": req.query}]})
        final_answer, steps = extract_trace(result["messages"])
        _history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": req.query,
                "final_answer": final_answer,
                "steps": steps,
            }
        )
        logger.info("Review completed (%d steps).", len(steps))
        return {"final_answer": final_answer, "steps": steps}
    except Exception as exc:
        logger.exception("Agent invocation failed")
        return JSONResponse(status_code=500, content={"error": format_llm_error(exc)})


@app.get("/escalations")
def get_escalations():
    return {"escalations": get_escalations_snapshot()}


@app.get("/scenarios")
def get_scenarios(featured: bool | None = None):
    catalog = load_scenarios()
    scenarios = catalog.scenarios
    if featured is not None:
        scenarios = [item for item in scenarios if item.featured == featured]
    return {
        "count": len(scenarios),
        "scenarios": [item.model_dump() for item in scenarios],
    }


@app.get("/history")
def get_history():
    return {"count": len(_history), "results": list(_history)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("price_review.api.app:app", host="0.0.0.0", port=get_settings().port)
