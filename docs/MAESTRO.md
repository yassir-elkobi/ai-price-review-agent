# Risk Analysis (MAESTRO-style, layer by layer)

This is a layer-by-layer risk analysis of the price review agent, in the spirit of the
MAESTRO framework for agentic AI (Model, Application/Ecosystem, System, Threat, Runtime,
Operations). It is scoped to the four layers that actually matter for this system: **Model**,
**Tool**, **Data**, and **Orchestration**. Each entry lists the risk, why it applies here,
the mitigation actually implemented, and where to see it in code or in the demo.

## 1. Model layer

**Risk: the LLM treats untrusted content as instructions.**
Any text that reaches the model - a user query, a tool result, a peer agent's answer - is,
from the model's point of view, just more text in its context window. Nothing stops it from
interpreting "ignore previous instructions" inside a news headline as an actual instruction
rather than as data to reason about.

- *Mitigation*: step 7 of the system prompt (`price_review/agent/builder.py`) is an explicit,
  standing instruction to treat all tool output as data, never as instructions, and to
  escalate rather than act whenever content looks command-like. This is a model-layer
  mitigation - it relies on instruction-following, so it is necessarily probabilistic, not a
  hard guarantee. It is backed up by the pattern-based `SecurityLayer` below, which does not
  depend on the model's willingness to comply.
- *Demo*: run any of the five injection examples in the Sécurité tab with the protection
  toggle off. The unprotected agent still resists the two direct-command examples most of
  the time (Claude's own training already pushes back on "ignore previous instructions"),
  but is meaningfully more likely to be swayed by the social-engineering, hidden-comment, and
  escalation-suppression examples, which imitate legitimate content instead of issuing a
  command.

**Risk: unreliable structured output from free text.**
The agent's final answer is free-form markdown, not a function call - there's no guaranteed
schema. Verdict and rule number have to be recovered by regex (`price_review/decisions.py`),
which is inherently fragile against phrasing drift.

- *Mitigation*: the system prompt hard-codes an exact final line format
  (`Decision: <VERDICT> (Rule <N>)`), and the parser is anchored on that literal label rather
  than scanning loosely for any APPROVED/REJECTED/ESCALATE keyword, with a proximity-based
  fallback for anything looser. This was tightened several times during evaluation-harness
  testing after real parsing failures (verbose multi-candidate answers, terse single-line
  answers with no ticker repeated, ambiguous rule attribution).
- *Residual risk*: this is still text parsing, not a contract. A sufficiently different
  phrasing can still slip past both regexes. The evaluation harness exists specifically to
  catch this class of regression before a demo, not to eliminate it.

## 2. Tool layer

**Risk: a tool call can be skipped, silently changing the outcome.**
Nothing forces the agent to call `escalate_to_human` before writing "ESCALATE," or to call
`get_price_data` before deciding at all. A model that "knows" the answer from context alone
could produce a plausible-looking verdict with no audit trail behind it.

- *Mitigation*: the evaluation harness's completeness check
  (`price_review/evaluation/runner.py::run_scenario`) specifically verifies that
  `escalate_to_human` was actually invoked for every scenario expecting ESCALATE, independent
  of whether the free-text verdict says the right thing. A scenario that states the right
  decision but skips the tool call is scored `amber`, not `pass`. Every tool docstring in
  `price_review/tools/registry.py` also states explicit "WHEN TO CALL" / "REQUIRED" language,
  since docstring precision measurably affects how reliably the model calls tools in order.

**Risk: an over-broad or malformed argument breaks a downstream lookup.**
All five instrument-scoped tools take a free-text `instrument_id` the model constructs itself.

- *Mitigation*: `_validate_instrument_id` (`price_review/tools/registry.py`) enforces
  non-empty input and a length cap before any lookup runs, and every lookup does a
  case-insensitive exact match against the known instrument list rather than a fuzzy or
  partial match, so a malformed id fails closed with a plain "not found" message instead of
  matching the wrong instrument.

## 3. Data layer

**Risk: a tool's data source is itself the injection vector.**
This is the core of the security demo. `market_context.json`, the Qdrant decision-history
store, and the Neo4j/local sector graph are all plausible places for a real desk to plant
compromised content - a wire headline, a poisoned internal note, a manipulated audit
record - and the agent reads all three as ordinary tool output with no built-in reason to
distrust them.

- *Mitigation*: `guard_tool_output` (`price_review/security/prompt_guard.py`) scans the text
  returned by `get_market_context`, `get_decision_history`, and `get_sector_context` before it
  reaches the model, using a pattern list that has grown to cover direct commands
  ("ignore previous instructions"), role hijacking ("you are now..."), social engineering
  disguised as a legitimate internal sign-off ("already reviewed," "pre-approved," "no
  further escalation needed"), hidden instructions inside an HTML comment embedded in
  otherwise-plausible content, and escalation suppression ("do not call escalate_to_human,"
  "without triggering the human queue"). A match redacts the content and replaces it with an
  explicit instruction to treat the instrument as sensitive under rule 5 and escalate -
  the guard does not try to "fix" the decision, it removes the tainted input from the
  reasoning entirely and forces a human into the loop.
- *Toggle*: `SecurityLayer` is deliberately runtime-toggleable (`GET/POST /security`, the
  Sécurité tab) specifically so the same injected content can be shown twice: once redacted
  (protected) and once reaching the model unfiltered (unprotected), which is the actual
  before/after the demo needs.
- *Residual risk*: this is pattern matching, not semantic understanding - it catches known
  phrasings, not arbitrary paraphrases of the same attack. It is intentionally presented as
  one layer of defense, not the only one; the model-layer instruction in section 1 is the
  fallback when a novel phrasing slips past the patterns.

**Risk: the user's own query is an injection vector, not just tool output.**
A user-facing endpoint has to assume the query itself may carry the same kind of
instruction-override content as a poisoned data source.

- *Mitigation*: `guard_user_query` runs the same pattern scan against the incoming request in
  `POST /validate`, before the agent is even built, and returns a plain 400 refusal instead
  of ever handing the text to the model.

## 4. Orchestration layer

**Risk: a compromised sub-agent output can steer the layer above it.**
`POST /validate/book` fans out to per-asset-class sub-agents in parallel (LangGraph `Send`)
and then feeds every branch's final answer into a Synthesis LLM call that aggregates them
into one desk report. Each branch answer is itself LLM-generated free text - if a branch had
been fed tainted tool data that slipped through (or if the guard were disabled), its answer
could carry injected content one level further up, into the Synthesis prompt, where it would
be trusted as "data already decided by a desk" rather than screened again.

- *This was a real, documented gap*: earlier versions of `_synthesis`
  (`price_review/orchestration/supervisor.py`) concatenated branch answers into the Synthesis
  prompt with no re-screening step, meaning the security boundary enforced at the tool layer
  did not automatically extend to the orchestration layer above it.
- *Mitigation*: every branch answer is now passed through `guard_tool_output` again,
  labelled `branch_synthesis_input`, immediately before being included in the Synthesis
  prompt - so a branch's answer is screened both when its own tools returned data and a
  second time before it crosses the sub-agent -> supervisor boundary. The Synthesis prompt
  itself also carries an explicit instruction to treat the verdicts below it as data to
  summarize, never as instructions, mirroring the model-layer mitigation in section 1.
- *Demo*: the escalation-suppression injection example, run through the Book tab instead of
  solo review, should still surface ESCALATE at both the branch level and in the aggregated
  synthesis report - if the Synthesis report ever undercounted or dropped an escalation that
  its own branch reported, that would indicate this boundary had regressed.

**Risk: parallel branches share no synchronization, so state assumptions can silently break.**
Each asset-class branch runs its own fresh sub-agent and its own tool calls; nothing forces
them to agree on rules, memory, or fixture state mid-run.

- *Mitigation*: this is accepted as an intentional design constraint rather than "solved" -
  each branch reads the same runtime-editable rules and fixtures independently on every
  invocation (no branch caches state across the graph), so a live rules edit or fixture reset
  applies uniformly to every branch of the next run. There is no cross-branch mutable state to
  desynchronize in the first place.

## Summary table

| Layer | Primary risk | Mitigation | Where |
|---|---|---|---|
| Model | Untrusted content read as instructions | Standing "treat tool output as data" instruction | `agent/builder.py` step 7 |
| Model | Unreliable free-text verdict parsing | Anchored regex + strict output format + eval harness | `decisions.py`, `evaluation/runner.py` |
| Tool | Skipped required tool call | Completeness check independent of stated verdict | `evaluation/runner.py` |
| Tool | Malformed/oversized instrument id | Input validation, exact case-insensitive match | `tools/registry.py` |
| Data | Poisoned market context / memory / sector data | Pattern-based redaction before the model sees it | `security/prompt_guard.py` |
| Data | Poisoned user query | Same pattern scan on the request itself | `security/prompt_guard.py` |
| Orchestration | Compromised branch answer reaching Synthesis | Re-guard every branch answer before Synthesis | `orchestration/supervisor.py` |
| Orchestration | Cross-branch state desync | No shared mutable state between branches by design | `orchestration/supervisor.py` |
