"""`coach` — the gaffer CLI."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from gaffer.agent import DEFAULT_MODEL, MODEL_ENV, CoachDeps, build_agent, resolve_model
from gaffer.data import cache, make_source

# Never crash on glyphs a legacy Windows console/pipe can't encode.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        with contextlib.suppress(Exception):
            stream.reconfigure(errors="replace")

app = typer.Typer(
    help="An AI soccer coach grounded in real match data. Provider-agnostic.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
console = Console()

ModelOpt = Annotated[
    str | None,
    typer.Option(
        "--model",
        "-m",
        help=f"Model string, e.g. anthropic:claude-sonnet-5 or ollama:llama3.2"
        f" (default: ${MODEL_ENV} or {DEFAULT_MODEL}).",
    ),
]
DataDirOpt = Annotated[
    Path | None,
    typer.Option("--data-dir", help="Use your own match data instead of StatsBomb open data."),
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Show tool calls as they run.")]

_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google-gla": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
}


def _preflight(model_name: str) -> None:
    provider = model_name.split(":", 1)[0]
    key_env = _KEY_ENV.get(provider)
    if key_env and not os.environ.get(key_env):
        console.print(
            Panel(
                f"Model [bold]{model_name}[/bold] needs [bold]{key_env}[/bold],"
                " which isn't set.\n\n"
                "Fix one of these ways:\n"
                f"  1. Set the key:           [cyan]export {key_env}=...[/cyan]\n"
                "  2. Go local, no key:      [cyan]coach chat -m ollama:llama3.2[/cyan]\n"
                "  3. Another provider:      [cyan]coach chat -m openai:gpt-5[/cyan]",
                title="missing API key",
                border_style="red",
            )
        )
        raise typer.Exit(1)


def _deps(data_dir: Path | None, verbose: bool) -> CoachDeps:
    on_tool = (
        (lambda name, detail: console.print(f"  [dim]⚙ {name}({detail})[/dim]"))
        if verbose
        else None
    )
    return CoachDeps(source=make_source(data_dir), on_tool=on_tool)


async def _run_turn(agent, deps: CoachDeps, prompt: str, history) -> list:
    # agent.run (not run_stream): several models interleave text with tool
    # calls, which makes "first text = final answer" streaming unreliable.
    if console.is_terminal:
        with console.status("[dim]the gaffer is checking the data…[/dim]"):
            result = await agent.run(prompt, deps=deps, message_history=history)
        console.print(Markdown(result.output))
    else:
        result = await agent.run(prompt, deps=deps, message_history=history)
        console.print(result.output)
    return result.all_messages()


@app.command()
def chat(model: ModelOpt = None, data_dir: DataDirOpt = None, verbose: VerboseOpt = False) -> None:
    """Interactive chat with the coach."""
    model_name = resolve_model(model)
    _preflight(model_name)
    agent = build_agent(model_name)
    deps = _deps(data_dir, verbose)
    console.print(
        Panel(
            f"model [bold]{model_name}[/bold] · data "
            f"[bold]{data_dir or 'StatsBomb open data (World Cup 2022 by default)'}[/bold]\n"
            "Ask about matches, tactics, players. [dim]/quit to leave.[/dim]",
            title="⚽ gaffer",
            border_style="green",
        )
    )
    history: list | None = None
    while True:
        try:
            question = console.input("\n[bold cyan]you ›[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not question:
            continue
        if question.lower() in {"/quit", "/exit", "quit", "exit"}:
            break
        try:
            history = asyncio.run(_run_turn(agent, deps, question, history))
        except Exception as exc:  # surface provider/network errors without a traceback wall
            console.print(f"[red]error:[/red] {exc}")
    console.print("[dim]full time.[/dim]")


@app.command()
def ask(
    question: str,
    model: ModelOpt = None,
    data_dir: DataDirOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Ask the coach one question and exit."""
    model_name = resolve_model(model)
    _preflight(model_name)
    agent = build_agent(model_name)
    asyncio.run(_run_turn(agent, _deps(data_dir, verbose), question, None))


@app.command()
def matches(
    competition: Annotated[str | None, typer.Option(help="Filter by competition name.")] = None,
    team: Annotated[str | None, typer.Option(help="Filter by team name.")] = None,
    data_dir: DataDirOpt = None,
) -> None:
    """List available matches (no LLM, no API key needed)."""
    found = make_source(data_dir).list_matches(competition=competition, team=team)
    table = Table(title=f"{len(found)} matches")
    for column in ("id", "date", "competition", "match"):
        table.add_column(column)
    for s in found:
        table.add_row(
            str(s.match_id),
            s.date.isoformat(),
            f"{s.competition} {s.season}",
            f"{s.home_team} {s.home_score}-{s.away_score} {s.away_team}",
        )
    console.print(table)


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port to serve on.")] = 8000,
    model: ModelOpt = None,
    data_dir: DataDirOpt = None,
) -> None:
    """Serve the coach as a local web app (http://localhost:PORT)."""
    import uvicorn

    from gaffer.server import create_app

    model_name = resolve_model(model)
    _preflight(model_name)
    console.print(f"⚽ gaffer serving on [bold green]http://localhost:{port}[/bold green]")
    uvicorn.run(create_app(model_name, data_dir), host="127.0.0.1", port=port, log_level="warning")


cache_app = typer.Typer(help="Manage the local data cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("info")
def cache_info() -> None:
    """Show cache location and size."""
    path, files, size = cache.info()
    console.print(f"{path} — {files} files, {size / 1_048_576:.1f} MB")


@cache_app.command("clear")
def cache_clear() -> None:
    """Delete all cached data."""
    console.print(f"removed {cache.clear()} files")


if __name__ == "__main__":
    app()
