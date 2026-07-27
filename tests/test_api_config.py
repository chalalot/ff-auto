"""
Tests for /api/config/* endpoints.
No external services — all file-based.
"""
import json
import os
from pathlib import Path


# ---- workflow types / vision models / options ----

def test_workflow_types(client):
    r = client.get("/api/config/workflow-types")
    assert r.status_code == 200
    data = r.json()
    assert data == ["image_generation", "image_upscaler", "multiangle_edit"]


def test_vision_models(client):
    r = client.get("/api/config/vision-models")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(m["value"] == "gpt-4o" for m in data)
    assert any(m["value"] == "gemma-4-31b-it" for m in data)


def test_clip_model_types(client):
    r = client.get("/api/config/clip-model-types")
    assert r.status_code == 200
    data = r.json()
    assert "sd3" in data


def test_lora_options(client):
    r = client.get("/api/config/lora-options")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---- personas ----

def test_list_personas_empty(client):
    """No personas created yet — should return empty list."""
    r = client.get("/api/config/personas")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---- identity locks (per-character preset user-prompt text) ----

def test_identity_locks_lists_persona_content(client, _temp_dirs):
    personas_dir = Path(_temp_dirs["PROMPTS_DIR"]) / "personas" / "TestGirl"
    personas_dir.mkdir(parents=True, exist_ok=True)
    (personas_dir / "identity_lock.txt").write_text("a young adult woman")

    r = client.get("/api/config/identity-locks")
    assert r.status_code == 200
    assert r.json()["TestGirl"] == "a young adult woman"


def test_save_identity_lock_round_trip(client, _temp_dirs):
    personas_dir = Path(_temp_dirs["PROMPTS_DIR"]) / "personas" / "Blondie"
    personas_dir.mkdir(parents=True, exist_ok=True)

    r = client.put(
        "/api/config/identity-locks/Blondie",
        content="a blonde woman in her 20s",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get("/api/config/identity-locks")
    assert r2.json()["Blondie"] == "a blonde woman in her 20s"


def test_save_identity_lock_unknown_persona_404(client):
    r = client.put(
        "/api/config/identity-locks/NoSuchPersona",
        content="x",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 404


# ---- presets ----

def test_list_presets_empty(client):
    r = client.get("/api/config/presets")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_save_and_get_preset(client):
    payload = {"name": "my_preset", "data": {"persona": "Jennie", "width": 1024}}
    r = client.post("/api/config/presets/my_preset", json=payload)
    assert r.status_code == 200

    r2 = client.get("/api/config/presets/my_preset")
    assert r2.status_code == 200
    assert r2.json()["persona"] == "Jennie"


def test_delete_preset(client):
    client.post("/api/config/presets/temp_preset", json={"name": "temp_preset", "data": {}})
    r = client.delete("/api/config/presets/temp_preset")
    assert r.status_code == 200

    r2 = client.get("/api/config/presets/temp_preset")
    assert r2.status_code == 404


def test_preset_not_found(client):
    r = client.get("/api/config/presets/doesnotexist")
    assert r.status_code == 404


# ---- last-used ----

def test_get_last_used_returns_dict(client):
    r = client.get("/api/config/presets/_last_used")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_save_and_get_last_used(client):
    payload = {
        "persona": "Sephera",
        "workflow_type": "image_upscaler",
        "workflow_name": "SeedVR_Image_Upscaler.json",
        "vision_model": "gpt-4o",
        "variations": 2,
    }
    r = client.put("/api/config/presets/_last_used", json=payload)
    assert r.status_code == 200

    r2 = client.get("/api/config/presets/_last_used")
    assert r2.json()["persona"] == "Sephera"
    assert r2.json()["workflow_type"] == "image_upscaler"
    assert r2.json()["workflow_name"] == "SeedVR_Image_Upscaler.json"
    assert r2.json()["variations"] == 2
