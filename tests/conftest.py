import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.database import get_session
from app.main import app
from httpx import AsyncClient, ASGITransport

TEST_URL = "postgresql://bankadmin:test@localhost:5432/bankdb"
pytest_plugins = ('pytest_asyncio', )

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

@pytest_asyncio.fixture
async def client(session):
    def override():
        yield session
    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()