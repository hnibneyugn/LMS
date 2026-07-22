"""Admin-only member management (#7): invite a member, list members.

Thin router — Supabase Admin API calls live in app/admin/members.py. Every
route depends on require_admin (the real authorization boundary)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.admin import members
from app.dependencies.auth import CurrentUser, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class InviteIn(BaseModel):
    email: str


class Member(BaseModel):
    email: str
    password_set: bool
    created_at: str | None = None


def _valid_email(email: str) -> bool:
    email = email.strip()
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain


@router.get("/members", response_model=list[Member])
def list_members(_: CurrentUser = Depends(require_admin)):
    try:
        return members.list_members()
    except httpx.HTTPError as err:
        raise HTTPException(502, "Không tải được danh sách thành viên.") from err


@router.post("/invite", response_model=Member, status_code=201)
def invite(body: InviteIn, _: CurrentUser = Depends(require_admin)):
    if not _valid_email(body.email):
        raise HTTPException(422, "Email không hợp lệ.")
    try:
        return members.invite_member(body.email)
    except members.AlreadyMemberError as err:
        raise HTTPException(409, str(err)) from err
    except members.InviteError as err:
        raise HTTPException(502, str(err)) from err
