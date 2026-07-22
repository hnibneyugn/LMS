from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    try:
        admin = settings.admin_email().strip().lower()
    except RuntimeError:
        admin = None  # ADMIN_EMAIL unset -> nobody is admin, but /api/me still works
    is_admin = bool(user.email) and admin is not None and user.email.strip().lower() == admin
    return {"user_id": user.user_id, "email": user.email, "is_admin": is_admin}
