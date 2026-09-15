"""
Master demo endpoints — backs static/master_demo.html.

Runs the real server/tests/demo_gap_*.py scripts (the same ones each PR's
own build was verified against) on demand and returns their live output,
so the demo page shows the actual system running, not a mock.
"""
from fastapi import APIRouter, HTTPException

from modules.master_demo.runner import list_features, run_feature

router = APIRouter(prefix="/master-demo", tags=["master-demo"])


@router.get("/features")
async def get_features():
    """Metadata for all 8 gap-closing features, in PR order."""
    return {"features": list_features()}


@router.post("/run/{key}")
async def run_one(key: str):
    """
    Runs one feature's real demo script in-process against the live app and
    DB, and returns its actual stdout plus a derived pass/fail. Each script
    is independently idempotent/collision-safe (see their own docstrings),
    so repeated clicks are safe.
    """
    result = await run_feature(key)
    if result.get("error") and "unknown feature key" in result["error"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
