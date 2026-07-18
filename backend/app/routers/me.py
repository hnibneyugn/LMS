from fastapi import APIRouter, Depends

from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email}
