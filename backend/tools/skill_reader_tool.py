"""SkillReaderTool — the progressive-disclosure primitive (P1, clause S4).

Exposes ONE capability to the Analyst agent: read a single reference file from
the vendored ``writing-image-prompts`` skill by its skill-relative path. All the
rooting, path-traversal guarding, and per-call read-logging live behind that one
verb, so the skill is consumed by progressive disclosure (open a map, then drill
into a detail file) rather than being concatenated up front.
"""
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)

# Vendored skill root: <repo>/prompts/skills/writing-image-prompts
# This file lives at <repo>/backend/tools/skill_reader_tool.py → parents[2] == repo.
DEFAULT_SKILL_ROOT = (
    Path(__file__).resolve().parents[2] / "prompts" / "skills" / "writing-image-prompts"
)


class SkillReaderInput(BaseModel):
    ref_path: str = Field(
        ...,
        description=(
            "Skill-relative path to ONE reference file, e.g. 'SKILL.md' or "
            "'references/lighting/lighting.md'. Open a section map before its "
            "detail files."
        ),
    )


class SkillReaderTool(BaseTool):
    name: str = "Skill Reader"
    description: str = (
        "Read ONE reference file from the writing-image-prompts skill by its "
        "skill-relative path (e.g. 'SKILL.md', 'references/lighting/lighting.md'). "
        "Returns the file's text. Walk the skill's sections in order and open a "
        "section map before opening any of its detail files."
    )
    args_schema: Type[BaseModel] = SkillReaderInput
    skill_root: str = str(DEFAULT_SKILL_ROOT)
    read_log: List[Tuple[int, str]] = Field(default_factory=list)

    def __init__(self, skill_root: Optional[object] = None, **kwargs):
        super().__init__(**kwargs)
        if skill_root is not None:
            self.skill_root = str(skill_root)

    def _run(self, ref_path: str) -> str:
        from backend.services.pipeline_trace import record_tool_call

        root = Path(self.skill_root).resolve()
        target = (root / ref_path).resolve()

        # Path-traversal guard: target must be the root or live under it.
        if target != root and root not in target.parents:
            logger.warning("[SkillReader] refused out-of-root path: %r", ref_path)
            result = f"Error: path {ref_path!r} escapes the skill root."
        elif not target.is_file():
            result = f"Error: skill reference {ref_path!r} not found."
        else:
            result = target.read_text(encoding="utf-8")
            self.read_log.append((len(self.read_log) + 1, ref_path))
        record_tool_call(self.name, {"ref_path": ref_path}, result)
        return result
