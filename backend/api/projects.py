"""Projects API (phase 3)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.identity import Identity, get_identity
from backend.database.projects_storage import ProjectsStorage
from backend.models.project import (
    AssignRequest,
    AssignResponse,
    ProjectCreateRequest,
    ProjectItem,
    ProjectMemberRequest,
    ProjectPatchRequest,
)

router = APIRouter()


@router.get("", response_model=list[ProjectItem])
def list_projects(include_archived: bool = Query(default=False)):
    return ProjectsStorage().list_projects(include_archived=include_archived)


@router.post("", response_model=ProjectItem)
def create_project(
    body: ProjectCreateRequest,
    identity: Identity = Depends(get_identity),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name must not be blank")
    return ProjectsStorage().create_project(
        name, description=body.description, owner_member_id=identity.member_id
    )


@router.patch("/{project_id}", response_model=ProjectItem)
def patch_project(project_id: str, body: ProjectPatchRequest):
    row = ProjectsStorage().update_project(
        project_id, name=body.name, description=body.description,
        archived=body.archived,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


@router.post("/{project_id}/members", response_model=ProjectItem)
def add_project_member(project_id: str, body: ProjectMemberRequest):
    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    storage.add_member(project_id, body.member_id)
    return storage.get_project(project_id)


@router.delete("/{project_id}/members/{member_id}", response_model=ProjectItem)
def remove_project_member(project_id: str, member_id: str):
    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    storage.remove_member(project_id, member_id)
    return storage.get_project(project_id)


@router.post("/{project_id}/assign", response_model=AssignResponse)
def assign_to_project(project_id: str, body: AssignRequest):
    from backend.database.projects_storage import ASSIGNABLE_TABLES

    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if body.table not in ASSIGNABLE_TABLES:
        raise HTTPException(
            status_code=422,
            detail=f"table must be one of: {', '.join(sorted(ASSIGNABLE_TABLES))}",
        )
    return AssignResponse(updated=storage.assign_rows(project_id, body.table, body.ids))
