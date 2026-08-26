"""Optional local Llama helper. Performance is not a goal.

Reads a NetworkX node-link graph, runs the graph tools, then asks Ollama to phrase an answer.
If Ollama is unreachable the tools still run and a structured fallback is printed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pidgraph.agent import query
from pidgraph.extract.export import load_node_link

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
# ISA-style identifiers: MV-101, F-715A, MV-715-02A, PdIC-101.
_TAG = re.compile(r"[A-Za-z]{1,8}-\d+[A-Za-z0-9]*(?:-\d+[A-Za-z0-9]*)*")


def _models() -> list[dict]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    return payload.get("models") or []


def _chat_model(models: list[dict] | None = None) -> str | None:
    """Use a locally installed completion model. Embedding-only pulls are skipped."""
    models = _models() if models is None else models
    chat: list[str] = []
    for model in models:
        name = str(model.get("name") or model.get("model") or "")
        if not name:
            continue
        caps = model.get("capabilities") or []
        if caps and "completion" not in caps and "chat" not in caps:
            continue
        chat.append(name)
    wanted = os.environ.get("PIDGRAPH_LLM", "").strip()
    if wanted:
        for name in chat:
            if name == wanted or name.startswith(f"{wanted}:"):
                return name
    return chat[0] if chat else None


def _call_tools(graph, question: str) -> dict:
    hits: list[dict] = []
    token = None
    candidates = sorted({m.group(0) for m in _TAG.finditer(question)}, key=len, reverse=True)
    for match in candidates:
        found = query.find_tag(graph, match, limit=1)
        if found:
            token = found[0]["stable_key"]
            hits = found
            break
    if token is None:
        hits = query.find_tag(graph, question.strip(), limit=12)
        if hits:
            token = hits[0]["stable_key"]
    payload: dict = {"matches": hits, "question": question}
    if token:
        payload["neighbors"] = query.neighbors(graph, token)
        payload["upstream"] = query.walk(graph, token, "upstream")
        payload["downstream"] = query.walk(graph, token, "downstream")
        payload["describe"] = query.describe(graph, token)
    return payload


def _ollama_phrase(evidence: dict, model: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer questions about a piping and instrumentation diagram using "
                        "ONLY the JSON evidence. Do not invent tags or connections. Edge "
                        "direction is assembly order, not process flow; say so when talking "
                        "about upstream or downstream. If fluid (gas/liquid) is not in the "
                        "evidence, say you do not know. Quote tags that appear in the evidence."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(evidence, default=str)[:12000],
                },
            ],
        }
    ).encode()
    request = urllib.request.Request(
        f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode())
    return payload.get("message", {}).get("content") or json.dumps(evidence, indent=2)


def _fallback_answer(evidence: dict, reason: str) -> str:
    """Structured reply when Ollama is missing or errors. Tools have already run."""
    note = (
        "Edge direction is assembly order along conductors, not verified process flow."
    )
    matches = evidence.get("matches") or []
    if not matches:
        return f"{reason} No tags in the graph matched this question. {note}"
    described = evidence.get("describe") or matches[0]
    neighbours = evidence.get("neighbors") or {}
    body = {
        "match": described,
        "neighbors": neighbours,
        "upstream": evidence.get("upstream"),
        "downstream": evidence.get("downstream"),
        "note": note,
    }
    return f"{reason}\n" + json.dumps(body, indent=2, default=str)


def ask(graph_path: str | Path, question: str) -> dict:
    graph = load_node_link(graph_path)
    evidence = _call_tools(graph, question)
    models = _models()
    model = _chat_model(models) if models else None
    if model:
        try:
            evidence["answer"] = _ollama_phrase(evidence, model)
            evidence["ollama"] = True
            evidence["model"] = model
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            detail = type(exc).__name__
            if isinstance(exc, urllib.error.HTTPError):
                detail = f"HTTP {exc.code}"
            evidence["answer"] = _fallback_answer(evidence, f"Ollama did not respond ({detail}).")
            evidence["ollama"] = False
    else:
        evidence["ollama"] = False
        reason = (
            "Ollama is running but has no chat model."
            if models
            else "Ollama is not running."
        )
        evidence["answer"] = _fallback_answer(evidence, reason)
    return evidence


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: python -m pidgraph.agent <graph.nodelink.json> <question>", file=sys.stderr)
        return 2
    result = ask(args[0], args[1])
    print(
        json.dumps(
            {
                "answer": result.get("answer"),
                "ollama": result.get("ollama"),
                "model": result.get("model"),
                "matches": result.get("matches"),
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
