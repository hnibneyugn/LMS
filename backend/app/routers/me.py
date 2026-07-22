from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    admin = settings.admin_email().strip().lower()
    is_admin = bool(user.email) and user.email.strip().lower() == admin
    return {"user_id": user.user_id, "email": user.email, "is_admin": is_admin}
