"""
Tests for /api/monitor/* endpoints.
No external services — reads local system metrics.
"""


def test_monitor_health(client):
    r = client.get("/api/monitor/health")
    assert r.status_code == 200
    data = r.json()
    assert "cpu_percent" in data
    assert "ram" in data
    assert "disk" in data
    assert "total_gb" in data["ram"]
    assert "percent" in data["ram"]


def test_monitor_filesystem(client):
    r = client.get("/api/monitor/filesystem")
    assert r.status_code == 200
    data = r.json()
    assert "input" in data
    assert "output_pending" in data
    assert "output_approved" in data
    assert "output_disapproved" in data


def test_monitor_db_stats(client):
    r = client.get("/api/monitor/db-stats")
    assert r.status_code == 200
    data = r.json()
    assert "images" in data
    counts = data["images"]
    assert "total" in counts
    assert "pending" in counts
    assert "completed" in counts
    assert "failed" in counts


def test_monitor_processes(client):
    r = client.get("/api/monitor/processes")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Each entry should have the right shape (if any Python processes running)
    for proc in data:
        assert "pid" in proc
        assert "name" in proc
        assert "cpu_percent" in proc
