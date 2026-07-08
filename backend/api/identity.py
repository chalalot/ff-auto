"""Header-based identity (phase 3). No auth — X-Member-Name is trusted.

Both headers are optional and both failure modes are silent by design:
a missing member stamps nothing (content lands in "Unassigned"), and a
stale/unknown project id from localStorage must never brick the UI.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Header


@dataclass
class Identity:
    member_id: Optional[str]
    project_id: Optional[str]


def get_identity(
    x_member_name: Optional[str] = Header(default=None),
    x_project_id: Optional[str] = Header(default=None),
) -> Identity:
    member_id = None
    name = (x_member_name or "").strip()
    if name:
        from backend.database.members_storage import MembersStorage

        member_id = MembersStorage().get_or_create(name)

    project_id = None
    if x_project_id:
        from backend.database.projects_storage import ProjectsStorage

        if ProjectsStorage().exists(x_project_id):
            project_id = x_project_id
    return Identity(member_id=member_id, project_id=project_id)
