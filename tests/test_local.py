"""BYO data loader: happy paths and friendly failure modes."""

import json

import pytest

from gaffer.analysis import summary
from gaffer.data.local import LocalSource


def test_list_matches_sorted_by_date(byo_source):
    matches = byo_source.list_matches()
    assert [m.match_id for m in matches] == [1001, 1002]


def test_filters(byo_source):
    assert len(byo_source.list_matches(team="rovers")) == 2
    assert len(byo_source.list_matches(competition="sunday")) == 2
    assert byo_source.list_matches(team="arsenal") == []


def test_get_match_json(byo_source):
    match = byo_source.get_match(1001)
    assert len(match.events) == 31
    assert match.formations["Rovers"] == "4-4-2"
    assert match.lineups["Rovers"][0].name == "Alice"


def test_get_match_csv(byo_source):
    match = byo_source.get_match(1002)
    assert len(match.events) == 4
    own_goals = [e for e in match.events if e.type == "own_goal"]
    assert own_goals and own_goals[0].team == "Rovers"
    # own goal shows up in the goal timeline
    detail = summary.detail(match)
    assert [(g.minute, g.team) for g in detail.goals] == [(60, "Rovers")]


def test_unknown_match_id(byo_source):
    with pytest.raises(KeyError, match="1001"):
        byo_source.get_match(9999)


def test_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="matches.json"):
        LocalSource(tmp_path)


def test_invalid_manifest_is_friendly(tmp_path):
    (tmp_path / "matches.json").write_text(
        json.dumps([{"match_id": 1, "date": "not-a-date"}]), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="date"):
        LocalSource(tmp_path)


def test_invalid_csv_row_reports_line(tmp_path, byo_dir):
    (tmp_path / "matches.json").write_text(
        json.dumps(
            [
                {
                    "match_id": 7,
                    "date": "2026-01-01",
                    "competition": "Test",
                    "season": "2026",
                    "home_team": "A",
                    "away_team": "B",
                    "home_score": 0,
                    "away_score": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    events = tmp_path / "events"
    events.mkdir()
    (events / "7.csv").write_text(
        "type,period,minute,second,team,player,x,y,end_x,end_y,outcome,pass_recipient,xg\n"
        "pass,1,not-a-minute,0,A,P,1,1,2,2,complete,Q,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="row 2"):
        LocalSource(tmp_path).get_match(7)


def test_missing_events_file(tmp_path):
    (tmp_path / "matches.json").write_text(
        json.dumps(
            [
                {
                    "match_id": 8,
                    "date": "2026-01-01",
                    "competition": "Test",
                    "season": "2026",
                    "home_team": "A",
                    "away_team": "B",
                    "home_score": 0,
                    "away_score": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="8"):
        LocalSource(tmp_path).get_match(8)
