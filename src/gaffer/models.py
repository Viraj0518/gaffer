"""Canonical data models shared by every layer.

The bring-your-own-data schema is these models serialized to JSON — see
docs/byo-data.md. Report models are what agent tools return; they are kept
flat and self-describing so any LLM can read them without extra context.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field

#: Period number StatsBomb uses for penalty shootouts. Shootout attempts are
#: excluded from shot/xG stats so they don't distort open-play numbers.
SHOOTOUT_PERIOD = 5

# ---------------------------------------------------------------------------
# Core match data
# ---------------------------------------------------------------------------


class Player(BaseModel):
    id: int | str
    name: str
    position: str | None = None
    jersey_number: int | None = None


class MatchSummary(BaseModel):
    match_id: int | str
    date: datetime.date
    competition: str
    season: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int

    def label(self) -> str:
        return (
            f"{self.home_team} {self.home_score}-{self.away_score} {self.away_team}"
            f" ({self.competition} {self.season}, {self.date.isoformat()})"
        )


class Event(BaseModel):
    """One match event, deliberately flat — only the fields analysis needs.

    Pitch coordinates follow the StatsBomb convention: 120 x 80, with each
    team attacking left-to-right (toward x=120) in its own events.
    """

    id: str
    type: str  # pass | shot | tackle | interception | pressure | block |
    #            clearance | ball_recovery | foul_committed | substitution
    period: int
    minute: int
    second: int = 0
    team: str
    player: str | None = None
    location: tuple[float, float] | None = None
    end_location: tuple[float, float] | None = None
    outcome: str | None = None  # passes: complete/incomplete/...; shots: goal/saved/...
    pass_recipient: str | None = None  # passes only
    replacement: str | None = None  # substitutions only: player coming on
    xg: float | None = None  # shots only


class Match(BaseModel):
    summary: MatchSummary
    lineups: dict[str, list[Player]] = Field(default_factory=dict)  # team name -> starting XI
    formations: dict[str, str] = Field(default_factory=dict)  # team name -> "4-3-3"
    events: list[Event] = Field(default_factory=list)

    def team_names(self) -> tuple[str, str]:
        return self.summary.home_team, self.summary.away_team


# ---------------------------------------------------------------------------
# Report models (tool return values)
# ---------------------------------------------------------------------------


class TeamPossession(BaseModel):
    team: str
    possession_pct: float
    passes: int
    passes_completed: int
    pass_completion_pct: float
    final_third_entries: int


class PossessionReport(BaseModel):
    match: str
    teams: list[TeamPossession]
    note: str = "Possession is approximated by each team's share of completed passes."


class Shot(BaseModel):
    minute: int
    team: str
    player: str | None
    xg: float | None
    outcome: str | None


class TeamShooting(BaseModel):
    team: str
    shots: int
    on_target: int
    goals: int
    total_xg: float
    xg_per_shot: float


class ShotReport(BaseModel):
    match: str
    teams: list[TeamShooting]
    shots: list[Shot]
    note: str = "Penalty-shootout attempts are excluded; see get_match for shootout results."


class PasserLine(BaseModel):
    player: str
    passes: int
    completed: int
    completion_pct: float


class PassPair(BaseModel):
    from_player: str
    to_player: str
    passes: int


class PassingReport(BaseModel):
    match: str
    team: str
    top_passers: list[PasserLine]
    top_pairs: list[PassPair]
    progressive_passes: int
    note: str = (
        "Pass pairs count completed passes only. A progressive pass moves the ball"
        " at least 15 units toward the opponent goal (pitch is 120 long)."
    )


class TeamDefense(BaseModel):
    team: str
    tackles: int
    interceptions: int
    pressures: int
    blocks: int
    clearances: int
    ball_recoveries: int


class DefenderLine(BaseModel):
    player: str
    team: str
    actions: int


class DefensiveReport(BaseModel):
    match: str
    teams: list[TeamDefense]
    top_defenders: list[DefenderLine]
    note: str = "actions = tackles + interceptions + pressures + blocks + clearances + recoveries"


class GoalEvent(BaseModel):
    minute: int
    team: str
    player: str | None


class SubstitutionEvent(BaseModel):
    minute: int
    team: str
    player_off: str | None
    player_on: str | None


class MatchDetail(BaseModel):
    summary: MatchSummary
    formations: dict[str, str]
    lineups: dict[str, list[str]]  # team name -> ["Player — position", ...]
    goals: list[GoalEvent]
    substitutions: list[SubstitutionEvent]
    shootout_score: dict[str, int] | None = None  # set when the match went to penalties


class PlayerReport(BaseModel):
    match: str
    player: str
    team: str
    passes: int
    passes_completed: int
    shots: int
    goals: int
    xg: float
    tackles: int
    interceptions: int
    pressures: int
    ball_recoveries: int


class FormMatch(BaseModel):
    match: str
    result: str  # W | D | L
    goals_for: int
    goals_against: int
    xg_for: float
    xg_against: float


class FormReport(BaseModel):
    team: str
    wins: int
    draws: int
    losses: int
    matches: list[FormMatch]
