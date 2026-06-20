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
                content = " ".join(
                    str(part.get("text", part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
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
