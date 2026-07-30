"""What each workflow file *is*, and where its inputs go.

Two things live here, both data rather than code, so a new kind of workflow is a
configuration change instead of an edit to the Create sidebar:

**Kinds** — the vocabulary the Create sidebar builds its Workflow Type and Mode
selects from. A kind's ``group`` is the Type; kinds sharing a group become the
Modes under it (``image_generation`` → I2I / T2I). ``needs_image``,
``uses_text`` and ``uses_ai`` are what the sidebar reads to decide which
controls to show and whether Process may fire without a selected image.

**Tags and bindings** — per workflow file: which kinds it can serve (so the
Workflow dropdown can be filtered to the ones that fit) and, optionally, which
node the prompt and the source image are written into. The bindings exist
because auto-detection has to guess: it takes the first ``CLIPTextEncode`` with
a literal ``text`` input, which is the negative prompt in about half the graphs
that have two. A binding is an override, not a requirement — with none set,
detection behaves exactly as it did before.

Stored as one JSON file in PROMPTS_DIR alongside ``options.json``, which is the
directory this deployment already bind-mounts for live-editable config.
"""
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from backend.config import GlobalConfig

logger = logging.getLogger(__name__)

REGISTRY_FILENAME = "workflow_registry.json"

# The kinds the app shipped with. Used when the registry file has no kinds of
# its own, so a fresh deployment behaves like the hardcoded list it replaces.
DEFAULT_KINDS: List[Dict[str, Any]] = [
    {
        "value": "image_generation.i2i",
        "label": "I2I — from a source image",
        "group": "image_generation",
        "group_label": "Image Generation",
        "needs_image": True,
        "uses_text": True,
        "uses_ai": True,
        "hint": "Image → LoadImage, prompt → CLIP Text Encode. Leave the prompt empty to let the AI write it from the image.",
    },
    {
        "value": "image_generation.t2i",
        "label": "T2I — prompt only",
        "group": "image_generation",
        "group_label": "Image Generation",
        "needs_image": False,
        "uses_text": True,
        "uses_ai": True,
        "hint": "Prompt → CLIP Text Encode. A T2I graph has no LoadImage node, so there is no image to select.",
    },
    {
        "value": "image_upscaler",
        "label": "Image Upscaler",
        "group": "image_upscaler",
        "group_label": "Image Upscaler",
        "needs_image": True,
        "uses_text": False,
        "uses_ai": False,
        "hint": "Image → LoadImage. Runs the workflow directly on each selected image.",
    },
    {
        "value": "multiangle_edit",
        "label": "Multiangle Edit",
        "group": "multiangle_edit",
        "group_label": "Multiangle Edit",
        "needs_image": True,
        "uses_text": True,
        "uses_ai": False,
        "hint": "Image → LoadImage, prompt → CLIP Text Encode. Camera angles are edited in Workflow Parameters.",
    },
]

_BOOL_FIELDS = ("needs_image", "uses_text", "uses_ai")


class RegistryValidationError(ValueError):
    """A kind list or a workflow entry the registry refuses to store."""


def _registry_path() -> str:
    return os.path.join(GlobalConfig.PROMPTS_DIR, REGISTRY_FILENAME)


def _read() -> Dict[str, Any]:
    """The registry file as stored, or an empty shell if it is absent/broken.

    A malformed file is logged and ignored rather than raised: the Create
    sidebar has to render, and falling back to the defaults leaves the app
    usable while the file gets fixed.
    """
    path = _registry_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f"Failed to read {path}: {exc}")
        return {}


def _write(data: Dict[str, Any]) -> None:
    """Temp file + rename, so a crash mid-write can't leave a truncated file.

    The worker reads this on every dispatch to resolve bindings.
    """
    path = _registry_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".registry-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, path)
        # The UI writes this through the container, which runs as root; without
        # this the file lands 0600 and the host user cannot edit or commit it.
        try:
            os.chmod(path, 0o664)
        except OSError:
            pass
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Kinds (the Workflow Type / Mode vocabulary)
# ---------------------------------------------------------------------------

def get_kinds() -> List[Dict[str, Any]]:
    """The configured kinds, or the built-in defaults when none are stored."""
    stored = _read().get("kinds")
    if isinstance(stored, list) and stored:
        return [_clean_kind(k) for k in stored if isinstance(k, dict)]
    return [dict(k) for k in DEFAULT_KINDS]


def _clean_kind(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in a stored kind's optional fields so the UI never sees a hole."""
    value = str(raw.get("value") or "").strip()
    group = str(raw.get("group") or "").strip() or value.split(".")[0]
    label = str(raw.get("label") or "").strip() or value
    return {
        "value": value,
        "label": label,
        "group": group,
        "group_label": str(raw.get("group_label") or "").strip() or group,
        "needs_image": bool(raw.get("needs_image", True)),
        "uses_text": bool(raw.get("uses_text", True)),
        "uses_ai": bool(raw.get("uses_ai", False)),
        "hint": str(raw.get("hint") or ""),
    }


def save_kinds(kinds: Any) -> List[Dict[str, Any]]:
    """Replace the kind vocabulary. Returns what is now stored."""
    if not isinstance(kinds, list) or not kinds:
        raise RegistryValidationError("At least one workflow kind is required")

    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for raw in kinds:
        if not isinstance(raw, dict):
            raise RegistryValidationError("Each kind must be an object")
        kind = _clean_kind(raw)
        if not kind["value"]:
            raise RegistryValidationError("Each kind needs a value")
        if kind["value"] in seen:
            raise RegistryValidationError(f"Duplicate kind value '{kind['value']}'")
        seen.add(kind["value"])
        cleaned.append(kind)

    data = _read()
    data["kinds"] = cleaned
    # Tags naming a kind that no longer exists would silently hide their
    # workflow from every dropdown, so drop those references as we go.
    workflows = data.get("workflows")
    if isinstance(workflows, dict):
        for entry in workflows.values():
            if isinstance(entry, dict) and isinstance(entry.get("kinds"), list):
                entry["kinds"] = [k for k in entry["kinds"] if k in seen]
    _write(data)
    return cleaned


# ---------------------------------------------------------------------------
# Per-workflow tags and node bindings
# ---------------------------------------------------------------------------

def _blank_entry() -> Dict[str, Any]:
    return {"kinds": [], "prompt_node": None, "image_node": None}


def get_tags() -> Dict[str, Dict[str, Any]]:
    """Every stored workflow entry, keyed by filename."""
    workflows = _read().get("workflows")
    if not isinstance(workflows, dict):
        return {}
    return {
        name: _clean_entry(entry)
        for name, entry in workflows.items()
        if isinstance(entry, dict)
    }


def _clean_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    kinds = raw.get("kinds")
    node = lambda key: (  # noqa: E731 - a node id is a string or nothing
        str(raw[key]).strip() or None if raw.get(key) not in (None, "") else None
    )
    return {
        "kinds": [str(k) for k in kinds if isinstance(k, (str, int))] if isinstance(kinds, list) else [],
        "prompt_node": node("prompt_node"),
        "image_node": node("image_node"),
    }


def get_entry(workflow_name: str) -> Dict[str, Any]:
    """One workflow's entry, or a blank one when it has never been tagged."""
    return get_tags().get(workflow_name, _blank_entry())


def save_entry(workflow_name: str, entry: Any) -> Dict[str, Any]:
    """Store one workflow's tags and bindings. Returns the stored entry."""
    if not isinstance(entry, dict):
        raise RegistryValidationError("Entry must be an object")
    cleaned = _clean_entry(entry)

    known = {k["value"] for k in get_kinds()}
    unknown = [k for k in cleaned["kinds"] if k not in known]
    if unknown:
        raise RegistryValidationError(f"Unknown workflow kind(s): {', '.join(unknown)}")

    data = _read()
    workflows = data.get("workflows")
    if not isinstance(workflows, dict):
        workflows = {}
    # An entry with nothing in it is absence, not a record — otherwise clearing
    # every field leaves a row that reads as "configured".
    if cleaned == _blank_entry():
        workflows.pop(workflow_name, None)
    else:
        workflows[workflow_name] = cleaned
    data["workflows"] = workflows
    _write(data)
    return cleaned


def rename_entry(old_name: str, new_name: str) -> None:
    """Follow a renamed workflow file, so its tags aren't orphaned."""
    data = _read()
    workflows = data.get("workflows")
    if not isinstance(workflows, dict) or old_name not in workflows:
        return
    workflows[new_name] = workflows.pop(old_name)
    data["workflows"] = workflows
    _write(data)


def delete_entry(workflow_name: str) -> None:
    """Drop a deleted workflow's tags, so a later file of the same name starts clean."""
    data = _read()
    workflows = data.get("workflows")
    if not isinstance(workflows, dict) or workflow_name not in workflows:
        return
    del workflows[workflow_name]
    data["workflows"] = workflows
    _write(data)


def get_bindings(workflow_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """``(prompt_node, image_node)`` for a workflow — ``(None, None)`` if unset.

    Called on every dispatch. Both being None means "detect the nodes", which is
    what every workflow did before bindings existed.
    """
    if not workflow_name:
        return None, None
    entry = get_entry(workflow_name)
    return entry["prompt_node"], entry["image_node"]
