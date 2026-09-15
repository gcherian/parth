"""
Backs static/founder_demo.html — the three-screen (student/teacher/parent)
founder & investor demo. One endpoint, idempotent: seeds the named Aarav
Sharma narrative and returns every id/name the page needs to drive the
real, already-shipped endpoints (/chat, /teacher/.../briefing,
/teacher/.../weekly-report, /parent/.../report, /parent/.../transcript,
/parent/.../alerts, /chrono-ritual/...) — no new business logic here.
"""
from fastapi import APIRouter, HTTPException

from modules.founder_demo.seed import seed as seed_founder_demo

router = APIRouter(prefix="/founder-demo", tags=["founder-demo"])


@router.post("/seed")
async def seed_endpoint():
    try:
        return await seed_founder_demo()
    except Exception as exc:  # noqa: BLE001 — surface to the demo page rather than 500 with no context
        raise HTTPException(status_code=500, detail=f"seed failed: {exc}")
