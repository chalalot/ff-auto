"""
Task 5 tests: RunsPostsStorage ported from raw psycopg2 to SQLAlchemy.

JSONB and TEXT[] columns must round-trip as dicts/lists (not strings),
matching the psycopg2 RealDictCursor behavior. Upsert-on-id semantics for
save_run/save_post are preserved.
"""
import pytest

from backend.database.runs_posts_storage import RunsPostsStorage


@pytest.fixture
def storage(clean_tables):
    return RunsPostsStorage()


def _run(storage, run_id="run-1", **overrides):
    kwargs = dict(
        run_id=run_id,
        trend_text="a trend",
        persona_name="dancer",
        num_posts=2,
        metadata={"workflow": "w1"},
        adapted_idea={"idea": "x"},
        trend_profile={"score": 0.9},
    )
    kwargs.update(overrides)
    return storage.save_run(**kwargs)


def _post(storage, post_id="post-1", run_id="run-1", **overrides):
    kwargs = dict(
        post_id=post_id,
        run_id=run_id,
        post_index=0,
        caption="hello",
        hashtags=["#a", "#b"],
        image_url="https://img/1.png",
        image_prompt="a prompt",
        cta="follow",
        visual_plan={"scene": "beach"},
        content_seed={"seed": 1},
        metadata={"tier": "a"},
    )
    kwargs.update(overrides)
    return storage.save_post(**kwargs)


def test_save_and_get_run_jsonb_roundtrip(storage):
    assert _run(storage) == "run-1"
    run = storage.get_run("run-1")
    assert run["id"] == "run-1"
    assert run["persona_name"] == "dancer"
    assert run["adapted_idea"] == {"idea": "x"}  # dict, not str
    assert run["trend_profile"] == {"score": 0.9}
    assert run["metadata"] == {"workflow": "w1"}
    assert isinstance(run["created_at"], int)


def test_save_run_upserts_on_id(storage):
    _run(storage)
    _run(storage, trend_text="updated trend", num_posts=5)
    run = storage.get_run("run-1")
    assert run["trend_text"] == "updated trend"
    assert run["num_posts"] == 5
    assert len(storage.list_runs()) == 1


def test_get_run_missing_returns_none(storage):
    assert storage.get_run("missing") is None
    assert storage.get_post_by_id("missing") is None
    assert storage.get_run_with_posts("missing") is None


def test_save_and_get_post_arrays_roundtrip(storage):
    _run(storage)
    assert _post(storage) == "post-1"
    post = storage.get_post_by_id("post-1")
    assert post["hashtags"] == ["#a", "#b"]  # list, not str
    assert post["visual_plan"] == {"scene": "beach"}
    assert post["content_seed"] == {"seed": 1}
    assert post["metadata"] == {"tier": "a"}
    assert post["run_id"] == "run-1"


def test_save_post_upserts_on_id(storage):
    _run(storage)
    _post(storage)
    _post(storage, caption="rewritten", hashtags=["#c"])
    post = storage.get_post_by_id("post-1")
    assert post["caption"] == "rewritten"
    assert post["hashtags"] == ["#c"]
    assert len(storage.get_posts_by_run("run-1")) == 1


def test_update_post_image_link(storage):
    _run(storage)
    _post(storage)
    storage.update_post_image_link("post-1", "https://img/new.png")
    assert storage.get_post_by_id("post-1")["image_url"] == "https://img/new.png"


def test_get_posts_by_run_and_run_with_posts(storage):
    _run(storage)
    _post(storage, post_id="p1", post_index=0)
    _post(storage, post_id="p2", post_index=1)
    posts = storage.get_posts_by_run("run-1")
    assert [p["id"] for p in posts] == ["p1", "p2"]

    combo = storage.get_run_with_posts("run-1")
    assert combo["id"] == "run-1"
    assert [p["id"] for p in combo["posts"]] == ["p1", "p2"]


def test_list_runs_includes_post_count(storage):
    _run(storage, run_id="run-a")
    _run(storage, run_id="run-b")
    _post(storage, post_id="p1", run_id="run-a")
    _post(storage, post_id="p2", run_id="run-a")
    runs = storage.list_runs()
    counts = {r["id"]: r["post_count"] for r in runs}
    assert counts == {"run-a": 2, "run-b": 0}


def test_get_all_runs_adds_run_id_alias(storage):
    _run(storage)
    runs = storage.get_all_runs()
    assert runs[0]["run_id"] == runs[0]["id"] == "run-1"


def test_delete_run_cascades_posts(storage):
    _run(storage)
    _post(storage)
    storage.delete_run("run-1")
    assert storage.get_run("run-1") is None
    assert storage.get_post_by_id("post-1") is None


def test_post_versioning_flow(storage):
    _run(storage)
    _post(storage)

    v1 = storage.save_post_version(
        post_id="post-1",
        visual_plan={"scene": "v1"},
        image_prompt="prompt v1",
        image_url="https://img/v1.png",
    )
    assert v1["version"] == 1
    assert v1["is_current"] is True

    v2 = storage.save_post_version(
        post_id="post-1",
        visual_plan={"scene": "v2"},
        image_prompt="prompt v2",
        image_url="https://img/v2.png",
    )
    assert v2["version"] == 2

    versions = storage.get_post_versions("post-1")
    assert [v["version"] for v in versions] == [1, 2]
    assert [v["is_current"] for v in versions] == [False, True]

    # Post carries the current version's payload.
    post = storage.get_post_by_id("post-1")
    assert post["image_url"] == "https://img/v2.png"
    assert post["current_version"] == 2

    # Roll back to v1.
    assert storage.set_current_version("post-1", 1) is True
    versions = storage.get_post_versions("post-1")
    assert [v["is_current"] for v in versions] == [True, False]
    assert storage.get_post_by_id("post-1")["image_url"] == "https://img/v1.png"

    # Unknown version / post.
    assert storage.set_current_version("post-1", 99) is False
    assert storage.set_current_version("missing", 1) is False


def test_save_post_version_missing_post_raises(storage):
    with pytest.raises(ValueError):
        storage.save_post_version(post_id="missing", image_url="x")


def test_get_post_versions_empty(storage):
    _run(storage)
    _post(storage)
    assert storage.get_post_versions("post-1") == []
    assert storage.get_post_versions("missing") == []


def test_create_tables_is_a_noop(storage):
    """Alembic owns the schema; the legacy method survives as a no-op."""
    storage.create_tables()
    assert storage.get_run("still-fine") is None


def test_constructor_takes_no_legacy_args(clean_tables):
    """The psycopg2-era connection_string parameter is gone for good."""
    with pytest.raises(TypeError):
        RunsPostsStorage(connection_string="postgresql://x")
    assert RunsPostsStorage().get_run("nope") is None
