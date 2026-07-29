"""CRUD over the ComfyUI workflow JSON files in the workflows directory.

The workflows directory is the single source of truth for the graphs the
generation pipelines build from (see :mod:`backend.pipelines.image`). Until now
it was read-only from the app's perspective — files were dropped in by hand and
per-run edits went through ephemeral ``workflow_overrides`` that were never
persisted. This module adds the write half so the UI can create, edit, rename,
duplicate, import and delete those graphs directly.

Everything here is a pure function over ``(name, graph)`` plus a filesystem
write, so the validation rules are unit-testable without a running app. The
API layer (:mod:`backend.api.workspace`) maps the three error types below onto
400 / 404 / 409.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from backend.pipelines.image import _workflows_dir, list_workflow_files


class WorkflowValidationError(ValueError):
    """The name or graph is not something we're willing to write. → HTTP 400."""


class WorkflowNotFoundError(LookupError):
    """No such workflow file in the workflows directory. → HTTP 404."""


class WorkflowConflictError(ValueError):
    """The target filename is already taken. → HTTP 409."""


# Filenames are user-facing labels in a dropdown, so stay permissive (the
# existing library has spaces and parentheses) and reject only what is unsafe
# or confusing: path escapes, control characters, and dotfiles.
_UNSAFE_NAME_RE = re.compile(r"[/\\\x00-\x1f]")
_MAX_NAME_LEN = 120

# Keys that mark the *UI editor* export format rather than the API format.
# ComfyUI's "Save" produces {"nodes": [...], "links": [...]}, which the
# /prompt endpoint cannot execute; only "Save (API Format)" output works.
_UI_FORMAT_KEYS = ("nodes", "links", "last_node_id", "last_link_id")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Validate a workflow filename and return it with a ``.json`` suffix.

    Raises :class:`WorkflowValidationError` for anything that could escape the
    workflows directory or shadow a hidden file.
    """
    if not isinstance(name, str):
        raise WorkflowValidationError("Workflow name must be a string")
    cleaned = name.strip()
    if not cleaned:
        raise WorkflowValidationError("Workflow name cannot be empty")
    if _UNSAFE_NAME_RE.search(cleaned):
        raise WorkflowValidationError(
            "Workflow name cannot contain path separators or control characters"
        )
    if ".." in cleaned:
        raise WorkflowValidationError("Workflow name cannot contain '..'")
    if cleaned.startswith("."):
        raise WorkflowValidationError("Workflow name cannot start with '.'")
    if not cleaned.lower().endswith(".json"):
        cleaned += ".json"
    if len(cleaned) > _MAX_NAME_LEN:
        raise WorkflowValidationError(
            f"Workflow name is too long (max {_MAX_NAME_LEN} characters)"
        )
    # Guard the suffix-only case ('.json' → hidden file with an empty stem).
    if cleaned[: -len(".json")].strip() == "":
        raise WorkflowValidationError("Workflow name needs a filename before '.json'")
    return cleaned


def validate_graph(graph: Any) -> Dict[str, Any]:
    """Check that ``graph`` is an executable ComfyUI API-format workflow.

    The API format is a flat mapping of ``node_id -> {class_type, inputs}``.
    Returns the graph unchanged so callers can use it as a checked passthrough.
    """
    if not isinstance(graph, dict):
        kind = "an array" if isinstance(graph, list) else type(graph).__name__
        raise WorkflowValidationError(
            f"Workflow must be a JSON object mapping node ids to nodes, got {kind}"
        )
    if not graph:
        raise WorkflowValidationError("Workflow has no nodes")

    # The UI-editor export is the most common wrong paste; name it explicitly
    # rather than letting it fail the per-node checks with a cryptic message.
    if any(key in graph for key in _UI_FORMAT_KEYS):
        raise WorkflowValidationError(
            "This looks like a ComfyUI UI-editor export (it has 'nodes'/'links'). "
            "Use ComfyUI's \"Save (API Format)\" — or Workflow → Export (API) — "
            "and import that file instead."
        )

    for node_id, node in graph.items():
        where = f"Node '{node_id}'"
        if not isinstance(node, dict):
            raise WorkflowValidationError(f"{where} must be an object")
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type.strip():
            raise WorkflowValidationError(f"{where} is missing a 'class_type' string")
        if "inputs" not in node:
            raise WorkflowValidationError(f"{where} ({class_type}) is missing 'inputs'")
        if not isinstance(node["inputs"], dict):
            raise WorkflowValidationError(
                f"{where} ({class_type}) has 'inputs' that is not an object"
            )
        meta = node.get("_meta")
        if meta is not None and not isinstance(meta, dict):
            raise WorkflowValidationError(f"{where} ({class_type}) has a non-object '_meta'")

    _validate_wiring(graph)
    return graph


def _validate_wiring(graph: Dict[str, Any]) -> None:
    """Reject links pointing at node ids that aren't in the graph.

    A dangling link is the one structural mistake that survives JSON parsing
    but always fails at submission time, and hand-editing (or deleting a node
    in the raw editor) is exactly how it happens.
    """
    dangling: List[str] = []
    for node_id, node in graph.items():
        for key, value in node["inputs"].items():
            # A connection is [source_node_id, output_index].
            if not isinstance(value, list) or not value:
                continue
            source = value[0]
            if isinstance(source, (str, int)) and str(source) not in graph:
                dangling.append(f"{node_id}.{key} → node '{source}'")
    if dangling:
        raise WorkflowValidationError(
            "Workflow has links to missing nodes: " + "; ".join(sorted(dangling)[:5])
        )


def parse_graph(raw: str) -> Dict[str, Any]:
    """Parse workflow JSON text and validate it. Used by the raw-JSON editor."""
    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowValidationError(f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})")
    return validate_graph(graph)


# ---------------------------------------------------------------------------
# Filesystem access
# ---------------------------------------------------------------------------

def _path_for(name: str) -> str:
    """Absolute path of a *validated* name inside the workflows directory."""
    return os.path.join(_workflows_dir(), normalize_name(name))


def _require_exists(name: str) -> str:
    path = _path_for(name)
    if not os.path.isfile(path):
        raise WorkflowNotFoundError(f"Unknown workflow '{name}'")
    return path


def _require_free(name: str) -> str:
    path = _path_for(name)
    if os.path.exists(path):
        raise WorkflowConflictError(f"A workflow named '{normalize_name(name)}' already exists")
    return path


def _atomic_write(path: str, graph: Dict[str, Any]) -> None:
    """Write the graph via a temp file + rename so a failure can't truncate.

    Workflow files are read by the Celery worker on every dispatch; a partial
    write would break generation until someone noticed.
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".wf-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(graph, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def summarize_workflows() -> List[Dict[str, Any]]:
    """Every workflow file with the metadata the management list shows.

    Unreadable or malformed files are listed with ``valid: False`` and their
    parse error rather than being hidden — a broken file the user needs to fix
    is precisely what they came to the page to see.
    """
    summaries: List[Dict[str, Any]] = []
    for name in list_workflow_files():
        path = os.path.join(_workflows_dir(), name)
        try:
            stat = os.stat(path)
            size_bytes, modified_at = stat.st_size, stat.st_mtime
        except OSError:
            size_bytes, modified_at = 0, 0.0
        entry: Dict[str, Any] = {
            "name": name,
            "size_bytes": size_bytes,
            "modified_at": modified_at,
            "node_count": 0,
            "valid": True,
            "error": None,
        }
        try:
            with open(path, "r") as handle:
                graph = json.load(handle)
            validate_graph(graph)
            entry["node_count"] = len(graph)
        except (OSError, json.JSONDecodeError, WorkflowValidationError) as exc:
            entry["valid"] = False
            entry["error"] = str(getattr(exc, "msg", None) or exc)
        summaries.append(entry)
    return summaries


def read_workflow_text(name: str) -> str:
    """Raw file contents, without parsing.

    The editor needs this even — especially — for files that don't parse: a
    broken workflow is repaired by editing its text, so failing here would make
    it unopenable.
    """
    path = _require_exists(name)
    with open(path, "r") as handle:
        return handle.read()


def read_workflow(name: str) -> Dict[str, Any]:
    """Load and parse a workflow graph (structure unvalidated)."""
    path = _require_exists(name)
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise WorkflowValidationError(
            f"'{normalize_name(name)}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        )


def save_workflow(name: str, graph: Any) -> str:
    """Overwrite an existing workflow with a validated graph. Returns its name."""
    path = _require_exists(name)
    _atomic_write(path, validate_graph(graph))
    return normalize_name(name)


def create_workflow(name: str, graph: Optional[Any] = None) -> str:
    """Create a new workflow file, refusing to clobber an existing one."""
    path = _require_free(name)
    _atomic_write(path, validate_graph(graph if graph is not None else blank_graph()))
    return normalize_name(name)


def duplicate_workflow(name: str, new_name: Optional[str] = None) -> str:
    """Copy a workflow under a new name (auto-suffixed when none is given)."""
    source = _require_exists(name)
    target_name = normalize_name(new_name) if new_name else _next_copy_name(name)
    path = _require_free(target_name)
    with open(source, "r") as handle:
        raw = handle.read()
    # Copy bytes rather than re-serializing so a duplicate of a broken file
    # stays byte-identical and repairable instead of failing validation here.
    with open(path, "w") as handle:
        handle.write(raw)
    return target_name


def rename_workflow(name: str, new_name: str) -> str:
    """Rename a workflow file. Refuses to overwrite a different existing file."""
    source = _require_exists(name)
    target_name = normalize_name(new_name)
    if target_name == normalize_name(name):
        return target_name
    target = _require_free(target_name)
    os.replace(source, target)
    return target_name


def delete_workflow(name: str) -> str:
    """Delete a workflow file. Returns the name that was removed."""
    path = _require_exists(name)
    os.unlink(path)
    return normalize_name(name)


def import_workflow(filename: str, raw: bytes) -> str:
    """Store an uploaded workflow file, side-stepping name collisions.

    Unlike :func:`create_workflow`, a collision is not an error: an import is a
    drag-and-drop gesture, so the upload lands beside the existing file under a
    ``copy`` name rather than failing or clobbering it.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise WorkflowValidationError("Workflow file must be UTF-8 encoded JSON")
    graph = parse_graph(text)

    name = normalize_name(os.path.basename(filename or "imported.json"))
    if os.path.exists(os.path.join(_workflows_dir(), name)):
        name = _next_copy_name(name)
    return create_workflow(name, graph)


def _next_copy_name(name: str) -> str:
    """``foo.json`` → ``foo copy.json``, then ``foo copy 2.json``, …"""
    stem = normalize_name(name)[: -len(".json")]
    candidate = f"{stem} copy.json"
    counter = 2
    existing = set(list_workflow_files())
    while candidate in existing:
        candidate = f"{stem} copy {counter}.json"
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# Starter graph for "New workflow"
# ---------------------------------------------------------------------------

def blank_graph() -> Dict[str, Any]:
    """A minimal valid text-to-image API graph to start editing from.

    Deliberately generic (checkpoint + two CLIP encodes + sampler + save) so it
    validates and submits as-is once the ``ckpt_name`` points at a real model.
    The positive prompt node is titled so the pipelines' prompt injection and
    the parameters form both recognise it.
    """
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "model.safetensors"},
            "_meta": {"title": "Load Checkpoint"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["1", 1]},
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["1", 1]},
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
            "_meta": {"title": "Empty Latent Image"},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
            "_meta": {"title": "KSampler"},
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "_meta": {"title": "VAE Decode"},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "ComfyUI", "images": ["6", 0]},
            "_meta": {"title": "Save Image"},
        },
    }
