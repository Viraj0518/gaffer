"""Local web UI: a small FastAPI app around the coach agent.

Run with `coach serve` — this is a localhost demo surface, not a production
deployment (sessions live in memory, one process).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gaffer.agent import CoachDeps, build_agent, resolve_model
from gaffer.data import make_source

_STATIC = Path(__file__).parent / "static"
_PAGE = _STATIC / "index.html"


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

    # Icons and other static assets (referenced from the manifest as /static/*).
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _PAGE.read_text(encoding="utf-8").replace("{{MODEL}}", model_name)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(
            _STATIC / "manifest.webmanifest", media_type="application/manifest+json"
        )

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        # Served from root so its scope covers the whole app.
        return FileResponse(
            _STATIC / "sw.js",
            media_type="text/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    @app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
    def apple_touch_icon() -> FileResponse:
        # iOS probes these root paths directly when adding to the home screen.
        return FileResponse(_STATIC / "apple-touch-icon.png", media_type="image/png")

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
