from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """Public health check — also used for the keep-alive ping (#8)."""
    return {"status": "ok"}
