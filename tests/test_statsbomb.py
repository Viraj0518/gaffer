"""Raw StatsBomb JSON -> canonical model parsing, against a vendored sample.

The sample is a trimmed slice of the 2022 World Cup final (all shots and
tactics events, capped counts of the rest) captured once from the open-data
API. No test here touches the network.
"""

import json
from pathlib import Path

from gaffer.analysis import shooting, summary
from gaffer.data.statsbomb import parse_events, parse_summary, parse_tactics
from gaffer.models import Match

FIXTURES = Path(__file__).parent / "fixtures"


def _raw_events() -> list[dict]:
    return json.loads((FIXTURES / "statsbomb_events_sample.json").read_text(encoding="utf-8"))


def _raw_match() -> dict:
    return json.loads((FIXTURES / "statsbomb_match_sample.json").read_text(encoding="utf-8"))


def test_parse_summary():
    s = parse_summary(_raw_match())
    assert (s.home_team, s.away_team) == ("Argentina", "France")
    assert (s.home_score, s.away_score) == (3, 3)
    assert s.competition == "FIFA World Cup"
    assert s.date.isoformat() == "2022-12-18"


def test_parse_events_maps_all_expected_types():
    events = parse_events(_raw_events())
    types = {e.type for e in events}
    assert {
        "pass",
        "shot",
        "tackle",
        "interception",
        "pressure",
        "block",
        "clearance",
        "ball_recovery",
        "foul_committed",
        "substitution",
    } <= types
    # Unmapped raw types (Half Start, Starting XI, ...) must be dropped.
    assert "half_start" not in types and "starting_xi" not in types


def test_pass_outcome_convention():
    events = parse_events(_raw_events())
    passes = [e for e in events if e.type == "pass"]
    complete = [e for e in passes if e.outcome == "complete"]
    incomplete = [e for e in passes if e.outcome == "incomplete"]
    assert complete and incomplete  # sample contains both
    assert all(e.pass_recipient for e in complete)


def test_shots_carry_xg():
    shots = [e for e in parse_events(_raw_events()) if e.type == "shot"]
    assert shots
    assert all(e.xg is not None for e in shots)
    assert any(e.outcome == "goal" for e in shots)


def test_parse_tactics():
    lineups, formations = parse_tactics(_raw_events())
    assert formations == {"Argentina": "4-3-3", "France": "4-2-3-1"}
    assert len(lineups["Argentina"]) == 11
    assert len(lineups["France"]) == 11
    assert all(p.position for p in lineups["Argentina"])


def test_shootout_excluded_from_shot_stats():
    """The final ended 3-3 with a shootout; stats must report 3 goals, not 7."""
    match = Match(summary=parse_summary(_raw_match()), events=parse_events(_raw_events()))
    argentina, france = shooting.compute(match).teams
    assert argentina.goals == 3
    assert france.goals == 3
    detail = summary.detail(match)
    assert detail.shootout_score == {"Argentina": 4, "France": 2}
    assert len(detail.goals) == 6  # open play + extra time, no shootout
