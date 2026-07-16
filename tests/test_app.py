from kronoskvm.app import create_app


async def test_health(aiohttp_client):
    client = await aiohttp_client(create_app())
    response = await client.get("/health")

    assert response.status == 200
    payload = await response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"


async def test_system_info(aiohttp_client):
    client = await aiohttp_client(create_app())
    response = await client.get("/api/v1/system")

    assert response.status == 200
    payload = await response.json()
    assert "hostname" in payload
    assert "architecture" in payload
