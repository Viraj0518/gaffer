# Bring your own match data

gaffer ships with StatsBomb open data, but the coach works on **any** match
data you can express in its canonical schema — your Sunday-league team, your
academy side, a league it doesn't cover. Point any command at your directory:

```bash
coach chat --data-dir ./my-team
coach matches --data-dir ./my-team
coach serve --data-dir ./my-team
```

## Directory layout

```
my-team/
├── matches.json          # the manifest: one record per match
└── events/
    ├── 1001.json         # events for match 1001 (JSON), or
    └── 1002.csv          # events for match 1002 (CSV)
```

## matches.json

A JSON list; one record per match. `lineups` and `formations` are optional.

```json
[
  {
    "match_id": 1001,
    "date": "2026-05-10",
    "competition": "Sunday League",
    "season": "2026",
    "home_team": "Rovers",
    "away_team": "United",
    "home_score": 2,
    "away_score": 1,
    "formations": { "Rovers": "4-4-2", "United": "4-3-3" },
    "lineups": {
      "Rovers": [
        { "id": 1, "name": "Alice", "position": "Center Midfield" },
        { "id": 2, "name": "Bob", "position": "Striker" }
      ]
    }
  }
]
```

## Events — JSON

`events/<match_id>.json` is a JSON list of event objects. Only `id`, `type`,
`period`, `minute`, and `team` are required.

```json
[
  {
    "id": "p1",
    "type": "pass",
    "period": 1,
    "minute": 2,
    "second": 14,
    "team": "Rovers",
    "player": "Alice",
    "location": [30, 40],
    "end_location": [50, 40],
    "outcome": "complete",
    "pass_recipient": "Bob"
  },
  {
    "id": "s1",
    "type": "shot",
    "period": 1,
    "minute": 15,
    "team": "Rovers",
    "player": "Bob",
    "location": [105, 40],
    "outcome": "goal",
    "xg": 0.5
  }
]
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `id` | string | any unique id |
| `type` | string | `pass`, `shot`, `tackle`, `interception`, `pressure`, `block`, `clearance`, `ball_recovery`, `foul_committed`, `substitution`, `own_goal` |
| `period` | int | 1–4; use `5` for penalty shootouts (excluded from stats automatically) |
| `minute`, `second` | int | match clock |
| `team` | string | must match a team in the match record (for `own_goal`: the team that *benefits*) |
| `player` | string? | player name |
| `location`, `end_location` | [x, y]? | StatsBomb pitch convention: 120×80, each team attacks toward x=120 in its own events |
| `outcome` | string? | passes: `complete`/`incomplete`; shots: `goal`, `saved`, `saved_to_post`, `blocked`, `off_target`, `wayward`, `post` |
| `pass_recipient` | string? | passes only |
| `replacement` | string? | substitutions only: the player coming on |
| `xg` | float? | shots only, 0–1 |

Notes on how stats are derived:

- **Possession** is approximated from each team's share of completed passes —
  you don't need possession data, just passes.
- **On-target** = `goal`, `saved`, or `saved_to_post`.
- **Progressive pass** = completed pass moving the ball ≥ 15 units toward x=120.
- Events without `location` still count for volume stats; location-based stats
  (final-third entries, progressive passes) just skip them.

## Events — CSV

If a spreadsheet is easier, use `events/<match_id>.csv` with this header:

```csv
type,period,minute,second,team,player,x,y,end_x,end_y,outcome,pass_recipient,xg
pass,1,2,14,Rovers,Alice,30,40,50,40,complete,Bob,
shot,1,15,0,Rovers,Bob,105,40,,,goal,,0.5
```

Leave cells empty for unknown values. Column meanings match the JSON fields
(`x,y` = `location`, `end_x,end_y` = `end_location`).

## Validation

Files are validated on load with friendly errors that name the file, the row,
and the field — run `coach matches --data-dir ./my-team` as a quick check.
