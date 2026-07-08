"""Identity resolution: X-Member-Name auto-create, X-Project-Id validation."""
import pytest

from backend.database.members_storage import MembersStorage


@pytest.fixture
def members(clean_tables):
    return MembersStorage()


def test_get_or_create_is_idempotent(members):
    a = members.get_or_create("Khang")
    b = members.get_or_create("Khang")
    assert a == b
    assert [m["name"] for m in members.list_members()] == ["Khang"]


def test_members_api_list_and_create(client, members):
    r = client.post("/api/members", json={"name": "Emi"})
    assert r.status_code == 200
    assert r.json()["name"] == "Emi"
    r = client.get("/api/members")
    assert r.status_code == 200
    assert [m["name"] for m in r.json()] == ["Emi"]


def test_blank_member_name_rejected(client, clean_tables):
    r = client.post("/api/members", json={"name": "   "})
    assert r.status_code == 422


def test_header_auto_creates_member_once(client, members):
    # Any identity-consuming endpoint works; /api/members POST double-creates
    # nothing, so use it twice with the header on a different name.
    headers = {"X-Member-Name": "HeaderUser"}
    client.get("/api/members", headers=headers)  # GET does not consume identity
    from backend.api.identity import get_identity
    ident1 = get_identity(x_member_name="HeaderUser", x_project_id=None)
    ident2 = get_identity(x_member_name="HeaderUser", x_project_id=None)
    assert ident1.member_id == ident2.member_id
    assert len(members.list_members()) == 1


def test_unknown_project_header_is_ignored(clean_tables):
    from backend.api.identity import get_identity
    ident = get_identity(x_member_name=None, x_project_id="nonexistent")
    assert ident.member_id is None
    assert ident.project_id is None
