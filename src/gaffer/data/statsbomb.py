"""StatsBomb open data as a DataSource.

Uses the free public dataset (https://github.com/statsbomb/open-data) via
statsbombpy — no credentials required. Raw JSON is mapped to the canonical
models by pure functions so parsing is testable offline.
"""

from __future__ import annotations

import datetime
import warnings
from typing import Any

from pydantic import BaseModel

from gaffer.data import cache
from gaffer.models import Event, Match, MatchSummary, Player


class CompetitionSeason(BaseModel):
    competition_id: int
    season_id: int
    competition_name: str
    season_name: str


# Default demo competition: FIFA World Cup 2022.
DEFAULT_COMPETITION_ID = 43
DEFAULT_SEASON_ID = 106

SHOOTOUT_PERIOD = 5

_TYPE_MAP = {
    "Pass": "pass",
    "Shot": "shot",
    "Interception": "interception",
    "Pressure": "pressure",
    "Block": "block",
    "Clearance": "clearance",
    "Ball Recovery": "ball_recovery",
    "Foul Committed": "foul_committed",
    "Substitution": "substitution",
    "Own Goal For": "own_goal",
}

_SHOT_OUTCOME_MAP = {
    "Off T": "off_target",
    "Saved Off T": "saved_off_target",
}


def _name(obj: Any) -> str | None:
    """Pull `.name` out of a StatsBomb `{id, name}` dict, tolerating None."""
    if isinstance(obj, dict):
        return obj.get("name")
    return None


def _norm(name: str | None) -> str | None:
    return name.lower().replace(" ", "_") if name else None


def _point(raw: Any) -> tuple[float, float] | None:
    if isinstance(raw, list) and len(raw) >= 2:
        return (float(raw[0]), float(raw[1]))
    return None


def parse_summary(record: dict[str, Any]) -> MatchSummary:
    """Map one record of matches.json to a MatchSummary."""
    return MatchSummary(
        match_id=record["match_id"],
        date=datetime.date.fromisoformat(record["match_date"]),
        competition=record["competition"]["competition_name"],
        season=record["season"]["season_name"],
        home_team=record["home_team"]["home_team_name"],
        away_team=record["away_team"]["away_team_name"],
        home_score=record["home_score"],
        away_score=record["away_score"],
    )


def parse_events(raw_events: list[dict[str, Any]]) -> list[Event]:
    """Map raw StatsBomb event dicts to canonical Events (unmapped types dropped)."""
    events: list[Event] = []
    for e in sorted(raw_events, key=lambda r: r.get("index", 0)):
        raw_type = _name(e.get("type"))
        if raw_type == "Duel":
            if _name(e.get("duel", {}).get("type")) != "Tackle":
                continue
            etype = "tackle"
        elif raw_type in _TYPE_MAP:
            etype = _TYPE_MAP[raw_type]
        else:
            continue

        outcome: str | None = None
        end_location: tuple[float, float] | None = None
        pass_recipient: str | None = None
        replacement: str | None = None
        xg: float | None = None

        if etype == "pass":
            detail = e.get("pass", {})
            # StatsBomb omits pass.outcome when the pass is complete.
            outcome = _norm(_name(detail.get("outcome"))) or "complete"
            end_location = _point(detail.get("end_location"))
            pass_recipient = _name(detail.get("recipient"))
        elif etype == "shot":
            detail = e.get("shot", {})
            raw_outcome = _name(detail.get("outcome"))
            outcome = _norm(_SHOT_OUTCOME_MAP.get(raw_outcome or "", raw_outcome))
            end_location = _point(detail.get("end_location"))
            xg = detail.get("statsbomb_xg")
        elif etype == "tackle":
            outcome = _norm(_name(e.get("duel", {}).get("outcome")))
        elif etype == "interception":
            outcome = _norm(_name(e.get("interception", {}).get("outcome")))
        elif etype == "substitution":
            replacement = _name(e.get("substitution", {}).get("replacement"))

        events.append(
            Event(
                id=e["id"],
                type=etype,
                period=e.get("period", 1),
                minute=e.get("minute", 0),
                second=e.get("second", 0),
                team=e["team"]["name"],
                player=_name(e.get("player")),
                location=_point(e.get("location")),
                end_location=end_location,
                outcome=outcome,
                pass_recipient=pass_recipient,
                replacement=replacement,
                xg=xg,
            )
        )
    return events


def parse_tactics(
    raw_events: list[dict[str, Any]],
) -> tuple[dict[str, list[Player]], dict[str, str]]:
    """Extract starting lineups and formations from Starting XI events."""
    lineups: dict[str, list[Player]] = {}
    formations: dict[str, str] = {}
    for e in raw_events:
        if _name(e.get("type")) != "Starting XI":
            continue
        team = e["team"]["name"]
        tactics = e.get("tactics", {})
        formation = tactics.get("formation")
        if formation:
            formations[team] = "-".join(str(formation))
        lineups[team] = [
            Player(
                id=slot["player"]["id"],
                name=slot["player"]["name"],
                position=_name(slot.get("position")),
                jersey_number=slot.get("jersey_number"),
            )
            for slot in tactics.get("lineup", [])
        ]
    return lineups, formations


class StatsBombSource:
    """DataSource over StatsBomb open data, with a disk cache."""

    def __init__(self) -> None:
        self._summaries: dict[str, MatchSummary] = {}

    def list_matches(
        self, competition: str | None = None, team: str | None = None
    ) -> list[MatchSummary]:
        comp_seasons = (
            self._resolve_competitions(competition)
            if competition
            else [(DEFAULT_COMPETITION_ID, DEFAULT_SEASON_ID)]
        )
        summaries: list[MatchSummary] = []
        for comp_id, season_id in comp_seasons:
            summaries.extend(self._matches_for(comp_id, season_id))
        if team:
            needle = team.lower()
            summaries = [
                s
                for s in summaries
                if needle in s.home_team.lower() or needle in s.away_team.lower()
            ]
        return sorted(summaries, key=lambda s: s.date)

    def get_match(self, match_id: int | str) -> Match:
        return cache.cached_model(f"match_{match_id}", Match, lambda: self._fetch_match(match_id))

    # -- internals ----------------------------------------------------------

    def _fetch_match(self, match_id: int | str) -> Match:
        summary = self._summaries.get(str(match_id))
        if summary is None:
            # Populate from the default competition, then give up with guidance.
            self.list_matches()
            summary = self._summaries.get(str(match_id))
        if summary is None:
            raise KeyError(
                f"Unknown match_id {match_id!r}. Call list_matches first to discover valid ids."
            )
        from statsbombpy import sb  # deferred: statsbombpy import is slow

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw = list(sb.events(match_id=int(match_id), fmt="dict").values())
        lineups, formations = parse_tactics(raw)
        return Match(
            summary=summary,
            lineups=lineups,
            formations=formations,
            events=parse_events(raw),
        )

    def _matches_for(self, comp_id: int, season_id: int) -> list[MatchSummary]:
        def fetch() -> list[MatchSummary]:
            from statsbombpy import sb

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                records = sb.matches(competition_id=comp_id, season_id=season_id, fmt="dict")
            return [parse_summary(r) for r in records.values()]

        summaries = cache.cached_model_list(f"matches_{comp_id}_{season_id}", MatchSummary, fetch)
        for s in summaries:
            self._summaries[str(s.match_id)] = s
        return summaries

    def _resolve_competitions(self, query: str) -> list[tuple[int, int]]:
        """Match 'world cup 2022'-style queries against open competition seasons."""
        comps = self._competitions()
        tokens = query.lower().split()
        hits = [
            c
            for c in comps
            if all(t in f"{c.competition_name} {c.season_name}".lower() for t in tokens)
        ]
        if not hits:
            available = sorted({c.competition_name for c in comps})
            raise LookupError(
                f"No open-data competition matches {query!r}. Available: {', '.join(available)}"
            )
        if len(hits) > 3:
            labels = sorted(f"{c.competition_name} {c.season_name}" for c in hits)
            raise LookupError(
                f"{query!r} matches {len(hits)} competition seasons — be more specific."
                f" Options: {', '.join(labels)}"
            )
        return [(c.competition_id, c.season_id) for c in hits]

    def _competitions(self) -> list[CompetitionSeason]:
        def fetch() -> list[CompetitionSeason]:
            from statsbombpy import sb

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                records = sb.competitions(fmt="dict")
            return [CompetitionSeason.model_validate(r) for r in records.values()]

        return cache.cached_model_list("competitions", CompetitionSeason, fetch)
