# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.database import get_session
from app.main import app
from httpx import AsyncClient, ASGITransport

TEST_URL = "postgresql://bankadmin:test@localhost:5432/bankdb"

@pytest.fixture(scope="session")
def engine():
    return create_engine(TEST_URL)

@pytest.fixture(autouse=True)
def fresh_db(engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()

@pytest.fixture
async def client(session):
    # Override the DB session so API routes use the test DB
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()