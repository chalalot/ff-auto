"""Smoke tests — no external services required."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_reachable(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert "paths" in data


def test_api_docs_reachable(client):
    r = client.get("/docs")
    assert r.status_code == 200
