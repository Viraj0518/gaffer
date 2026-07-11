"""Possession and ball-progression stats, approximated from pass events."""

from __future__ import annotations

from gaffer.models import Match, PossessionReport, TeamPossession

FINAL_THIRD_X = 80.0  # pitch is 120 long; the attacking third starts at x=80


def compute(match: Match) -> PossessionReport:
    teams = []
    completed_by_team: dict[str, int] = {}

    for team in match.team_names():
        passes = [e for e in match.events if e.type == "pass" and e.team == team]
        completed = [e for e in passes if e.outcome == "complete"]
        entries = sum(
            1
            for e in completed
            if e.location and e.end_location and e.location[0] < FINAL_THIRD_X <= e.end_location[0]
        )
        completed_by_team[team] = len(completed)
        teams.append(
            TeamPossession(
                team=team,
                possession_pct=0.0,  # filled below once both teams are counted
                passes=len(passes),
                passes_completed=len(completed),
                pass_completion_pct=round(100 * len(completed) / len(passes), 1) if passes else 0.0,
                final_third_entries=entries,
            )
        )

    total_completed = sum(completed_by_team.values())
    for line in teams:
        if total_completed:
            line.possession_pct = round(100 * completed_by_team[line.team] / total_completed, 1)

    return PossessionReport(match=match.summary.label(), teams=teams)
