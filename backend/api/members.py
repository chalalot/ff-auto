"""Members API (phase 3)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database.members_storage import MembersStorage

router = APIRouter()


class MemberCreateRequest(BaseModel):
    name: str


class MemberItem(BaseModel):
    id: str
    name: str
    created_at: str | None = None


@router.get("", response_model=list[MemberItem])
def list_members():
    return MembersStorage().list_members()


@router.post("", response_model=MemberItem)
def create_member(body: MemberCreateRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Member name must not be blank")
    storage = MembersStorage()
    member_id = storage.get_or_create(name)
    return next(m for m in storage.list_members() if m["id"] == member_id)
