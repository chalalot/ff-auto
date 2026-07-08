from typing import List, Optional

from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectPatchRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    archived: Optional[bool] = None


class ProjectItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_member_id: Optional[str] = None
    created_at: Optional[str] = None
    archived_at: Optional[str] = None
    member_ids: List[str] = []


class ProjectMemberRequest(BaseModel):
    member_id: str


class AssignRequest(BaseModel):
    table: str
    ids: List[str]


class AssignResponse(BaseModel):
    updated: int
