"""
Shared test fixtures and async client setup.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from marg.api.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP test client bound directly to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
