import pytest

from tests.conftest import make_png


@pytest.fixture(autouse=True)
def _db(clean_tables):
    """Analysis endpoints read evaluations from the (throwaway) postgres."""


def test_analysis_endpoint_returns_summary_and_items(client, _temp_dirs):
    make_png(_temp_dirs["OUTPUT_DIR"], "api_analysis_pending.png")

    resp = client.get("/api/analysis", params={"status": "all", "evaluated": "all"})
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "items" in body
    assert body["summary"]["total"] >= 1
    assert {"approval", "evaluation", "avg_overall_score"} <= set(body["summary"].keys())


def test_analysis_rejects_bad_status(client):
    resp = client.get("/api/analysis", params={"status": "bogus"})
    assert resp.status_code == 422


def test_analysis_pagination_params(client, _temp_dirs):
    for i in range(3):
        make_png(_temp_dirs["OUTPUT_DIR"], f"api_an_page_{i}.png")
    resp = client.get("/api/analysis", params={"page": 1, "per_page": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["per_page"] == 2
    assert len(body["items"]) <= 2
