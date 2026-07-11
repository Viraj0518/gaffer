"""Bring-your-own-data source.

Point `--data-dir` at a directory shaped like this (full spec: docs/byo-data.md):

    my-team/
    ├── matches.json          # list of match records (canonical MatchSummary fields,
    │                         #   plus optional "lineups" and "formations")
    └── events/
        ├── 1001.json         # list of canonical Event objects, or
        └── 1002.csv          # flat CSV (see CSV_COLUMNS)

The JSON schema IS the canonical model schema — what gaffer uses internally.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import Field, TypeAdapter, ValidationError

from gaffer.models import Event, Match, MatchSummary, Player

CSV_COLUMNS = "type,period,minute,second,team,player,x,y,end_x,end_y,outcome,pass_recipient,xg"


class LocalMatchRecord(MatchSummary):
    lineups: dict[str, list[Player]] = Field(default_factory=dict)
    formations: dict[str, str] = Field(default_factory=dict)


_RECORDS = TypeAdapter(list[LocalMatchRecord])
_EVENTS = TypeAdapter(list[Event])


class LocalSource:
    """DataSource over a local directory of match files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        manifest = self.root / "matches.json"
        if not manifest.exists():
            raise FileNotFoundError(
                f"{manifest} not found. A BYO data directory needs a matches.json manifest —"
                " see docs/byo-data.md."
            )
        try:
            self._records = _RECORDS.validate_json(manifest.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise ValueError(f"{manifest} is invalid:\n{_friendly(exc)}") from exc

    def list_matches(
        self, competition: str | None = None, team: str | None = None
    ) -> list[MatchSummary]:
        summaries: list[MatchSummary] = [
            MatchSummary.model_validate(r.model_dump(include=set(MatchSummary.model_fields)))
            for r in self._records
        ]
        if competition:
            needle = competition.lower()
            summaries = [s for s in summaries if needle in f"{s.competition} {s.season}".lower()]
        if team:
            needle = team.lower()
            summaries = [
                s
                for s in summaries
                if needle in s.home_team.lower() or needle in s.away_team.lower()
            ]
        return sorted(summaries, key=lambda s: s.date)

    def get_match(self, match_id: int | str) -> Match:
        record = next((r for r in self._records if str(r.match_id) == str(match_id)), None)
        if record is None:
            known = ", ".join(str(r.match_id) for r in self._records)
            raise KeyError(f"No match {match_id!r} in {self.root}. Known ids: {known}")
        return Match(
            summary=MatchSummary.model_validate(
                record.model_dump(include=set(MatchSummary.model_fields))
            ),
            lineups=record.lineups,
            formations=record.formations,
            events=self._load_events(record.match_id),
        )

    # -- internals ----------------------------------------------------------

    def _load_events(self, match_id: int | str) -> list[Event]:
        json_path = self.root / "events" / f"{match_id}.json"
        csv_path = self.root / "events" / f"{match_id}.csv"
        if json_path.exists():
            try:
                return _EVENTS.validate_json(json_path.read_text(encoding="utf-8"))
            except ValidationError as exc:
                raise ValueError(f"{json_path} is invalid:\n{_friendly(exc)}") from exc
        if csv_path.exists():
            return _events_from_csv(csv_path)
        raise FileNotFoundError(
            f"No event file for match {match_id}: expected {json_path} or {csv_path}."
        )


def _events_from_csv(path: Path) -> list[Event]:
    events = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                events.append(
                    Event(
                        id=f"{path.stem}-{row_number}",
                        type=row["type"].strip().lower(),
                        period=int(row.get("period") or 1),
                        minute=int(row["minute"]),
                        second=int(row.get("second") or 0),
                        team=row["team"].strip(),
                        player=row.get("player", "").strip() or None,
                        location=_csv_point(row.get("x"), row.get("y")),
                        end_location=_csv_point(row.get("end_x"), row.get("end_y")),
                        outcome=row.get("outcome", "").strip().lower() or None,
                        pass_recipient=row.get("pass_recipient", "").strip() or None,
                        xg=float(row["xg"]) if row.get("xg", "").strip() else None,
                    )
                )
            except (KeyError, ValueError, ValidationError) as exc:
                raise ValueError(
                    f"{path} row {row_number}: {exc}\nExpected columns: {CSV_COLUMNS}"
                ) from exc
    return events


def _csv_point(x: str | None, y: str | None) -> tuple[float, float] | None:
    if x and x.strip() and y and y.strip():
        return (float(x), float(y))
    return None


def _friendly(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors():
        where = " -> ".join(str(part) for part in error["loc"])
        lines.append(f"  {where}: {error['msg']}")
    return "\n".join(lines)
