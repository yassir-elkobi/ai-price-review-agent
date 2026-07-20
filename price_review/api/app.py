import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from price_review import paths
from price_review.agent import build_agent
from price_review.agent.llm import format_llm_error
from price_review.api.logging_setup import setup_logging
from price_review.api.schemas import (
    BookRequest,
    MarketContextRequest,
    RulesRequest,
    SecurityToggleRequest,
    ValidateRequest,
)
from price_review.api.trace import extract_trace
from price_review.config import get_settings
from price_review.decisions import parse_decisions
from price_review.evaluation import run_all_scenarios
from price_review.market.context import clear_market_context_cache
from price_review.memory import record_decision, reset_decision_history
from price_review.orchestration import run_book_review
from price_review.scenarios import load_scenarios
from price_review.scenarios.loader import load_instrument_ids
from price_review.security import (
    get_security_events_snapshot,
    guard_user_query,
    is_security_enabled,
    set_security_enabled,
)
from price_review.tools import get_escalations_snapshot, reset_escalations

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Price Review Agent")
app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")

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


def _read_market_context() -> str:
    try:
        return paths.DESK_CONTEXT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read market context from %s: %s", paths.DESK_CONTEXT_PATH, exc)
        raise


def _write_market_context(content: str) -> None:
    json.loads(content)  # reject invalid JSON before touching the file
    try:
        paths.DESK_CONTEXT_PATH.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write market context to %s: %s", paths.DESK_CONTEXT_PATH, exc)
        raise
    clear_market_context_cache()


_DEFAULT_MARKET_CONTEXT = _read_market_context()


def _static_asset_version() -> int:
    try:
        return int(
            max(
                (paths.STATIC_DIR / "js" / "app.js").stat().st_mtime,
                (paths.STATIC_DIR / "css" / "app.css").stat().st_mtime,
            )
        )
    except OSError:
        return 0


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        html = (paths.STATIC_DIR / "app.html").read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read app.html: %s", exc)
        return HTMLResponse("UI unavailable.", status_code=500)
    version = _static_asset_version()
    html = html.replace('/static/js/app.js"', f'/static/js/app.js?v={version}"')
    html = html.replace('/static/css/app.css"', f'/static/css/app.css?v={version}"')
    return html


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "provider": "anthropic",
        "model": settings.llm_model,
        "has_key": settings.has_llm_key,
        "market_context": "desk_demo_fixtures",
        "memory": {
            "decision_history": "qdrant_cloud" if settings.has_qdrant_cloud else "in_memory",
            "sector_graph": "neo4j_aura" if settings.has_neo4j else "local_fixture",
        },
        "security_enabled": is_security_enabled(),
    }


@app.get("/rules")
def read_rules():
    return {"rules": _read_rules()}


@app.post("/rules")
def write_rules(req: RulesRequest):
    _write_rules(req.rules)
    logger.info("Rules updated.")
    return {"status": "saved"}


@app.get("/market-context")
def read_market_context():
    return {"content": _read_market_context(), "default": _DEFAULT_MARKET_CONTEXT}


@app.post("/market-context")
def write_market_context(req: MarketContextRequest):
    try:
        _write_market_context(req.content)
    except (OSError, json.JSONDecodeError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    logger.info("Market context fixtures updated.")
    return {"status": "saved"}


@app.post("/market-context/reset")
def reset_market_context():
    _write_market_context(_DEFAULT_MARKET_CONTEXT)
    logger.info("Market context fixtures reset to defaults.")
    return {"status": "reset", "content": _DEFAULT_MARKET_CONTEXT}


@app.post("/memory/reset")
def reset_memory():
    try:
        reset_decision_history()
    except Exception as exc:
        logger.exception("Failed to reset decision history")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    logger.info("Decision history memory wiped.")
    return {"status": "reset"}


def _reviewed_instrument_ids(steps: list[dict]) -> list[str]:
    ids: list[str] = []
    for step in steps:
        if step.get("kind") == "call" and step.get("tool") == "get_price_data":
            instrument_id = (step.get("args") or {}).get("instrument_id")
            if instrument_id and instrument_id not in ids:
                ids.append(instrument_id)
    return ids


def _record_decisions(final_answer: str, steps: list[dict]) -> None:
    try:
        known_ids = _reviewed_instrument_ids(steps) or list(load_instrument_ids())
        for parsed in parse_decisions(final_answer, known_ids):
            record_decision(parsed.instrument_id, parsed.decision, parsed.rule_ref)
    except Exception:  # noqa: BLE001 - memory persistence must never break a review
        logger.exception("Failed to record decision history for %s", final_answer[:60])


@app.post("/validate")
def validate(req: ValidateRequest):
    logger.info("Review request: %s", req.query[:120])

    allowed, refusal = guard_user_query(req.query)
    if not allowed:
        logger.warning("SecurityLayer blocked a request.")
        return JSONResponse(status_code=400, content={"error": refusal})

    try:
        agent = get_agent()
    except Exception as exc:
        logger.exception("Failed to build agent")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": req.query}]})
        final_answer, steps = extract_trace(result["messages"])
        logger.info("Review completed (%d steps).", len(steps))
        _record_decisions(final_answer, steps)
        return {"final_answer": final_answer, "steps": steps}
    except Exception as exc:
        logger.exception("Agent invocation failed")
        return JSONResponse(status_code=500, content={"error": format_llm_error(exc)})


@app.post("/validate/book")
def validate_book(req: BookRequest):
    logger.info("Book review request: %s", req.instrument_ids or "(whole book)")
    try:
        outcome = run_book_review(req.instrument_ids)
        logger.info("Book review completed (%d branches).", len(outcome["branches"]))
        return outcome
    except Exception as exc:
        logger.exception("Book review failed")
        return JSONResponse(status_code=500, content={"error": format_llm_error(exc)})


@app.get("/escalations")
def get_escalations():
    return {"escalations": get_escalations_snapshot()}


@app.post("/escalations/reset")
def reset_escalations_endpoint():
    reset_escalations()
    logger.info("Escalation queue cleared.")
    return {"status": "reset", "escalations": get_escalations_snapshot()}


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


@app.post("/evaluation/run")
def run_evaluation():
    try:
        agent = get_agent()
    except Exception as exc:
        logger.exception("Failed to build agent for evaluation")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    try:
        report = run_all_scenarios(agent)
        logger.info("Evaluation completed: %d/%d passed.", report.passed, report.total)
        return report.model_dump()
    except Exception as exc:
        logger.exception("Evaluation run failed")
        return JSONResponse(status_code=500, content={"error": format_llm_error(exc)})


@app.get("/security")
def get_security_status():
    return {"enabled": is_security_enabled(), "events": get_security_events_snapshot()}


@app.post("/security")
def set_security_status(req: SecurityToggleRequest):
    set_security_enabled(req.enabled)
    logger.info("SecurityLayer toggled to enabled=%s", req.enabled)
    return {"enabled": is_security_enabled()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("price_review.api.app:app", host="0.0.0.0", port=get_settings().port)
