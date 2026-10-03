"""Business tests exercise their endpoints; test_auth verifies the real perimeter."""

import pytest

from backend.app.security.auth import AuthMiddleware


@pytest.fixture(autouse=True)
def business_endpoint_access(request, monkeypatch):
    if request.module.__name__.endswith("test_auth"):
        return

    async def business_only(self, scope, receive, send):
        await self.app(scope, receive, send)

    monkeypatch.setattr(AuthMiddleware, "__call__", business_only)
