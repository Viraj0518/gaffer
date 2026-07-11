"""The seam every data source implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gaffer.models import Match, MatchSummary


@runtime_checkable
class DataSource(Protocol):
    def list_matches(
        self, competition: str | None = None, team: str | None = None
    ) -> list[MatchSummary]:
        """List available matches, optionally filtered by competition/team name."""
        ...

    def get_match(self, match_id: int | str) -> Match:
        """Load one match with its full event list."""
        ...
