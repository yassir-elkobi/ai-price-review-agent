_NON_TEXT_BLOCK_TYPES = {"thinking", "redacted_thinking", "tool_use", "server_tool_use"}


def _extract_text(part) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if part.get("type") in _NON_TEXT_BLOCK_TYPES:
            return ""
        return part.get("text", "")
    return ""


def extract_trace(messages) -> tuple[str, list[dict]]:
    steps: list[dict] = []
    final_answer = ""

    for message in messages:
        mtype = getattr(message, "type", None)
        if mtype == "ai":
            for tool_call in getattr(message, "tool_calls", None) or []:
                steps.append(
                    {
                        "kind": "call",
                        "tool": tool_call.get("name", ""),
                        "args": tool_call.get("args", {}),
                    }
                )
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = " ".join(_extract_text(part) for part in content).strip()
            if content:
                final_answer = content
        elif mtype == "tool":
            steps.append(
                {
                    "kind": "result",
                    "tool": getattr(message, "name", ""),
                    "content": str(getattr(message, "content", "")),
                }
            )

    return final_answer, steps
