from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """Public health check — cũng dùng cho keep-alive ping (#8)."""
    return {"status": "ok"}
