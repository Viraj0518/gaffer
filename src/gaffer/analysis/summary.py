"""Match overview, per-player lines, and team form."""

from __future__ import annotations

from gaffer.models import (
    SHOOTOUT_PERIOD,
    FormMatch,
    FormReport,
    GoalEvent,
    Match,
    MatchDetail,
    PlayerReport,
    SubstitutionEvent,
)


def detail(match: Match) -> MatchDetail:
    ordered = sorted(match.events, key=lambda e: (e.period, e.minute, e.second))
    goals = [
        GoalEvent(minute=e.minute, team=e.team, player=e.player)
        for e in ordered
        if e.period != SHOOTOUT_PERIOD
        and (e.type == "own_goal" or (e.type == "shot" and e.outcome == "goal"))
    ]
    substitutions = [
        SubstitutionEvent(
            minute=e.minute, team=e.team, player_off=e.player, player_on=e.replacement
        )
        for e in ordered
        if e.type == "substitution"
    ]
    shootout = [e for e in ordered if e.type == "shot" and e.period == SHOOTOUT_PERIOD]
    shootout_score = None
    if shootout:
        shootout_score = {team: 0 for team in match.team_names()}
        for e in shootout:
            if e.outcome == "goal":
                shootout_score[e.team] = shootout_score.get(e.team, 0) + 1

    return MatchDetail(
        summary=match.summary,
        formations=match.formations,
        lineups={
            team: [f"{p.name} — {p.position or '?'}" for p in players]
            for team, players in match.lineups.items()
        },
        goals=goals,
        substitutions=substitutions,
        shootout_score=shootout_score,
    )


def player_line(match: Match, player: str) -> PlayerReport:
    """Stats for one player (exact name — fuzzy resolution happens at the agent layer)."""
    events = [e for e in match.events if e.player == player]
    team = events[0].team if events else "?"
    passes = [e for e in events if e.type == "pass"]
    shots = [e for e in events if e.type == "shot" and e.period != SHOOTOUT_PERIOD]

    def count(etype: str) -> int:
        return sum(1 for e in events if e.type == etype)

    return PlayerReport(
        match=match.summary.label(),
        player=player,
        team=team,
        passes=len(passes),
        passes_completed=sum(1 for e in passes if e.outcome == "complete"),
        shots=len(shots),
        goals=sum(1 for e in shots if e.outcome == "goal"),
        xg=round(sum(e.xg or 0.0 for e in shots), 2),
        tackles=count("tackle"),
        interceptions=count("interception"),
        pressures=count("pressure"),
        ball_recoveries=count("ball_recovery"),
    )


def form(team: str, matches: list[Match]) -> FormReport:
    """W/D/L and xG trend over `matches` (expected most-recent first)."""
    lines = []
    wins = draws = losses = 0
    for match in matches:
        s = match.summary
        if team == s.home_team:
            goals_for, goals_against = s.home_score, s.away_score
        else:
            goals_for, goals_against = s.away_score, s.home_score
        if goals_for > goals_against:
            result = "W"
            wins += 1
        elif goals_for == goals_against:
            result = "D"
            draws += 1
        else:
            result = "L"
            losses += 1

        open_play_shots = [
            e for e in match.events if e.type == "shot" and e.period != SHOOTOUT_PERIOD
        ]
        xg_for = sum(e.xg or 0.0 for e in open_play_shots if e.team == team)
        xg_against = sum(e.xg or 0.0 for e in open_play_shots if e.team != team)
        lines.append(
            FormMatch(
                match=s.label(),
                result=result,
                goals_for=goals_for,
                goals_against=goals_against,
                xg_for=round(xg_for, 2),
                xg_against=round(xg_against, 2),
            )
        )
    return FormReport(team=team, wins=wins, draws=draws, losses=losses, matches=lines)
