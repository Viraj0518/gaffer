from pathlib import Path

import pydantic_ai.models
import pytest

from gaffer.data.local import LocalSource

# Hard guarantee: no test can ever call a real LLM API.
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def byo_dir() -> Path:
    return FIXTURES / "byo"


@pytest.fixture()
def byo_source(byo_dir: Path) -> LocalSource:
    return LocalSource(byo_dir)


@pytest.fixture()
def match(byo_source: LocalSource):
    return byo_source.get_match(1001)
