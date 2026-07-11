"""Tiny JSON disk cache so repeat queries are fast and work offline.

StatsBomb open data is effectively static, so there is no TTL — clear
manually with `coach cache clear`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import platformdirs
from pydantic import BaseModel, TypeAdapter

M = TypeVar("M", bound=BaseModel)


def cache_dir() -> Path:
    override = os.environ.get("GAFFER_CACHE_DIR")
    path = Path(override) if override else Path(platformdirs.user_cache_dir("gaffer"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cached_model(key: str, model: type[M], fetch: Callable[[], M]) -> M:
    path = cache_dir() / f"{key}.json"
    if path.exists():
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    value = fetch()
    path.write_text(value.model_dump_json(), encoding="utf-8")
    return value


def cached_model_list(key: str, model: type[M], fetch: Callable[[], list[M]]) -> list[M]:
    adapter: TypeAdapter[list[M]] = TypeAdapter(list[model])  # type: ignore[valid-type]
    path = cache_dir() / f"{key}.json"
    if path.exists():
        return adapter.validate_json(path.read_text(encoding="utf-8"))
    value = fetch()
    path.write_text(json.dumps(adapter.dump_python(value, mode="json")), encoding="utf-8")
    return value


def clear() -> int:
    """Delete all cache files; returns the number removed."""
    removed = 0
    for file in cache_dir().glob("*.json"):
        file.unlink()
        removed += 1
    return removed


def info() -> tuple[Path, int, int]:
    """Return (path, file count, total bytes)."""
    directory = cache_dir()
    files = list(directory.glob("*.json"))
    return directory, len(files), sum(f.stat().st_size for f in files)
