import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# NOTE: Adjust these imports if your core files are named differently (e.g., from app.main import app)
from main import app
from database import get_db

# Inside Docker, the API connects to the database using the 'db' service name
TEST_DATABASE_URL = "postgresql+asyncpg://buildshield_user:supersecurepassword@db:5432/buildshield_db"

# Create a dedicated async engine for testing
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    Spins up an isolated database transaction for a single test.
    Rolls back automatically when the test finishes.
    """
    async with engine.connect() as connection:
        # 1. Start a master transaction
        transaction = await connection.begin()
        # 2. Start a nested transaction (savepoint) so app commits don't persist
        await connection.begin_nested()
        
        # 3. Bind the session to this specific connection
        async_session = TestingSessionLocal(bind=connection)
        
        yield async_session
        
        # 4. Clean up and roll back everything 
        await async_session.close()
        await transaction.rollback()

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session):
    """
    Creates an async HTTP client for testing our FastAPI endpoints.
    Automatically injects the isolated db_session into the app.
    """
    # Override FastAPI's database dependency to use our isolated test session
    async def override_get_db():
        yield db_session
        
    app.dependency_overrides[get_db] = override_get_db
    
    # Use httpx.AsyncClient to mock requests directly against the ASGI app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
        
    # Clear overrides so they don't leak into other tests
    app.dependency_overrides.clear()