"""The coach agent: provider-agnostic via PydanticAI.

Design rule: the LLM coaches, the tools compute. Every number in an answer
comes from a deterministic analysis function over real event data — the model
composes and interprets, it never invents statistics.
"""

from __future__ import annotations

import difflib
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from pydantic_ai import Agent, ModelRetry, RunContext

from gaffer.analysis import defending, passing, possession, shooting, summary
from gaffer.data.base import DataSource
from gaffer.models import (
    DefensiveReport,
    FormReport,
    Match,
    MatchDetail,
    MatchSummary,
    PassingReport,
    PlayerReport,
    PossessionReport,
    ShotReport,
)

DEFAULT_MODEL = "anthropic:claude-sonnet-5"
MODEL_ENV = "COACH_MODEL"

COACH_INSTRUCTIONS = """\
You are an experienced professional soccer coach and match analyst. You have
tools that compute statistics from real match event data.

Rules you never break:
- Every statistic you state MUST come from a tool call in this conversation.
  Never estimate, recall, or invent numbers — if you haven't fetched it, fetch it.
- Resolve matches first: use list_matches to find match ids before analyzing.
  When the user names a match loosely ("the final", "France vs Argentina"),
  find it in the list rather than guessing ids.
- If the data cannot answer the question, say so plainly and suggest what it
  can answer instead.

How you talk: like a coach at a whiteboard — direct, concrete, tactical.
Structure analysis as: what the data shows → why it matters tactically →
what to work on (in training or in the next match). Prefer a few sharp
insights over exhaustive stat dumps. Use players' common short names in prose
even when the data returns full legal names.
"""

ProgressHook = Callable[[str, str], None]


@dataclass
class CoachDeps:
    source: DataSource
    on_tool: ProgressHook | None = None


def resolve_model(model: str | None = None) -> str:
    """Pick the model string: explicit arg > $COACH_MODEL > default.

    Any PydanticAI model string works: `anthropic:...`, `openai:...`,
    `google-gla:...`, `groq:...`, `ollama:...` (local; base URL defaults to
    the standard localhost Ollama endpoint), etc.
    """
    name = model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    if name.startswith("ollama:"):
        os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    return name


def build_agent(model: str | None = None) -> Agent[CoachDeps, str]:
    agent: Agent[CoachDeps, str] = Agent(
        resolve_model(model),
        deps_type=CoachDeps,
        instructions=COACH_INSTRUCTIONS,
        retries=3,
    )

    def _notify(ctx: RunContext[CoachDeps], tool: str, detail: str) -> None:
        if ctx.deps.on_tool:
            ctx.deps.on_tool(tool, detail)

    def _get_match(ctx: RunContext[CoachDeps], match_id: int | str) -> Match:
        try:
            return ctx.deps.source.get_match(match_id)
        except (KeyError, LookupError, FileNotFoundError, ValueError) as exc:
            raise ModelRetry(str(exc)) from exc

    @agent.tool
    def list_matches(
        ctx: RunContext[CoachDeps],
        competition: str | None = None,
        team: str | None = None,
    ) -> list[MatchSummary]:
        """List available matches with their ids, teams, scores, and dates.

        Call this first to resolve which match the user means. Without
        arguments it lists the default dataset; `competition` filters by
        competition/season name ("world cup 2018", "premier league"), `team`
        by team name.
        """
        _notify(ctx, "list_matches", competition or team or "all")
        try:
            matches = ctx.deps.source.list_matches(competition=competition, team=team)
        except LookupError as exc:
            raise ModelRetry(str(exc)) from exc
        if not matches:
            raise ModelRetry(
                f"No matches found for competition={competition!r} team={team!r}."
                " Try list_matches with no filters to see what's available."
            )
        return matches

    @agent.tool
    def get_match(ctx: RunContext[CoachDeps], match_id: int | str) -> MatchDetail:
        """Match overview: lineups, formations, goal timeline, substitutions,
        and shootout score if the match went to penalties."""
        _notify(ctx, "get_match", str(match_id))
        return summary.detail(_get_match(ctx, match_id))

    @agent.tool
    def possession_stats(ctx: RunContext[CoachDeps], match_id: int | str) -> PossessionReport:
        """Per-team possession %, pass volume/completion, and final-third entries."""
        _notify(ctx, "possession_stats", str(match_id))
        return possession.compute(_get_match(ctx, match_id))

    @agent.tool
    def shot_stats(
        ctx: RunContext[CoachDeps], match_id: int | str, team: str | None = None
    ) -> ShotReport:
        """Shots, on-target, goals, and xG — per team plus a per-shot list."""
        _notify(ctx, "shot_stats", str(match_id))
        match = _get_match(ctx, match_id)
        return shooting.compute(match, _resolve_team(match, team) if team else None)

    @agent.tool
    def passing_stats(ctx: RunContext[CoachDeps], match_id: int | str, team: str) -> PassingReport:
        """One team's passing structure: top passers, most-used pass pairs,
        and progressive pass count."""
        _notify(ctx, "passing_stats", f"{match_id}, {team}")
        match = _get_match(ctx, match_id)
        return passing.compute(match, _resolve_team(match, team))

    @agent.tool
    def defensive_stats(
        ctx: RunContext[CoachDeps], match_id: int | str, team: str | None = None
    ) -> DefensiveReport:
        """Defensive activity: tackles, interceptions, pressures, blocks,
        clearances, recoveries — per team plus the busiest defenders."""
        _notify(ctx, "defensive_stats", str(match_id))
        match = _get_match(ctx, match_id)
        return defending.compute(match, _resolve_team(match, team) if team else None)

    @agent.tool
    def player_match_stats(
        ctx: RunContext[CoachDeps], match_id: int | str, player: str
    ) -> PlayerReport:
        """One player's full statistical line for a match."""
        _notify(ctx, "player_match_stats", f"{match_id}, {player}")
        match = _get_match(ctx, match_id)
        return summary.player_line(match, _resolve_player(match, player))

    @agent.tool
    def team_form(
        ctx: RunContext[CoachDeps],
        team: str,
        last_n: int = 5,
        competition: str | None = None,
    ) -> FormReport:
        """A team's recent form: W/D/L, goals, and xG for/against over their
        last `last_n` matches. Useful for scouting an opponent."""
        _notify(ctx, "team_form", f"{team}, last {last_n}")
        try:
            summaries = ctx.deps.source.list_matches(competition=competition, team=team)
        except LookupError as exc:
            raise ModelRetry(str(exc)) from exc
        if not summaries:
            raise ModelRetry(f"No matches found for team {team!r}. Use list_matches to see teams.")
        recent = sorted(summaries, key=lambda s: s.date, reverse=True)[:last_n]
        matches = [_get_match(ctx, s.match_id) for s in recent]
        canonical = _canonical_team(recent[0], team)
        return summary.form(canonical, matches)

    return agent


# ---------------------------------------------------------------------------
# Fuzzy name resolution — the LLM self-corrects via ModelRetry
# ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Lowercase and strip accents so 'Mbappe' matches 'Mbappé'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _resolve_team(match: Match, team: str) -> str:
    names = list(match.team_names())
    hits = [n for n in names if _fold(team) in _fold(n) or _fold(n) in _fold(team)]
    if len(hits) == 1:
        return hits[0]
    raise ModelRetry(f"No team {team!r} in this match. Teams: {names[0]}, {names[1]}.")


def _canonical_team(summary_: MatchSummary, team: str) -> str:
    for name in (summary_.home_team, summary_.away_team):
        if _fold(team) in _fold(name):
            return name
    return team


def _resolve_player(match: Match, player: str) -> str:
    candidates = sorted({e.player for e in match.events if e.player})
    hits = [c for c in candidates if _fold(player) in _fold(c)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ModelRetry(f"Ambiguous player {player!r} — matches: {', '.join(hits)}.")
    close = difflib.get_close_matches(player, candidates, n=3, cutoff=0.6)
    hint = f" Closest names: {', '.join(close)}." if close else ""
    raise ModelRetry(
        f"No player matching {player!r} in this match.{hint} Use get_match to see the lineups."
    )
