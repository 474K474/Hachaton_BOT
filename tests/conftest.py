from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from eventbot.db.session import init_db, make_engine, make_sessionmaker

FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("Europe/Moscow")


@pytest.fixture
def tz():
    return TZ


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
async def sm():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()
