"""Analysis functions vs hand-computed values from the BYO fixture match.

Fixture ground truth (tests/fixtures/byo/events/1001.json):
Rovers: 10 passes (8 complete), 3 progressive, 2 final-third entries,
        4 shots (2 goals, 3 on target, 1.1 xG), Dana = 4 defensive actions.
United: 6 passes (4 complete), 1 progressive, 0 entries,
        2 shots (1 goal, 1 on target, 0.8 xG).
"""

from gaffer.analysis import defending, passing, possession, shooting, summary


def test_possession(match):
    report = possession.compute(match)
    rovers, united = report.teams
    assert rovers.team == "Rovers"
    assert (rovers.passes, rovers.passes_completed) == (10, 8)
    assert rovers.pass_completion_pct == 80.0
    assert (united.passes, united.passes_completed) == (6, 4)
    assert rovers.possession_pct == 66.7  # 8 / 12 completed
    assert united.possession_pct == 33.3
    assert rovers.final_third_entries == 2
    assert united.final_third_entries == 0


def test_shooting(match):
    rovers, united = shooting.compute(match).teams
    assert (rovers.shots, rovers.on_target, rovers.goals) == (4, 3, 2)
    assert rovers.total_xg == 1.1
    assert (united.shots, united.on_target, united.goals) == (2, 1, 1)
    assert united.total_xg == 0.8


def test_shooting_single_team(match):
    report = shooting.compute(match, team="United")
    assert len(report.teams) == 1
    assert all(shot.team == "United" for shot in report.shots)


def test_passing(match):
    report = passing.compute(match, "Rovers")
    assert report.progressive_passes == 3
    top = report.top_passers[0]
    assert (top.player, top.passes, top.completed) == ("Alice", 5, 4)
    pair = report.top_pairs[0]
    assert (pair.from_player, pair.to_player, pair.passes) == ("Alice", "Bob", 3)


def test_defending(match):
    report = defending.compute(match)
    rovers = next(t for t in report.teams if t.team == "Rovers")
    assert (rovers.tackles, rovers.interceptions, rovers.pressures) == (1, 1, 2)
    assert (rovers.blocks, rovers.clearances, rovers.ball_recoveries) == (0, 1, 0)
    united = next(t for t in report.teams if t.team == "United")
    assert (united.tackles, united.blocks, united.ball_recoveries) == (1, 1, 1)
    assert report.top_defenders[0].player == "Dana"
    assert report.top_defenders[0].actions == 4


def test_detail(match):
    detail = summary.detail(match)
    assert detail.formations == {"Rovers": "4-4-2", "United": "4-3-3"}
    assert [(g.minute, g.team) for g in detail.goals] == [
        (15, "Rovers"),
        (50, "United"),
        (75, "Rovers"),
    ]
    assert detail.substitutions[0].player_off == "Finn"
    assert detail.substitutions[0].player_on == "Gil"
    assert detail.shootout_score is None
    assert "Alice — Center Midfield" in detail.lineups["Rovers"]


def test_player_line(match):
    line = summary.player_line(match, "Bob")
    assert line.team == "Rovers"
    assert (line.passes, line.passes_completed) == (3, 2)
    assert (line.shots, line.goals) == (2, 1)
    assert line.xg == 0.8


def test_form(byo_source):
    newest_first = [byo_source.get_match(1002), byo_source.get_match(1001)]
    report = summary.form("Rovers", newest_first)
    assert (report.wins, report.draws, report.losses) == (2, 0, 0)
    assert report.matches[0].goals_for == 1  # the 1002 away win via own goal
    assert report.matches[0].xg_against == 0.3
