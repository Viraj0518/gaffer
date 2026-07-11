"""Local web UI: a small FastAPI app around the coach agent.

Run with `coach serve` — this is a localhost demo surface, not a production
deployment (sessions live in memory, one process).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gaffer.agent import CoachDeps, build_agent, resolve_model
from gaffer.data import make_source

_PAGE = Path(__file__).parent / "static" / "index.html"


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ToolCall(BaseModel):
    tool: str
    detail: str


class ChatResponse(BaseModel):
    answer: str
    tools: list[ToolCall]


def create_app(model: str | None = None, data_dir: Path | None = None) -> FastAPI:
    model_name = resolve_model(model)
    agent = build_agent(model_name)
    source = make_source(data_dir)
    sessions: dict[str, list] = {}

    app = FastAPI(title="gaffer", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _PAGE.read_text(encoding="utf-8").replace("{{MODEL}}", model_name)

    @app.get("/api/matches")
    def api_matches() -> list[dict]:
        return [
            {"match_id": s.match_id, "label": s.label(), "date": s.date.isoformat()}
            for s in source.list_matches()
        ]

    @app.post("/api/chat")
    async def api_chat(request: ChatRequest) -> ChatResponse:
        calls: list[ToolCall] = []
        deps = CoachDeps(
            source=source,
            on_tool=lambda tool, detail: calls.append(ToolCall(tool=tool, detail=detail)),
        )
        try:
            result = await agent.run(
                request.message, deps=deps, message_history=sessions.get(request.session_id)
            )
        except Exception as exc:  # provider/network errors -> clean JSON error
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        sessions[request.session_id] = result.all_messages()
        return ChatResponse(answer=result.output, tools=calls)

    return app
