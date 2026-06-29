"""Tests for pipeline metadata, JSON introspection, and override application."""
from backend.pipelines import pipelines_metadata


def test_pipelines_metadata_includes_image_and_video():
    meta = pipelines_metadata()
    by_type = {m["pipeline_type"]: m for m in meta}

    assert by_type["image.subject_environment"]["media_type"] == "image"
    assert by_type["image.subject_environment"]["available"] is True
    assert by_type["image.subject_environment"]["label"] == "Subject + Environment"
    assert by_type["image.unified"]["label"] == "Unified prompt"

    # Video pipelines are typed stubs — present but not runnable yet.
    assert by_type["video.first_frame"]["available"] is False
    assert by_type["video.first_last_frame"]["media_type"] == "video"
    assert by_type["video.first_middle_last_frame"]["available"] is False


def test_pipelines_metadata_sorted_by_type():
    types = [m["pipeline_type"] for m in pipelines_metadata()]
    assert types == sorted(types)
