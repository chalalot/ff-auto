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
    assert isinstance(data, list)
    assert "turbo" in data


def test_vision_models(client):
    r = client.get("/api/config/vision-models")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(m["value"] == "gpt-4o" for m in data)


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


def test_persona_not_found(client):
    r = client.get("/api/config/personas/nonexistent")
    assert r.status_code == 404


def test_create_and_read_persona(client, _temp_dirs):
    """Create a persona directory manually, then read via API."""
    personas_dir = Path(_temp_dirs["PROMPTS_DIR"]) / "personas" / "TestGirl"
    personas_dir.mkdir(parents=True, exist_ok=True)
    (personas_dir / "type.txt").write_text("instagirl")
    (personas_dir / "hair_color.txt").write_text("black")
    (personas_dir / "hairstyles.txt").write_text("straight\nwavy")

    r = client.get("/api/config/personas/TestGirl")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "TestGirl"
    assert data["type"] == "instagirl"
    assert data["hair_color"] == "black"
    assert "straight" in data["hairstyles"]


def test_update_persona(client, _temp_dirs):
    personas_dir = Path(_temp_dirs["PROMPTS_DIR"]) / "personas" / "TestGirl"
    personas_dir.mkdir(parents=True, exist_ok=True)

    r = client.put("/api/config/personas/TestGirl", json={"hair_color": "blonde"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get("/api/config/personas/TestGirl")
    assert r2.json()["hair_color"] == "blonde"


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
        "kol_persona": "Sephera",
        "workflow_choice": "Turbo",
        "vision_model_choice": "ChatGPT (gpt-4o)",
        "clip_model_type": "sd3",
        "limit_choice": 5,
        "variation_count": 2,
        "strength_model": 0.9,
        "width": "1024",
        "height": "1600",
        "seed_strategy": "random",
        "base_seed": 0,
        "lora_name_override": "",
        "persona_config_select": "Sephera",
        "editor_type_select": "instagirl",
    }
    r = client.put("/api/config/presets/_last_used", json=payload)
    assert r.status_code == 200

    r2 = client.get("/api/config/presets/_last_used")
    assert r2.json()["kol_persona"] == "Sephera"
    assert r2.json()["variation_count"] == 2
