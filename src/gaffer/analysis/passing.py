"""Passing structure: volume, combinations, progression."""

from __future__ import annotations

from collections import Counter

from gaffer.models import Match, PasserLine, PassingReport, PassPair

PROGRESSIVE_GAIN = 15.0
TOP_N = 5


def compute(match: Match, team: str) -> PassingReport:
    passes = [e for e in match.events if e.type == "pass" and e.team == team]
    completed = [e for e in passes if e.outcome == "complete"]

    by_player: Counter[str] = Counter(e.player for e in passes if e.player)
    completed_by_player: Counter[str] = Counter(e.player for e in completed if e.player)
    top_passers = [
        PasserLine(
            player=player,
            passes=count,
            completed=completed_by_player[player],
            completion_pct=round(100 * completed_by_player[player] / count, 1),
        )
        for player, count in by_player.most_common(TOP_N)
    ]

    pairs: Counter[tuple[str, str]] = Counter(
        (e.player, e.pass_recipient) for e in completed if e.player and e.pass_recipient
    )
    top_pairs = [
        PassPair(from_player=source, to_player=target, passes=count)
        for (source, target), count in pairs.most_common(TOP_N)
    ]

    progressive = sum(
        1
        for e in completed
        if e.location and e.end_location and e.end_location[0] - e.location[0] >= PROGRESSIVE_GAIN
    )

    return PassingReport(
        match=match.summary.label(),
        team=team,
        top_passers=top_passers,
        top_pairs=top_pairs,
        progressive_passes=progressive,
    )
