"""Defensive activity: duels, interceptions, pressing."""

from __future__ import annotations

from collections import Counter

from gaffer.models import DefenderLine, DefensiveReport, Match, TeamDefense

DEFENSIVE_TYPES = ("tackle", "interception", "pressure", "block", "clearance", "ball_recovery")
TOP_N = 5


def compute(match: Match, team: str | None = None) -> DefensiveReport:
    team_names = [team] if team else list(match.team_names())

    team_lines = []
    player_actions: Counter[tuple[str, str]] = Counter()
    for name in team_names:
        events = [e for e in match.events if e.team == name and e.type in DEFENSIVE_TYPES]
        counts = Counter(e.type for e in events)
        team_lines.append(
            TeamDefense(
                team=name,
                tackles=counts["tackle"],
                interceptions=counts["interception"],
                pressures=counts["pressure"],
                blocks=counts["block"],
                clearances=counts["clearance"],
                ball_recoveries=counts["ball_recovery"],
            )
        )
        player_actions.update((e.player, name) for e in events if e.player)

    top_defenders = [
        DefenderLine(player=player, team=team_name, actions=actions)
        for (player, team_name), actions in player_actions.most_common(TOP_N)
    ]
    return DefensiveReport(
        match=match.summary.label(), teams=team_lines, top_defenders=top_defenders
    )
