"""Data sources: StatsBomb open data by default, or your own match files."""

from __future__ import annotations

from pathlib import Path

from gaffer.data.base import DataSource


def make_source(data_dir: Path | str | None = None) -> DataSource:
    """Build the right DataSource: LocalSource if a directory is given."""
    if data_dir is not None:
        from gaffer.data.local import LocalSource

        return LocalSource(data_dir)
    from gaffer.data.statsbomb import StatsBombSource

    return StatsBombSource()
