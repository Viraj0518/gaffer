"""Shot and xG aggregation."""

from __future__ import annotations

from gaffer.models import SHOOTOUT_PERIOD, Match, Shot, ShotReport, TeamShooting

ON_TARGET = {"goal", "saved", "saved_to_post"}


def compute(match: Match, team: str | None = None) -> ShotReport:
    team_names = [team] if team else list(match.team_names())

    team_lines = []
    shot_lines = []
    for name in team_names:
        shots = [
            e
            for e in match.events
            if e.type == "shot" and e.team == name and e.period != SHOOTOUT_PERIOD
        ]
        xg_values = [e.xg for e in shots if e.xg is not None]
        total_xg = round(sum(xg_values), 2)
        team_lines.append(
            TeamShooting(
                team=name,
                shots=len(shots),
                on_target=sum(1 for e in shots if e.outcome in ON_TARGET),
                goals=sum(1 for e in shots if e.outcome == "goal"),
                total_xg=total_xg,
                xg_per_shot=round(total_xg / len(shots), 3) if shots else 0.0,
            )
        )
        shot_lines.extend(
            Shot(minute=e.minute, team=e.team, player=e.player, xg=e.xg, outcome=e.outcome)
            for e in shots
        )

    shot_lines.sort(key=lambda s: s.minute)
    return ShotReport(match=match.summary.label(), teams=team_lines, shots=shot_lines)
